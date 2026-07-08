# Teacher Lily — AI English Teacher for Kids (5–10)

A voice-based educational agent that assesses, corrects, teaches, and practices
English with a child, and can trigger physical robot actions (`robot_move`,
`robot_gesture`, `robot_speak_emotion`) via tool-calling.

**Runs on Groq's free cloud API** — no credit card, no paid tier, no local GPU
required. Groq hosts Llama 3.3 70B (the exact model this project's system
prompt was engineered for) on their own hardware and serves it over the cloud
for free, gated only by generous rate limits.

## Project Structure

```
teacher_lily/
├── main.py               # Entry point: listen -> think -> speak loop
├── agent.py               # Groq (Llama 3.3) API wrapper + tool-use loop
├── memory.py              # Per-child JSON memory (likes, mistakes, sessions)
├── robot_interface.py     # Hardware abstraction layer -- wire your robot SDK here
├── speech_io.py            # Whisper STT + gTTS/pygame TTS
├── vision_emotion.py        # Background face + emotion detection thread
├── ui.py                    # Live transcript window (Tkinter)
├── system_prompt.md        # Lily's full behavioral spec (persona, workflow, rules)
├── tool_schemas.json       # OpenAI-compatible tool definitions (Groq's format)
├── requirements.txt
├── .env.example
└── child_profiles/         # Auto-created; one JSON file per child
```

## Live UI

Running `python main.py` now opens a small window showing the live transcript
(what Whisper heard, what Lily said) and the currently detected emotion, so
you can see what's happening without relying on audio alone during dev/debug.

- `python main.py --child aanya` → voice mode **with the UI window** (default)
- `python main.py --no-ui --child aanya` → voice mode, console-only (old behavior)
- `python main.py --text --child aanya` → typed text mode, console-only, no mic/UI

Click "Stop Session" or close the window to end cleanly. The voice loop runs
in a background thread; the UI owns the main thread (a Tkinter requirement).

## Windows Setup Gotchas

**ffmpeg not on PATH** → Whisper transcription silently fails with
`[WinError 2] The system cannot find the file specified`. Fix:
```powershell
choco install ffmpeg
```
Then **restart your terminal/IDE** so the updated PATH takes effect.
`main.py` now checks for this upfront in voice mode and exits with a clear
message instead of failing on every turn.

**`PermissionError` on `lily_output.mp3`** → this was a real bug (fixed):
pygame kept a Windows file-handle lock on a fixed temp filename between
turns. `speech_io.py` now uses a unique filename per utterance and
explicitly unloads the track after playback.

## Setup (all free)

1. **Get a free Groq API key** — no credit card needed:
   - Go to https://console.groq.com/keys
   - Sign up (email or Google login)
   - Click "Create API Key", copy it

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   Note: `openai-whisper` requires `ffmpeg` on your system PATH.
   - Windows: `choco install ffmpeg` or download from ffmpeg.org
   - The speech stack matches your existing KidRails pipeline (Whisper + gTTS +
     pygame), so it should slot into your current environment cleanly.

3. **Add your key**
   ```bash
   cp .env.example .env
   # then edit .env and paste your GROQ_API_KEY (starts with gsk_...)
   ```

4. **Run in text mode first (no mic/speaker needed)** — fastest way to sanity-check
   the conversation loop and tool calls:
   ```bash
   python main.py --text --child aanya
   ```

5. **Run in full voice mode**, once text mode is confirmed working:
   ```bash
   python main.py --child aanya
   ```

## Free-Tier Limits (Groq, as of mid-2026)

| Model | Requests/min | Requests/day | Notes |
|---|---|---|---|
| `llama-3.3-70b-versatile` (default) | 30 | 1,000 | Best reasoning quality; used for lesson logic |
| `llama-3.1-8b-instant` (fallback) | higher | 14,400 | Swap to this in `agent.py` if you're doing heavy dev/testing and hit the 70B daily cap |

1,000 requests/day is roughly 1,000 conversation turns — more than enough for
real tutoring sessions with one or a handful of children. If you're iterating
rapidly during development and hit the cap, switch `MODEL_NAME` in `agent.py`
to `"llama-3.1-8b-instant"` temporarily (much higher daily quota, slightly
less nuanced pedagogical reasoning), then switch back for real sessions.

No credit card is required at any point on the free tier. Rate limits reset
daily (midnight UTC).

## Wiring Up Your Physical Robot

Open `robot_interface.py`. Each function (`robot_move`, `robot_gesture`,
`robot_speak_emotion`) currently just logs to console. Replace the `# TODO`
sections with calls into your existing humanoid robot integration bridge
(the same one used by your task-assistant dispatcher / emotion-response
system). Set `HARDWARE_CONNECTED = True` once wired.

