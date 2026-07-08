"""
agent.py
--------
Core conversational agent for Teacher Lily -- now running on Groq's
FREE cloud API instead of a paid provider.

Groq (console.groq.com) hosts open-source models (including Llama 3.3
70B -- the exact model this project's system prompt was written for)
on their own custom LPU chips, served over the cloud. No local GPU,
no Ollama install, no hardware requirements on your end. The free
tier requires no credit card: ~30 requests/min, ~1,000 requests/day,
which is more than enough for developing and running a kids' tutoring
session (each turn is one request).

Wires together:
  - The system prompt (system_prompt.md)
  - The tool schema (tool_schemas.json)  -> OpenAI-compatible tool-use,
    which Groq implements natively
  - Per-child memory (memory.py)
  - The robot hardware layer (robot_interface.py)

Requires: pip install groq
Requires: GROQ_API_KEY environment variable (free at console.groq.com)
"""

import json
import logging
import os
import re
from pathlib import Path

from groq import Groq

from memory import ChildMemory
import robot_interface

logger = logging.getLogger("teacher_lily.agent")

BASE_DIR = Path(__file__).parent
SYSTEM_PROMPT_PATH = BASE_DIR / "system_prompt.md"
TOOL_SCHEMA_PATH = BASE_DIR / "tool_schemas.json"

# llama-3.3-70b-versatile is Groq's flagship free-tier model -- strong
# reasoning quality, fast LPU inference, and it's the exact model this
# project's system prompt was originally engineered for.
# Free-tier alternative if you hit rate limits during heavy testing:
# "llama-3.1-8b-instant" (much higher daily request quota, slightly
# less nuanced pedagogical reasoning).
MODEL_NAME = "llama-3.3-70b-versatile"
MAX_TOKENS = 300  # keep responses short by design -- this is a voice agent for kids

# Defensive safety net: matches Llama's occasional pseudo tool-call leak
# pattern, e.g. "TOOL_CALL: <function=robot_gesture{"type": "think"}</function>"
# This should not happen after the system_prompt.md fix (no more literal
# SPEECH:/TOOL_CALL: templates in the few-shot examples), but hosted
# quantized models can still slip into it occasionally, so we guard here too.
_FUNC_LEAK_RE = re.compile(r"<function=(\w+)(\{.*?\})?", re.DOTALL)


def _sanitize_speech(raw_text: str) -> str:
    """
    Strips any literal 'SPEECH:'/'TOOL_CALL:' text the model might leak
    instead of using real function-calling, and best-effort recovers +
    executes the intended tool call anyway so the robot action still
    happens even when the model expressed it as text. Always returns
    clean text safe to hand to the TTS layer.
    """
    if "TOOL_CALL:" not in raw_text.upper() and "<function=" not in raw_text:
        return re.sub(r"^\s*SPEECH:\s*", "", raw_text, flags=re.IGNORECASE).strip()

    logger.warning(
        "Model leaked literal tool-call text instead of using function-calling. "
        "Sanitizing before speaking (see system_prompt.md TOOL-USE PROTOCOL)."
    )

    # Keep only the part before the leak as the actual spoken content
    speech_part = re.split(r"TOOL_CALL:|<function=", raw_text, maxsplit=1, flags=re.IGNORECASE)[0]
    speech_part = re.sub(r"^\s*SPEECH:\s*", "", speech_part, flags=re.IGNORECASE).strip()

    # Best-effort: recover and execute the intended tool call anyway
    match = _FUNC_LEAK_RE.search(raw_text)
    if match:
        tool_name = match.group(1).lower()
        arg_blob = match.group(2) or "{}"
        try:
            args = json.loads(arg_blob)
        except json.JSONDecodeError:
            args = {}
        if tool_name in robot_interface.TOOL_DISPATCH:
            logger.info(f"Recovered leaked tool call: {tool_name}({args})")
            robot_interface.execute_tool_call(tool_name, args)

    return speech_part


def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _load_tools() -> list:
    with open(TOOL_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["tools"]


class TeacherLilyAgent:
    def __init__(self, child_id: str, api_key: str = None):
        self.client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))
        self.system_prompt = _load_system_prompt()
        self.tools = _load_tools()
        self.memory = ChildMemory(child_id)
        self.history = []  # list of {"role": ..., "content": ...} for this session

    # ---- public API ----

    def start_session(self):
        self.memory.start_session_summary()
        self.history = [{"role": "system", "content": self.system_prompt}]

    def end_session(self):
        self.memory.end_session_summary()

    def handle_child_utterance(self, child_text: str, detected_emotion: dict = None) -> str:
        """
        Takes what the child said (already transcribed), runs it through
        Groq/Llama with tool access, executes any robot tool calls, and
        returns the final spoken text to hand to the TTS layer.

        `detected_emotion` (optional): a snapshot from vision_emotion.py,
        e.g. {"emotion": "sad", "confidence": 0.7, "face_detected": True}.
        Passed as a soft contextual signal, not a command -- the system
        prompt instructs Lily to let it inform tone, never to name it
        aloud ("I see you're sad") which would feel invasive to a child.
        """
        context_note = self.memory.as_context_string()

        emotion_note = ""
        if detected_emotion and detected_emotion.get("face_detected") and detected_emotion.get("confidence", 0) >= 0.4:
            emotion_note = (
                f" [Visual signal: the student's face currently reads as "
                f"'{detected_emotion['emotion']}' (confidence {detected_emotion['confidence']}). "
                f"Let this inform your tone subtly -- do not mention detecting it.]"
            )

        # Inject memory context alongside the child's utterance so the
        # model can personalize without it living permanently in the
        # (cacheable) system prompt.
        user_content = (
            f"[Context about this child: {context_note}]{emotion_note}\n\n"
            f"Child said: \"{child_text}\""
        )
        self.history.append({"role": "user", "content": user_content})

        speech_out = self._run_turn()
        return speech_out

    # ---- internals ----

    def _run_turn(self) -> str:
        """
        Runs one full turn, including the tool-use loop: the model may
        respond with one or more tool_calls, which we execute via
        robot_interface, feed the results back, and let it produce its
        final spoken text.
        """
        speech_chunks = []

        for _ in range(4):  # hard cap to avoid infinite tool loops
            response = self.client.chat.completions.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                tools=self.tools,
                messages=self.history,
            )

            message = response.choices[0].message
            self.history.append(message.model_dump(exclude_none=True))

            if message.content and message.content.strip():
                speech_chunks.append(_sanitize_speech(message.content))

            tool_calls = message.tool_calls or []
            if not tool_calls:
                break  # done -- no more tools requested, we have our final speech

            for tool_call in tool_calls:
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                result = robot_interface.execute_tool_call(tool_call.function.name, tool_args)

                self.history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

        return " ".join(speech_chunks).strip()
