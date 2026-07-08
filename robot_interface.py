"""
robot_interface.py
-------------------
Hardware abstraction layer between Teacher Lily's LLM tool calls and
your physical robot / humanoid stack.

This module deliberately knows NOTHING about the LLM. It just exposes
three plain Python functions matching the tool schema in
`tool_schemas.json`. Wire the bodies of these functions to your actual
robot SDK (motor controllers, servo driver, whatever your humanoid
project already uses for `robot_move` / `robot_gesture` in your
existing integration bridge).

If no physical robot is connected, everything falls back to console
logging + optional simulated delays, so you can develop and test the
conversational loop before hardware is attached.
"""

import logging
import time

logger = logging.getLogger("teacher_lily.robot")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

# Set this to True once your real robot SDK is wired in below.
HARDWARE_CONNECTED = False

# TODO: import your real robot SDK here, e.g.:
# from evolve_robotics.motor_controller import MotorController
# from evolve_robotics.gesture_player import GesturePlayer
# robot = MotorController()
# gestures = GesturePlayer()


VALID_GESTURES = {"celebrate", "nod", "think", "wave", "encourage"}
VALID_DIRECTIONS = {"forward", "backward", "left", "right"}
VALID_EMOTIONS = {"happy", "curious", "proud", "gentle"}

# Optional hook so a UI (e.g. the on-screen robot face) can react live to
# every gesture/emotion call, without robot_interface needing to know
# anything about Tkinter or the UI's internals. main.py wires this up.
_ui_hook = None


def set_ui_hook(fn):
    """fn(kind: str, value: str) is called on every successful gesture/emotion.
    kind is 'gesture' or 'emotion'; value is the type/emotion string."""
    global _ui_hook
    _ui_hook = fn


def robot_gesture(type: str) -> dict:
    """Play a physical gesture on the robot."""
    if type not in VALID_GESTURES:
        return {"status": "error", "message": f"Unknown gesture '{type}'"}

    logger.info(f"GESTURE -> {type}")

    if HARDWARE_CONNECTED:
        # TODO: replace with real call, e.g. gestures.play(type)
        pass
    else:
        time.sleep(0.1)  # simulate action latency

    if _ui_hook:
        _ui_hook("gesture", type)

    return {"status": "ok", "gesture": type}


def robot_move(direction: str, distance: float = 0.3) -> dict:
    """Move the robot base a short distance in a direction."""
    if direction not in VALID_DIRECTIONS:
        return {"status": "error", "message": f"Unknown direction '{direction}'"}

    distance = max(0.1, min(2.0, float(distance)))  # clamp for classroom safety
    logger.info(f"MOVE -> {direction} ({distance}m)")

    if HARDWARE_CONNECTED:
        # TODO: replace with real call, e.g. robot.move(direction, distance)
        pass
    else:
        time.sleep(0.1)

    return {"status": "ok", "direction": direction, "distance": distance}


def robot_speak_emotion(emotion: str) -> dict:
    """Set the robot's facial/voice emotion display."""
    if emotion not in VALID_EMOTIONS:
        return {"status": "error", "message": f"Unknown emotion '{emotion}'"}

    logger.info(f"EMOTION -> {emotion}")

    if HARDWARE_CONNECTED:
        # TODO: replace with real call, e.g. robot.set_face(emotion)
        pass

    if _ui_hook:
        _ui_hook("emotion", emotion)

    return {"status": "ok", "emotion": emotion}


# Dispatch table used by agent.py to call the right function by name
TOOL_DISPATCH = {
    "robot_gesture": robot_gesture,
    "robot_move": robot_move,
    "robot_speak_emotion": robot_speak_emotion,
}


def execute_tool_call(name: str, tool_input: dict) -> dict:
    """Look up and execute a tool call by name, matching Anthropic's tool_use format."""
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        logger.warning(f"Unknown tool requested: {name}")
        return {"status": "error", "message": f"No such tool: {name}"}
    try:
        return fn(**tool_input)
    except TypeError as e:
        logger.warning(f"Bad arguments for {name}: {tool_input} ({e})")
        return {"status": "error", "message": str(e)}
