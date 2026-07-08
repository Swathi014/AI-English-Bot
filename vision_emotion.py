"""
vision_emotion.py
------------------
Live face detection + emotion recognition, running as a background
thread so the voice/conversation loop is never blocked waiting on
camera frames.

This is deliberately built with the SAME architecture pattern as your
existing Features 5 & 6 emotion pipeline (multi-person capable,
temporal smoothing, confidence thresholding, action cooldowns) so it
should feel familiar and is easy to swap for your actual trained model.

Two ways to use this file:

  OPTION A (recommended if you already have Features 5 & 6 built):
      Skip the built-in classifier entirely. Set `EXTERNAL_PIPELINE`
      below to import and call your existing multi-person emotion
      detector, and just keep this file's threading/smoothing/cooldown
      wrapper. See the `_predict_emotion` docstring for the exact
      plug-in point.

  OPTION B (standalone / no existing pipeline wired in yet):
      Uses OpenCV Haar cascade for face detection (bundled with
      opencv-python, no extra downloads) + a pluggable Keras model for
      emotion classification. If no trained model file is found, it
      logs a warning and falls back to a neutral "no signal" state
      rather than crashing -- so the rest of the app runs fine while
      you finish training/wiring the real model.

Output is intentionally coarse: one "current emotion snapshot" for the
main student in frame (largest detected face), not raw per-frame
predictions. That's what main.py reads before each conversation turn.
"""

import logging
import os
import threading
import time
from collections import deque, Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("teacher_lily.vision")

# Matches this project's actual trained model: 5 classes, alphabetically
# ordered to match how Keras' flow_from_directory / image_dataset_from_directory
# assigns class indices during training (sorted by folder name). Confirmed
# from the training data folder structure: Angry, Happy, Neutral, Sad, Suprise.
# Note: "surprise" is intentionally spelled to match the original folder name
# ("Suprise") in case that affects anything downstream -- display-only, so if
# you want it spelled correctly on screen, just change the string here; the
# list ORDER is what actually matters and must match your training folders.
EMOTION_LABELS = ["angry", "happy", "neutral", "sad", "surprise"]

# --- Tunables (match the pattern of your existing Features 5 & 6 system) ---
FRAME_SAMPLE_INTERVAL = 0.3      # seconds between processed frames (perf)
SMOOTHING_WINDOW = 8              # number of recent predictions to smooth over
CONFIDENCE_THRESHOLD = 0.45       # ignore single predictions below this
STABLE_VOTE_RATIO = 0.5           # fraction of window that must agree to "commit" an emotion
COOLDOWN_SECONDS = 4.0            # minimum time between emitted emotion-state changes

MODEL_PATH_ENV_VAR = "LILY_EMOTION_MODEL_PATH"
DEFAULT_MODEL_PATH = "models/emotion_model.h5"


@dataclass
class EmotionState:
    emotion: str
    confidence: float
    face_detected: bool
    updated_at: str

    @classmethod
    def no_face(cls):
        return cls(emotion="neutral", confidence=0.0, face_detected=False,
                    updated_at=datetime.now(timezone.utc).isoformat())