No other file needs to change — `agent.py` calls `robot_interface.execute_tool_call()`
generically, so your hardware layer stays fully decoupled from the LLM logic.

## How the Tool-Calling Loop Works

1. Child speaks -> Whisper transcribes -> `agent.handle_child_utterance()`.
2. Llama 3.3 (via Groq) receives the system prompt + child's utterance + memory
   context, and may respond with **text** (what Lily says) and/or **tool_calls**
   (robot actions), per the rules in `system_prompt.md`.
3. `agent.py` executes any tool calls against `robot_interface.py`, sends the
   results back to the model as `role: "tool"` messages, and collects the
   final spoken text.
4. `speech_io.speak()` plays it aloud.

This uses native OpenAI-compatible function calling (which Groq implements
directly), not text parsing — more reliable than having the model emit a
`TOOL_CALL: ...` string that you then regex out.

## Memory / Personalization

`memory.py` stores one JSON file per child under `child_profiles/`, tracking:
- Name, age, likes (for personalized example sentences)
- Recurring grammar mistakes (referenced when they resurface)
- Mastered concepts (used to bump difficulty over time)
- Session history

This is injected into each turn as a compact context string — not dumped
into the system prompt — so token usage (and therefore rate-limit consumption)
stays low per request.

## Tuning / Iteration

If Lily is too chatty or under-uses the robot:
- Tighten `MAX_TOKENS` in `agent.py` (currently 300).
- Edit `system_prompt.md`'s Constraints section to be stricter
  (e.g., "max 1 sentence" instead of "max 2 sentences").
- Add a stronger line under Task Workflow prioritizing Step 4 (Practice)
  over Step 3 (Teach).

If robot actions fire too often or too rarely, adjust the Trigger Rules
in the `### TOOL-USE PROTOCOL ###` section of `system_prompt.md` — the model
follows these rules directly when deciding whether to emit a tool call.

## Seeing the Student: Face + Emotion Detection

`vision_emotion.py` runs a background thread that:
1. Reads the default camera continuously (independent of the voice loop, so
   nothing blocks waiting on frames).
2. Detects the largest face in view (the student in front of the robot) using
   OpenCV's bundled Haar cascade — no extra downloads.
3. Classifies emotion via a pluggable Keras model (currently wired to your
   trained 5-class model: angry, happy, neutral, sad, surprise).
4. Applies **temporal smoothing** (votes over the last 8 predictions),
   **confidence thresholding** (ignores single low-confidence frames), and a
   **cooldown** (4s minimum between state changes) — the same pattern as your
   existing Features 5 & 6 pipeline, so results don't flicker turn-to-turn.

Before each conversation turn, `main.py` reads the current snapshot and passes
it into `agent.handle_child_utterance(..., detected_emotion=...)`, which
injects it as a soft contextual hint in the prompt (see the `### STUDENT
EMOTION AWARENESS ###` section of `system_prompt.md`). Lily uses it to adjust
tone and pacing — she never says "I see you're sad" out loud, since naming a
detected emotion at a child feels invasive rather than caring.

**Your model is already wired in:**
```
LILY_EMOTION_MODEL_PATH=D:/EVOLVE ROBOTICS/Emotion Detection using Opencv/Multi-person-emotion-detection/emotion_detection_model.keras
```
`vision_emotion.py` introspects the model's actual `input_shape` at load time
(size + grayscale/RGB) rather than assuming a fixed shape, so it adapts to
your model automatically. `EMOTION_LABELS` is set to `["angry", "happy",
"neutral", "sad", "surprise"]`, matching your training folder order
(Keras sorts class folders alphabetically, confirmed from your dataset
structure). Run `python test_emotion_model.py` first to verify the model
loads correctly and see live predictions overlaid on your webcam feed
before running the full voice pipeline.

**No model file? No camera?** The system degrades gracefully — it logs a
warning and reports a `neutral / no-signal` state rather than crashing, so
the rest of the app (conversation, tools, memory) keeps working while you
finish training or wiring the real model.

## Model Choice

Default is `llama-3.3-70b-versatile` on Groq (free, cloud-hosted, good
reasoning quality, fast LPU inference — this is also the exact model your
original system prompt was engineered for). If you outgrow the free tier's
1,000 requests/day, Groq's paid tier is also inexpensive (~$0.59/$0.79 per
million input/output tokens) — but for a single-classroom or home-use tutor,
the free tier should comfortably cover real usage.
