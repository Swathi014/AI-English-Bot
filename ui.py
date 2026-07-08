"""
ui.py
-----
The live session window for Teacher Lily: an animated robot face on the
left (reacts to gestures/emotions and animates while talking) and a
live transcript on the right (what Whisper heard, what Lily said).

Runs in the main thread (Tkinter requirement). The actual listen ->
think -> speak loop runs in a background thread (see main.py) and
pushes updates into a thread-safe queue that this window drains ~10x
a second.
"""

import queue
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime

from robot_face import RobotFace


class TeacherLilyUI:
    def __init__(self, on_stop=None):
        """
        `on_stop`: callback invoked when the user closes the window or
        clicks "Stop Session" -- main.py uses this to signal the
        background voice-loop thread to wind down cleanly.
        """
        self.root = tk.Tk()
        self.root.title("Teacher Lily -- Live Session")
        self.root.geometry("820x640")
        self.root.configure(bg="#1e1e1e")

        self._queue = queue.Queue()
        self._on_stop = on_stop

        self._build_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)
        self.root.after(100, self._drain_queue)

    def _build_widgets(self):
        header = tk.Label(
            self.root, text="🌟 Teacher Lily", font=("Segoe UI", 16, "bold"),
            bg="#1e1e1e", fg="#ffd166", pady=10,
        )
        header.pack(fill="x")

        body = tk.Frame(self.root, bg="#1e1e1e")
        body.pack(fill="both", expand=True, padx=10)

        # ---- Left: robot face ----
        left = tk.Frame(body, bg="#1e1e1e")
        left.pack(side="left", fill="y", padx=(0, 10))

        self.face = RobotFace(left, size=260)
        self.face.pack(pady=(0, 6))

        self.emotion_label = tk.Label(
            left, text="👀 Watching for the student's face...",
            font=("Segoe UI", 9), bg="#1e1e1e", fg="#8a8a8a", wraplength=260, justify="center",
        )
        self.emotion_label.pack()

        # ---- Right: transcript ----
        right = tk.Frame(body, bg="#1e1e1e")
        right.pack(side="left", fill="both", expand=True)

        self.log = scrolledtext.ScrolledText(
            right, wrap="word", font=("Segoe UI", 11),
            bg="#252526", fg="#e0e0e0", insertbackground="#e0e0e0",
            state="disabled", padx=10, pady=10, borderwidth=0,
        )
        self.log.pack(fill="both", expand=True)

        self.log.tag_config("child", foreground="#7ec8e3", font=("Segoe UI", 11, "bold"))
        self.log.tag_config("lily", foreground="#ffd166", font=("Segoe UI", 11, "bold"))
        self.log.tag_config("system", foreground="#8a8a8a", font=("Segoe UI", 9, "italic"))
        self.log.tag_config("body", foreground="#e0e0e0")

        # ---- Bottom: status bar ----
        status_bar = tk.Frame(self.root, bg="#1e1e1e")
        status_bar.pack(fill="x", padx=10, pady=10)

        self.status_label = tk.Label(
            status_bar, text="● Listening", font=("Segoe UI", 9),
            bg="#1e1e1e", fg="#6fcf97",
        )
        self.status_label.pack(side="left")

        stop_btn = tk.Button(
            status_bar, text="Stop Session", command=self._handle_close,
            bg="#3a3a3a", fg="#e0e0e0", relief="flat", padx=10, pady=4,
            activebackground="#4a4a4a", activeforeground="#e0e0e0",
        )
        stop_btn.pack(side="right")

    # ---- thread-safe public API -- call these from the worker thread ----

    def log_child(self, text: str):
        self._queue.put(("child", text))

    def log_lily(self, text: str):
        self._queue.put(("lily", text))

    def log_system(self, text: str):
        self._queue.put(("system", text))

    def set_emotion(self, emotion: str, confidence: float, face_detected: bool):
        self._queue.put(("emotion", (emotion, confidence, face_detected)))

    def set_status(self, text: str, color: str = "#6fcf97"):
        self._queue.put(("status", (text, color)))

    def set_face_expression(self, name: str):
        """Drives the robot face -- called from robot_interface's UI hook
        whenever a robot_gesture/robot_speak_emotion tool fires."""
        self._queue.put(("face_expression", name))

    def start_talking(self):
        self._queue.put(("talk_start", None))

    def stop_talking(self):
        self._queue.put(("talk_stop", None))

    # ---- internals (main thread only, driven by root.after) ----

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _handle_event(self, kind, payload):
        if kind == "child":
            self._append("Child", payload, "child")
        elif kind == "lily":
            self._append("Lily", payload, "lily")
        elif kind == "system":
            self._append("System", payload, "system")
        elif kind == "emotion":
            emotion, confidence, face_detected = payload
            if face_detected:
                self.emotion_label.config(text=f"👀 Reading: {emotion} ({confidence:.0%})")
            else:
                self.emotion_label.config(text="👀 No face detected")
        elif kind == "status":
            text, color = payload
            self.status_label.config(text=text, fg=color)
        elif kind == "face_expression":
            self.face.set_expression(payload)
        elif kind == "talk_start":
            self.face.start_talking()
        elif kind == "talk_stop":
            self.face.stop_talking()

    def _append(self, sender: str, text: str, tag: str):
        self.log.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.insert("end", f"[{timestamp}] {sender}: ", tag)
        self.log.insert("end", f"{text}\n\n", "body")
        self.log.config(state="disabled")
        self.log.see("end")

    def _handle_close(self):
        if self._on_stop:
            self._on_stop()
        self.root.after(300, self.root.destroy)

    def run(self):
        """Blocks the calling thread -- must be called from the main thread."""
        self.root.mainloop()
