"""
main.py
-------
Entry point for Teacher Lily. Runs the listen -> think -> speak loop.

Usage:
    python main.py                       # voice mode WITH the live UI window
    python main.py --no-ui               # voice mode, console-only (old behavior)
    python main.py --child aanya         # voice mode, named profile
    python main.py --text                # type instead of speaking (dev/testing, console-only)

Environment:
    GROQ_API_KEY must be set (see .env.example).
    LILY_EMOTION_MODEL_PATH optional -- path to your trained emotion model.
"""

import argparse
import logging
import threading

from dotenv import load_dotenv

load_dotenv()  # must happen before importing modules below that read env vars

import os

from agent import TeacherLilyAgent
import speech_io
import robot_interface
from vision_emotion import EmotionVisionSystem

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("teacher_lily.main")


def run_voice_mode(agent: TeacherLilyAgent, ui=None, stop_event: threading.Event = None):
    """
    The core listen -> think -> speak loop. If `ui` is provided, pushes
    transcript/emotion/status updates into it (thread-safe) instead of
    (or in addition to) printing to console. If `stop_event` is provided,
    the loop checks it between turns so an external UI "Stop" button can
    end the session cleanly (in addition to voice commands like "stop").
    """
    stop_event = stop_event or threading.Event()

    def say(text: str):
        if ui:
            ui.log_lily(text)
        speech_io.speak(text)

    def note(text: str):
        logger.info(text)
        if ui:
            ui.log_system(text)

    note("🌟 Teacher Lily is starting a voice session.")
    robot_interface.robot_gesture("wave")
    say("Hi hi! I'm Lily! Let's practice English together!")

    vision = EmotionVisionSystem()
    vision.start()

    agent.start_session()
    try:
        while not stop_event.is_set():
            if ui:
                ui.set_status("● Listening", "#6fcf97")

            audio_path = speech_io.record_from_microphone(duration=5.0)
            child_text = speech_io.transcribe_audio(audio_path)

            # Best-effort cleanup of the temp recording file
            try:
                os.remove(audio_path)
            except OSError:
                pass

            if stop_event.is_set():
                break

            if not child_text:
                say("Hmm, I didn't catch that. Can you say it again?")
                continue

            if ui:
                ui.log_child(child_text)

            if child_text.strip().lower() in {"stop", "bye", "goodbye", "quit"}:
                break

            if ui:
                ui.set_status("● Thinking...", "#f2c94c")

            emotion_state = vision.get_current_state()
            if ui:
                ui.set_emotion(emotion_state.emotion, emotion_state.confidence, emotion_state.face_detected)

            reply = agent.handle_child_utterance(
                child_text,
                detected_emotion={
                    "emotion": emotion_state.emotion,
                    "confidence": emotion_state.confidence,
                    "face_detected": emotion_state.face_detected,
                },
            )

            if ui:
                ui.set_status("● Speaking", "#7ec8e3")
            say(reply)

    finally:
        vision.stop()
        robot_interface.robot_gesture("celebrate")
        if ui:
            ui.set_status("● Session ended", "#8a8a8a")
        say("Great job today! Bye bye! See you next time!")
        agent.end_session()


def run_text_mode(agent: TeacherLilyAgent):
    logger.info("🌟 Teacher Lily text mode (dev/testing). Type 'quit' to stop.")
    print("Lily: Hi hi! I'm Lily! Let's practice English together!")

    agent.start_session()
    try:
        while True:
            child_text = input("Child: ").strip()
            if not child_text or child_text.lower() in {"stop", "bye", "goodbye", "quit"}:
                break
            reply = agent.handle_child_utterance(child_text)
            print(f"Lily: {reply}")
    except KeyboardInterrupt:
        pass
    finally:
        print("Lily: Great job today! Bye bye! See you next time!")
        agent.end_session()


def check_voice_dependencies():
    """Fails fast with a clear message instead of silently erroring on every turn."""
    if not speech_io.ffmpeg_available():
        raise SystemExit(
            "ffmpeg is not on your PATH. Whisper (speech-to-text) needs it to run.\n"
            "Install it, e.g. on Windows: `choco install ffmpeg`\n"
            "Then RESTART your terminal/IDE so the updated PATH takes effect, and try again.\n"
            "(Skip this check with --text mode, which doesn't need a microphone.)"
        )


def main():
    parser = argparse.ArgumentParser(description="Teacher Lily - AI English Teacher")
    parser.add_argument("--child", default="default", help="Child profile ID (used for memory)")
    parser.add_argument("--text", action="store_true", help="Run in text mode instead of voice")
    parser.add_argument("--no-ui", action="store_true", help="Voice mode without the live UI window (console only)")
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your free key "
            "from https://console.groq.com/keys"
        )

    agent = TeacherLilyAgent(child_id=args.child)

    if args.text:
        run_text_mode(agent)
        return

    check_voice_dependencies()

    if args.no_ui:
        run_voice_mode(agent)
        return

    # UI mode: Tkinter must own the main thread, so the voice loop runs
    # in a background thread and pushes updates into the UI via a queue.
    from ui import TeacherLilyUI

    stop_event = threading.Event()
    ui = TeacherLilyUI(on_stop=stop_event.set)

    worker = threading.Thread(target=run_voice_mode, args=(agent, ui, stop_event), daemon=True)
    worker.start()

    ui.run()  # blocks main thread until the window is closed
    stop_event.set()
    worker.join(timeout=3.0)


if __name__ == "__main__":
    main()
