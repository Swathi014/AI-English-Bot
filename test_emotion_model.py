"""
test_emotion_model.py
----------------------
Standalone sanity check for wiring in your real trained emotion model
-- run this BEFORE running the full main.py, so model-loading issues
are easy to diagnose on their own.

Usage:
    # PowerShell -- set the env var for this session, then run:
    $env:LILY_EMOTION_MODEL_PATH = "D:/EVOLVE ROBOTICS/Emotion Detection using Opencv/Multi-person-emotion-detection/emotion_detection_model.keras"
    python test_emotion_model.py

This will:
  1. Load your model and print its detected input shape / class count
  2. Open your webcam
  3. Show a live window with the detected face box + predicted emotion
     and confidence overlaid
  4. Press 'q' to quit

If step 1 fails, the error will tell you exactly what's wrong (bad
path, incompatible TF/Keras version, corrupted file, etc.) without
needing to run the whole voice pipeline to find out.
"""

import os
import sys

import cv2
from dotenv import load_dotenv

load_dotenv()  # must happen BEFORE importing vision_emotion's classifier below

from vision_emotion import _EmotionClassifier, EMOTION_LABELS, MODEL_PATH_ENV_VAR, DEFAULT_MODEL_PATH


def main():
    model_path = os.environ.get(MODEL_PATH_ENV_VAR, DEFAULT_MODEL_PATH)
    print(f"Loading model from: {model_path}")
    classifier = _EmotionClassifier()

    if classifier.model is None:
        print("\n❌ Model failed to load (see error above). Fix this before running main.py.")
        sys.exit(1)

    print(f"✅ Model loaded successfully.")
    print(f"   Input shape expected: {classifier.input_hw + (classifier.channels,)}")
    print(f"   Output classes: {classifier.num_classes}")
    print(f"   EMOTION_LABELS in code: {EMOTION_LABELS}")
    if classifier.num_classes != len(EMOTION_LABELS):
        print(f"   ⚠️  Class count mismatch -- update EMOTION_LABELS in vision_emotion.py "
              f"to match your model's actual {classifier.num_classes} classes/order.")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("\n❌ Could not open webcam (index 0). Check your camera connection/permissions.")
        sys.exit(1)

    print("\n🎥 Webcam opened. Press 'q' in the video window to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

        for (x, y, w, h) in faces:
            face_crop = frame[y:y + h, x:x + w]
            label, confidence = classifier.predict(face_crop)

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                frame, f"{label} ({confidence:.2f})",
                (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2
            )

        cv2.imshow("Teacher Lily -- Emotion Model Test (press q to quit)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
