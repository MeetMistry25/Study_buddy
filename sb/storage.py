"""Tiny JSON file store. One file per collection under the data directory."""
import json
import os
import tempfile
import threading


class Store:
    def __init__(self, data_dir):
        self.dir = data_dir
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.RLock()

    def path(self, name):
        return os.path.join(self.dir, name + ".json")

    def load(self, name, default=None):
        with self.lock:
            try:
                with open(self.path(name), encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                return default

    def save(self, name, data):
        with self.lock:
            fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path(name))
