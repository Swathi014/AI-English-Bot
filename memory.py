"""
memory.py
---------
Simple JSON-backed memory store for Teacher Lily.

Tracks per-child facts (likes, name), session history, and recurring
grammar mistakes so the agent can personalize lessons and reference
past progress ("Remember how we learned 'went' last time?").

This is intentionally file-based (no DB dependency) so it drops
straight into a Raspberry Pi / Windows robot environment without
extra setup. Swap `_load`/`_save` for a real DB later if needed.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROFILES_DIR = Path(__file__).parent / "child_profiles"
PROFILES_DIR.mkdir(exist_ok=True)


def _profile_path(child_id: str) -> Path:
    safe_id = "".join(c for c in child_id if c.isalnum() or c in ("-", "_")) or "default"
    return PROFILES_DIR / f"{safe_id}.json"


DEFAULT_PROFILE = {
    "child_id": "",
    "name": "",
    "age": None,
    "likes": [],           # e.g. ["biryani", "dinosaurs"]
    "mistake_history": {},  # {"past_tense_went": {"count": 2, "last_seen": "..."}}
    "successes": {},        # same shape, for concepts mastered
    "sessions": []           # list of session summary dicts
}


class ChildMemory:
    def __init__(self, child_id: str):
        self.child_id = child_id
        self.path = _profile_path(child_id)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        profile = dict(DEFAULT_PROFILE)
        profile["child_id"] = self.child_id
        return profile

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    # ---- basic profile fields ----

    def set_name(self, name: str):
        self.data["name"] = name
        self.save()

    def add_like(self, thing: str):
        if thing and thing not in self.data["likes"]:
            self.data["likes"].append(thing)
            self.save()

    # ---- mistake / success tracking ----

    def log_mistake(self, concept: str):
        entry = self.data["mistake_history"].setdefault(
            concept, {"count": 0, "last_seen": None}
        )
        entry["count"] += 1
        entry["last_seen"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def log_success(self, concept: str):
        entry = self.data["successes"].setdefault(
            concept, {"count": 0, "last_seen": None}
        )
        entry["count"] += 1
        entry["last_seen"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def mistake_count(self, concept: str) -> int:
        return self.data["mistake_history"].get(concept, {}).get("count", 0)

    def success_count(self, concept: str) -> int:
        return self.data["successes"].get(concept, {}).get("count", 0)

    # ---- session logging ----

    def start_session_summary(self):
        self._current_session = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "topics": [],
        }

    def log_topic(self, topic: str):
        if hasattr(self, "_current_session"):
            self._current_session["topics"].append(topic)

    def end_session_summary(self):
        if hasattr(self, "_current_session"):
            self._current_session["ended_at"] = datetime.now(timezone.utc).isoformat()
            self.data["sessions"].append(self._current_session)
            self.save()
            del self._current_session

    # ---- context injection for the LLM ----

    def as_context_string(self) -> str:
        """
        Produces a short natural-language memory summary to inject into
        the system/user context so the LLM can personalize the lesson.
        Kept deliberately compact -- this is not a full transcript dump.
        """
        parts = []
        if self.data.get("name"):
            parts.append(f"Child's name: {self.data['name']}.")
        if self.data.get("age"):
            parts.append(f"Age: {self.data['age']}.")
        if self.data.get("likes"):
            parts.append(f"Likes: {', '.join(self.data['likes'])}.")

        recurring = [
            concept for concept, info in self.data["mistake_history"].items()
            if info["count"] >= 2
        ]
        if recurring:
            parts.append(f"Recurring mistakes to watch for: {', '.join(recurring)}.")

        mastered = [
            concept for concept, info in self.data["successes"].items()
            if info["count"] >= 3
        ]
        if mastered:
            parts.append(f"Concepts mastered (can increase difficulty): {', '.join(mastered)}.")

        return " ".join(parts) if parts else "No prior history for this child yet."
