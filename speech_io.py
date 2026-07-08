"""
speech_io.py
------------
Speech input/output layer for Teacher Lily.

STT: OpenAI Whisper (local, offline) -- matches the approach used in
     your KidRails Robot project. Requires the `ffmpeg` BINARY on your
     system PATH (separate from any Python ffmpeg package) -- Whisper
     shells out to it internally to decode/resample audio regardless
     of input format.
TTS: gTTS + pygame -- also consistent with KidRails.

Both are wrapped behind simple functions so you can swap engines
(e.g. faster-whisper, pyttsx3, ElevenLabs, a robot's built-in TTS)
without touching agent.py or main.py.
"""

import logging
import os
import shutil
import tempfile
import uuid

logger = logging.getLogger("teacher_lily.speech")

# ---- Dependency check ----


def ffmpeg_available() -> bool:
    """Checks whether the ffmpeg binary is discoverable on PATH."""
    return shutil.which("ffmpeg") is not None


# ---- Speech-to-Text (Whisper) ----

_whisper_model = None


def _get_whisper_model(model_size: str = "base"):
    global _whisper_model
    if _whisper_model is None:
        import whisper  # pip install openai-whisper
        logger.info(f"Loading Whisper model '{model_size}'...")
        _whisper_model = whisper.load_model(model_size)
    return _whisper_model


def transcribe_audio(audio_path: str, model_size: str = "base") -> str:
    """
    Transcribe a WAV/MP3 file to text using local Whisper.
    Returns an empty string on silence/failure rather than raising,
    so the main loop can just re-prompt the child.
    """
    if not ffmpeg_available():
        logger.error(
            "ffmpeg is not on your PATH -- Whisper cannot decode audio without it. "
            "Install it (e.g. `choco install ffmpeg` on Windows) and RESTART your "
            "terminal/IDE so the updated PATH takes effect."
        )
        return ""

    try:
        model = _get_whisper_model(model_size)
        result = model.transcribe(audio_path, language="en", fp16=False)
        text = result.get("text", "").strip()
        logger.info(f"Heard: {text!r}")
        return text
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return ""


def record_from_microphone(duration: float = 5.0, samplerate: int = 16000) -> str:
    """
    Records `duration` seconds from the default microphone and returns
    a path to a temp WAV file. Requires `sounddevice` + `numpy` + `scipy`.
    Swap this out entirely if your robot has its own mic capture API.

    Uses a unique filename per call so nothing can collide with a file
    still being read/played elsewhere.
    """
    import sounddevice as sd
    from scipy.io.wavfile import write as wav_write

    logger.info("Listening...")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()

    tmp_path = os.path.join(tempfile.gettempdir(), f"lily_input_{uuid.uuid4().hex}.wav")
    wav_write(tmp_path, samplerate, recording)
    return tmp_path


# ---- Text-to-Speech (gTTS + pygame) ----

_pygame_ready = False


def _ensure_pygame():
    global _pygame_ready
    if not _pygame_ready:
        import pygame
        pygame.mixer.init()
        _pygame_ready = True


def speak(text: str, lang: str = "en", slow: bool = False):
    """
    Speaks `text` aloud using gTTS (cloud) + pygame playback.
    For a fully offline robot, swap gTTS for pyttsx3 or your robot's
    native TTS -- the function signature can stay identical.

    Uses a unique temp filename per call AND explicitly unloads the
    track from pygame's mixer after playback. Windows keeps a file
    handle locked on whatever pygame last loaded, so re-using a fixed
    filename (or forgetting to unload) causes PermissionError on the
    next write -- this avoids both.
    """
    if not text:
        return

    tmp_path = os.path.join(tempfile.gettempdir(), f"lily_output_{uuid.uuid4().hex}.mp3")

    try:
        from gtts import gTTS
        import pygame

        _ensure_pygame()

        gTTS(text=text, lang=lang, slow=slow).save(tmp_path)

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        # Release the file handle so it (and future temp files) can be
        # cleaned up / rewritten without a Windows PermissionError.
        pygame.mixer.music.unload()

    except Exception as e:
        logger.error(f"TTS playback failed: {e}")
        # Fallback: at least print it so the loop doesn't die silently
        print(f"[Lily would say]: {text}")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass  # best-effort cleanup; not worth failing the turn over