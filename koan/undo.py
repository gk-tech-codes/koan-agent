"""Undo system — automatic backups before file writes.

Enabled with --undo flag. Every write_file/edit_file creates a backup.
/undo reverts the last file change.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Optional

from koan.log import get_logger

log = get_logger("undo")

_MAX_HISTORY = 20


class UndoManager:
    """Tracks file changes and supports undo."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._history: list[dict] = []
        self._backup_dir = Path.home() / ".koan" / "undo"
        if enabled:
            self._backup_dir.mkdir(parents=True, exist_ok=True)

    def backup(self, path: str) -> None:
        """Backup a file before modification."""
        if not self.enabled:
            return
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            self._history.append({
                "action": "created",
                "path": str(p),
                "backup": None,
                "time": time.time(),
            })
            return

        backup_name = f"{p.name}.{int(time.time() * 1000)}.bak"
        backup_path = self._backup_dir / backup_name
        shutil.copy2(p, backup_path)

        self._history.append({
            "action": "modified",
            "path": str(p),
            "backup": str(backup_path),
            "time": time.time(),
        })

        if len(self._history) > _MAX_HISTORY:
            old = self._history.pop(0)
            if old.get("backup"):
                Path(old["backup"]).unlink(missing_ok=True)

        log.debug("Backed up %s → %s", path, backup_path)

    def undo(self) -> Optional[str]:
        """Undo the last file change. Returns description or None."""
        if not self.enabled:
            return "Undo not enabled. Start with --undo flag."
        if not self._history:
            return "Nothing to undo."

        entry = self._history.pop()
        p = Path(entry["path"])

        if entry["action"] == "created":
            if p.is_file():
                p.unlink()
                log.info("Undo: deleted %s (was newly created)", p)
                return f"Deleted {p.name} (was newly created)"
        elif entry["action"] == "modified" and entry["backup"]:
            backup = Path(entry["backup"])
            if backup.is_file():
                shutil.copy2(backup, p)
                backup.unlink()
                log.info("Undo: restored %s from backup", p)
                return f"Restored {p.name} to previous version"

        return "Undo failed — backup not found."

    def history(self) -> list[dict]:
        return [
            {"action": e["action"], "path": Path(e["path"]).name, "ago": f"{int(time.time() - e['time'])}s ago"}
            for e in reversed(self._history)
        ]


# Global instance — set by CLI based on --undo flag
undo_manager = UndoManager(enabled=False)