class _EmotionClassifier:
    """
    Thin wrapper around a Keras emotion model. Falls back gracefully
    if no model file is present, so the rest of the app keeps working
    while you finish training/exporting your model.

    PLUG-IN POINT: point LILY_EMOTION_MODEL_PATH at your trained
    .h5/.keras file. Rather than assuming a fixed 48x48 grayscale input,
    this introspects the model's actual `input_shape` at load time and
    adapts preprocessing (size, grayscale vs. RGB) to match -- so it
    works with your real model's shape, whatever that turns out to be.
    Assumes a single-input model outputting an N-class softmax; if N
    doesn't match len(EMOTION_LABELS), predictions still work but are
    reported as generic class indices (see predict()).
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.model = None
        self.input_hw = (48, 48)   # (height, width), overwritten on load
        self.channels = 1           # overwritten on load
        self.num_classes = len(EMOTION_LABELS)

        if model_path is None:
            # Resolved HERE (at instantiation), not at module import time,
            # so it correctly picks up a .env value loaded via load_dotenv()
            # even though that happens after this module is first imported.
            model_path = Path(os.environ.get(MODEL_PATH_ENV_VAR, DEFAULT_MODEL_PATH))

        self._load(model_path)

    def _load(self, model_path: Path):
        if not model_path.exists():
            logger.warning(
                f"No emotion model found at '{model_path}'. Running in "
                f"NO-SIGNAL fallback mode (always neutral, 0 confidence) "
                f"until a trained model is wired in."
            )
            return
        try:
            from tensorflow import keras  # local import -- optional heavy dep
            self.model = keras.models.load_model(str(model_path))

            shape = self.model.input_shape  # e.g. (None, 48, 48, 1)
            if isinstance(shape, list):      # some models report a list of input shapes
                shape = shape[0]

            _, h, w, c = shape
            self.input_hw = (h or 48, w or 48)
            self.channels = c or 1

            out_shape = self.model.output_shape
            if isinstance(out_shape, list):
                out_shape = out_shape[0]
            self.num_classes = out_shape[-1] or len(EMOTION_LABELS)

            logger.info(
                f"Loaded emotion model from {model_path} "
                f"(input={self.input_hw + (self.channels,)}, classes={self.num_classes})"
            )

            if self.num_classes != len(EMOTION_LABELS):
                logger.warning(
                    f"Model has {self.num_classes} output classes but EMOTION_LABELS "
                    f"has {len(EMOTION_LABELS)}. Update EMOTION_LABELS at the top of "
                    f"this file to match your model's actual class order."
                )
        except Exception as e:
            logger.error(f"Failed to load emotion model: {e}. Falling back to no-signal mode.")
            self.model = None

    def predict(self, face_bgr: np.ndarray) -> tuple[str, float]:
        """
        Returns (label, confidence) for a single cropped face, given as
        a BGR color crop straight from OpenCV (as produced by
        `_process_frame`). Converts to grayscale or RGB internally
        depending on what the loaded model actually expects.
        """
        if self.model is None:
            return "neutral", 0.0

        try:
            if self.channels == 1:
                face = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
            else:
                face = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)

            face = cv2.resize(face, (self.input_hw[1], self.input_hw[0]))  # cv2.resize wants (w, h)
            face = face.astype("float32") / 255.0

            if self.channels == 1:
                face = np.expand_dims(face, axis=-1)  # (H, W, 1)
            face = np.expand_dims(face, axis=0)         # (1, H, W, C)

            probs = self.model.predict(face, verbose=0)[0]
            idx = int(np.argmax(probs))
            label = EMOTION_LABELS[idx] if idx < len(EMOTION_LABELS) else f"class_{idx}"
            return label, float(probs[idx])
        except Exception as e:
            logger.error(f"Emotion prediction failed on this frame: {e}")
            return "neutral", 0.0


class EmotionVisionSystem:
    """
    Background thread that continuously watches the camera, detects
    the primary student's face, classifies emotion, applies temporal
    smoothing + confidence thresholding + a cooldown, and exposes a
    thread-safe `get_current_state()` snapshot for main.py to read
    before each conversation turn.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.classifier = _EmotionClassifier()
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        self._history = deque(maxlen=SMOOTHING_WINDOW)
        self._state = EmotionState.no_face()
        self._lock = threading.Lock()
        self._last_commit_time = 0.0
        self._stop_event = threading.Event()
        self._thread = None

    # ---- public API ----

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Emotion vision system started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Emotion vision system stopped.")

    def get_current_state(self) -> EmotionState:
        with self._lock:
            return self._state

    # ---- internals ----

    def _run_loop(self):
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            logger.error("Could not open camera. Emotion detection disabled for this session.")
            return

        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(FRAME_SAMPLE_INTERVAL)
                    continue

                self._process_frame(frame)
                time.sleep(FRAME_SAMPLE_INTERVAL)
        finally:
            cap.release()

    def _process_frame(self, frame: np.ndarray):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )

        if len(faces) == 0:
            self._maybe_commit(EmotionState.no_face())
            return

        # "The student" = largest face in frame (closest to camera/robot).
        # Multi-person support: swap this for your Features 5/6 tracker if
        # you need to distinguish multiple children by identity.
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_crop_bgr = frame[y:y + h, x:x + w]  # color crop -- classifier converts as needed

        label, confidence = self.classifier.predict(face_crop_bgr)

        if confidence >= CONFIDENCE_THRESHOLD:
            self._history.append(label)

        self._maybe_commit_from_history()

    def _maybe_commit_from_history(self):
        if not self._history:
            return

        counts = Counter(self._history)
        top_label, top_count = counts.most_common(1)[0]
        vote_ratio = top_count / len(self._history)

        if vote_ratio >= STABLE_VOTE_RATIO:
            avg_confidence = top_count / len(self._history)
            self._maybe_commit(EmotionState(
                emotion=top_label,
                confidence=round(avg_confidence, 2),
                face_detected=True,
                updated_at=datetime.now(timezone.utc).isoformat(),
            ))

    def _maybe_commit(self, new_state: EmotionState):
        """Applies the cooldown so state doesn't flicker turn-to-turn."""
        now = time.time()
        with self._lock:
            changed = new_state.emotion != self._state.emotion or \
                       new_state.face_detected != self._state.face_detected
            if changed and (now - self._last_commit_time) < COOLDOWN_SECONDS:
                return  # still in cooldown, ignore this change
            if changed:
                self._last_commit_time = now
                logger.info(
                    f"Emotion state -> {new_state.emotion} "
                    f"(confidence={new_state.confidence}, face_detected={new_state.face_detected})"
                )
            self._state = new_state
