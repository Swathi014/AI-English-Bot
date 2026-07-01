"""
main.py
-------
Entry point for Teacher Lily. Runs the listen -> think -> speak loop.

Usage:
    python main.py                       # voice mode, default child profile
    python main.py --child aanya         # voice mode, named profile
    python main.py --text                # type instead of speaking (for dev/testing)

Environment:
    ANTHROPIC_API_KEY must be set (see .env.example).
"""

import argparse
import logging
import os

from dotenv import load_dotenv

from agent import TeacherLilyAgent
import speech_io
import robot_interface

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("teacher_lily.main")


def run_voice_mode(agent: TeacherLilyAgent):
    logger.info("🌟 Teacher Lily is starting a voice session. Press Ctrl+C to stop.")
    robot_interface.robot_gesture("wave")
    speech_io.speak("Hi hi! I'm Lily! Let's practice English together!")

    agent.start_session()
    try:
        while True:
            audio_path = speech_io.record_from_microphone(duration=5.0)
            child_text = speech_io.transcribe_audio(audio_path)

            if not child_text:
                speech_io.speak("Hmm, I didn't catch that. Can you say it again?")
                continue

            if child_text.strip().lower() in {"stop", "bye", "goodbye", "quit"}:
                break

            reply = agent.handle_child_utterance(child_text)
            speech_io.speak(reply)

    except KeyboardInterrupt:
        pass
    finally:
        robot_interface.robot_gesture("celebrate")
        speech_io.speak("Great job today! Bye bye! See you next time!")
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


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Teacher Lily - AI English Teacher")
    parser.add_argument("--child", default="default", help="Child profile ID (used for memory)")
    parser.add_argument("--text", action="store_true", help="Run in text mode instead of voice")
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your free key "
            "from https://console.groq.com/keys"
        )

    agent = TeacherLilyAgent(child_id=args.child)

    if args.text:
        run_text_mode(agent)
    else:
        run_voice_mode(agent)


if __name__ == "__main__":
    main()
