import json
import os
import threading


class EventStore:
    """
    Append-only store of completed incidents, persisted to JSONL so history
    survives restarts. Thread-safe.
    """
    def __init__(self, path="logs/events.jsonl", max_keep=500):
        self.path = path
        self.max_keep = max_keep
        self.lock = threading.Lock()
        self.events = []
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.events.append(json.loads(line))
                        except Exception:
                            pass
            self.events = self.events[-self.max_keep:]

    def add(self, event):
        with self.lock:
            self.events.append(event)
            self.events = self.events[-self.max_keep:]
            try:
                with open(self.path, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                print(f"[events] failed to persist: {e}")

    def list(self, limit=100):
        with self.lock:
            return list(reversed(self.events[-limit:]))  # newest first
