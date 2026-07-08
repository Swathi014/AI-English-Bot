"""
ui.py
-----
A minimal live chat-log window for Teacher Lily, so you can SEE what
was heard (Whisper's transcription) and what Lily said, instead of
relying only on speakers + console logs while debugging.

Runs in the main thread (Tkinter requirement). The actual listen ->
think -> speak loop runs in a background thread (see main.py) and
pushes updates into a thread-safe queue that this window drains ~10x
a second.
"""

import queue
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime


class TeacherLilyUI:
    def __init__(self, on_stop=None):
        """
        `on_stop`: callback invoked when the user closes the window or
        clicks "Stop Session" -- main.py uses this to signal the
        background voice-loop thread to wind down cleanly.
        """
        self.root = tk.Tk()
        self.root.title("Teacher Lily -- Live Session")
        self.root.geometry("560x640")
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

        self.emotion_label = tk.Label(
            self.root, text="👀 Watching for the student's face...",
            font=("Segoe UI", 10), bg="#1e1e1e", fg="#8a8a8a",
        )
        self.emotion_label.pack(fill="x", pady=(0, 6))

        self.log = scrolledtext.ScrolledText(
            self.root, wrap="word", font=("Segoe UI", 11),
            bg="#252526", fg="#e0e0e0", insertbackground="#e0e0e0",
            state="disabled", padx=10, pady=10, borderwidth=0,
        )
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log.tag_config("child", foreground="#7ec8e3", font=("Segoe UI", 11, "bold"))
        self.log.tag_config("lily", foreground="#ffd166", font=("Segoe UI", 11, "bold"))
        self.log.tag_config("system", foreground="#8a8a8a", font=("Segoe UI", 9, "italic"))
        self.log.tag_config("body", foreground="#e0e0e0")

        status_bar = tk.Frame(self.root, bg="#1e1e1e")
        status_bar.pack(fill="x", padx=10, pady=(0, 10))

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
