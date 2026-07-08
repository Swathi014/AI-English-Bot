"""
robot_face.py
-------------
A simple, expressive, vector-drawn robot face for Teacher Lily, rendered
on a Tkinter Canvas -- no image assets needed, so it has zero extra
dependencies and is trivial to re-theme (just change the color constants).

Designed to feel alive and kid-friendly:
- Expression changes based on gestures/emotions the LLM triggers
  (celebrate, encourage, think, wave, happy, curious, proud, gentle)
- A simple mouth-animation loop while Lily is speaking, so the face
  looks like it's actually talking rather than sitting static
- A gentle idle "blink" every few seconds so it doesn't look frozen
  when nothing else is happening
"""

import random
import tkinter as tk

# ---- Visual theme ----
FACE_BG = "#1e1e1e"
HEAD_COLOR = "#4a6fa5"
HEAD_OUTLINE = "#7ea3d1"
EYE_COLOR = "#ffffff"
PUPIL_COLOR = "#1e1e1e"
MOUTH_COLOR = "#ffffff"
CHEEK_COLOR = "#ff9eb5"

# ---- Expression definitions ----
# Each expression controls: eye shape ('round','happy_arc','wide','sleepy','wink'),
# mouth shape ('smile','open_smile','flat','o','small_smile'), and whether cheeks show.
EXPRESSIONS = {
    "neutral":   {"eyes": "round",      "mouth": "small_smile", "cheeks": False},
    "happy":     {"eyes": "happy_arc",  "mouth": "smile",       "cheeks": True},
    "celebrate": {"eyes": "happy_arc",  "mouth": "open_smile",  "cheeks": True},
    "proud":     {"eyes": "happy_arc",  "mouth": "smile",       "cheeks": True},
    "curious":   {"eyes": "wide",       "mouth": "o",           "cheeks": False},
    "think":     {"eyes": "sleepy",     "mouth": "flat",        "cheeks": False},
    "encourage": {"eyes": "round",      "mouth": "small_smile", "cheeks": False},
    "gentle":    {"eyes": "sleepy",     "mouth": "small_smile", "cheeks": False},
    "wave":      {"eyes": "happy_arc",  "mouth": "smile",       "cheeks": True},
    "nod":       {"eyes": "round",      "mouth": "small_smile", "cheeks": False},
}

BLINK_INTERVAL_MS = 4000
TALK_FRAME_MS = 150


