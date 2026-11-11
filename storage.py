"""Хранилище каналов-источников в channels.json."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

FILE = Path(__file__).with_name("channels.json")


class ChannelStore:
    def __init__(self, path: Path = FILE):
        self.path = path
        self._mtime = None
        self._data = {"channels": []}
        self.reload()

    def reload(self):
        if not self.path.exists():
            self._data, self._mtime = {"channels": []}, None
            return
        self._data = json.loads(self.path.read_text(encoding="utf-8"))
        self._mtime = self.path.stat().st_mtime

    def refresh_if_changed(self):
        """Подхватывает правки, сделанные из другого терминала (`main.py add`) без перезапуска."""
        m = self.path.stat().st_mtime if self.path.exists() else None
        if m != self._mtime:
            self.reload()

    def _save(self):
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self._mtime = self.path.stat().st_mtime

    @property
    def channels(self):
        return self._data["channels"]

    def get(self, chat_id):
        return next((c for c in self.channels if c["id"] == chat_id), None)

    def add(self, chat_id, title, username):
        if self.get(chat_id):
            return False
        self._data["channels"].append(
            {
                "id": chat_id,
                "title": title,
                "username": username,
                "added_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._save()
        return True

    def remove(self, chat_id):
        before = len(self.channels)
        self._data["channels"] = [c for c in self.channels if c["id"] != chat_id]
        if len(self.channels) != before:
            self._save()
            return True
        return False
