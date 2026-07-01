"""
speech_io.py
------------
Speech input/output layer for Teacher Lily.

STT: OpenAI Whisper (local, offline) -- matches the approach used in
     your KidRails Robot project.
TTS: gTTS + pygame -- also consistent with KidRails, so this should
     drop in with minimal changes to your existing audio pipeline.

Both are wrapped behind simple functions so you can swap engines
(e.g. faster-whisper, pyttsx3, ElevenLabs, a robot's built-in TTS)
without touching agent.py or main.py.
"""

import io
import logging
import os
import tempfile

logger = logging.getLogger("teacher_lily.speech")

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
    """
    import sounddevice as sd
    from scipy.io.wavfile import write as wav_write

    logger.info("Listening...")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype="int16")
    sd.wait()

    tmp_path = os.path.join(tempfile.gettempdir(), "lily_input.wav")
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
    """
    if not text:
        return

    try:
        from gtts import gTTS
        import pygame

        _ensure_pygame()

        tmp_path = os.path.join(tempfile.gettempdir(), "lily_output.mp3")
        gTTS(text=text, lang=lang, slow=slow).save(tmp_path)

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

    except Exception as e:
        logger.error(f"TTS playback failed: {e}")
        # Fallback: at least print it so the loop doesn't die silently
        print(f"[Lily would say]: {text}")