class RobotFace(tk.Canvas):
    def __init__(self, parent, size: int = 260, **kwargs):
        super().__init__(parent, width=size, height=size, bg=FACE_BG,
                          highlightthickness=0, **kwargs)
        self.size = size
        self.cx = size / 2
        self.cy = size / 2

        self._current_expression = "neutral"
        self._is_talking = False
        self._talk_frame = 0
        self._blinking = False

        self._draw()
        self.after(BLINK_INTERVAL_MS, self._blink_cycle)

    # ---- public API ----

    def set_expression(self, name: str):
        """name should be a gesture type or emotion string -- unknown
        names fall back to 'neutral' rather than raising, since this
        should never crash a live session over an unexpected value."""
        self._current_expression = name if name in EXPRESSIONS else "neutral"
        self._draw()

    def start_talking(self):
        self._is_talking = True
        self._talk_loop()

    def stop_talking(self):
        self._is_talking = False
        self._draw()

    # ---- internals ----

    def _blink_cycle(self):
        if not self._is_talking:
            self._blinking = True
            self._draw()
            self.after(120, self._end_blink)
        self.after(BLINK_INTERVAL_MS + random.randint(-500, 800), self._blink_cycle)

    def _end_blink(self):
        self._blinking = False
        self._draw()

    def _talk_loop(self):
        if not self._is_talking:
            return
        self._talk_frame = (self._talk_frame + 1) % 2
        self._draw()
        self.after(TALK_FRAME_MS, self._talk_loop)

    def _draw(self):
        self.delete("all")
        spec = EXPRESSIONS[self._current_expression]

        # Head
        pad = self.size * 0.08
        self.create_oval(pad, pad, self.size - pad, self.size - pad,
                          fill=HEAD_COLOR, outline=HEAD_OUTLINE, width=4)

        eye_y = self.cy - self.size * 0.08
        eye_dx = self.size * 0.16
        eye_w = self.size * 0.11
        eye_h = self.size * 0.14

        if self._blinking:
            self._draw_blink_eyes(eye_y, eye_dx, eye_w)
        else:
            self._draw_eyes(spec["eyes"], eye_y, eye_dx, eye_w, eye_h)

        if spec["cheeks"]:
            self._draw_cheeks(eye_y)

        mouth_y = self.cy + self.size * 0.18
        self._draw_mouth(spec["mouth"], mouth_y)

    def _draw_eyes(self, style, y, dx, w, h):
        for sign in (-1, 1):
            x = self.cx + sign * dx
            if style == "round":
                self.create_oval(x - w/2, y - h/2, x + w/2, y + h/2, fill=EYE_COLOR, outline="")
                self.create_oval(x - w/5, y - h/5, x + w/5, y + h/5, fill=PUPIL_COLOR, outline="")
            elif style == "happy_arc":
                self.create_arc(x - w/2, y - h/2, x + w/2, y + h/2,
                                 start=0, extent=180, style=tk.CHORD, fill=EYE_COLOR, outline="")
            elif style == "wide":
                big = w * 1.25
                self.create_oval(x - big/2, y - h*0.7, x + big/2, y + h*0.7, fill=EYE_COLOR, outline="")
                self.create_oval(x - big/6, y - h*0.25, x + big/6, y + h*0.25, fill=PUPIL_COLOR, outline="")
            elif style == "sleepy":
                self.create_line(x - w/2, y, x + w/2, y - h*0.15, fill=EYE_COLOR, width=5, capstyle=tk.ROUND)
            elif style == "wink":
                if sign == -1:
                    self.create_line(x - w/2, y, x + w/2, y, fill=EYE_COLOR, width=5, capstyle=tk.ROUND)
                else:
                    self.create_oval(x - w/2, y - h/2, x + w/2, y + h/2, fill=EYE_COLOR, outline="")
                    self.create_oval(x - w/5, y - h/5, x + w/5, y + h/5, fill=PUPIL_COLOR, outline="")

    def _draw_blink_eyes(self, y, dx, w):
        for sign in (-1, 1):
            x = self.cx + sign * dx
            self.create_line(x - w/2, y, x + w/2, y, fill=EYE_COLOR, width=5, capstyle=tk.ROUND)

    def _draw_cheeks(self, eye_y):
        r = self.size * 0.045
        cheek_y = eye_y + self.size * 0.10
        for sign in (-1, 1):
            x = self.cx + sign * self.size * 0.28
            self.create_oval(x - r, cheek_y - r, x + r, cheek_y + r, fill=CHEEK_COLOR, outline="")

    def _draw_mouth(self, style, y):
        w = self.size * 0.22
        h = self.size * 0.10

        if self._is_talking:
            # Alternate between two open-mouth heights for a simple talk animation
            talk_h = h * (0.5 if self._talk_frame == 0 else 1.0)
            self.create_oval(self.cx - w/2, y - talk_h/2, self.cx + w/2, y + talk_h/2,
                              fill=MOUTH_COLOR, outline="")
            return

        if style == "smile":
            self.create_arc(self.cx - w/2, y - h/2, self.cx + w/2, y + h,
                             start=200, extent=140, style=tk.ARC, outline=MOUTH_COLOR, width=5)
        elif style == "open_smile":
            self.create_arc(self.cx - w/2, y - h/2, self.cx + w/2, y + h*1.4,
                             start=200, extent=140, style=tk.CHORD, fill=MOUTH_COLOR, outline="")
        elif style == "small_smile":
            self.create_arc(self.cx - w/3, y - h/3, self.cx + w/3, y + h/2,
                             start=200, extent=140, style=tk.ARC, outline=MOUTH_COLOR, width=4)
        elif style == "flat":
            self.create_line(self.cx - w/3, y, self.cx + w/3, y, fill=MOUTH_COLOR, width=4, capstyle=tk.ROUND)
        elif style == "o":
            r = h * 0.5
            self.create_oval(self.cx - r, y - r, self.cx + r, y + r, fill=MOUTH_COLOR, outline="")
