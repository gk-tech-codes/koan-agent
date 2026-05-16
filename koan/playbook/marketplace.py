"""Playbook Marketplace — install, share, and discover community playbooks.

Usage:
  koan playbooks install deploy-aws
  koan playbooks publish my-playbook
  koan playbooks search "deploy"
  koan playbooks list --installed

Playbooks are stored as JSONL files. The marketplace is a GitHub repo
with an index.json listing all available playbooks.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import httpx

from koan.log import get_logger
from koan.playbook.store import Playbook, PlaybookStore

log = get_logger("marketplace")

# Default marketplace registry (GitHub raw URL)
DEFAULT_REGISTRY = "https://raw.githubusercontent.com/gk-tech-codes/koan-playbooks/main"
INDEX_FILE = "index.json"


class PlaybookMarketplace:
    """Manages community playbook installation and discovery."""

    def __init__(self, store: PlaybookStore, registry_url: str = DEFAULT_REGISTRY):
        self._store = store
        self._registry = registry_url
        self._cache_dir = Path.home() / ".koan" / "marketplace"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: str) -> list[dict]:
        """Search available playbooks in the registry."""
        index = self._fetch_index()
        if not index:
            return []
        query_lower = query.lower()
        return [
            p for p in index
            if query_lower in p.get("name", "").lower()
            or query_lower in p.get("description", "").lower()
            or any(query_lower in t.lower() for t in p.get("tags", []))
        ]

    def install(self, name: str) -> Optional[str]:
        """Install a playbook from the marketplace."""
        index = self._fetch_index()
        if not index:
            return "Cannot reach marketplace registry."

        # Find playbook in index
        entry = next((p for p in index if p["name"] == name), None)
        if not entry:
            return f"Playbook '{name}' not found. Use 'koan playbooks search' to find available playbooks."

        # Download playbook file
        url = f"{self._registry}/playbooks/{name}.json"
        try:
            r = httpx.get(url, timeout=10)
            if r.status_code != 200:
                return f"Failed to download '{name}': HTTP {r.status_code}"
            data = r.json()
        except Exception as exc:
            return f"Failed to download '{name}': {exc}"

        # Convert to Playbook and store
        playbook = Playbook(data)
        playbook.id = f"market_{name}"
        self._store.store(playbook)

        log.info("Installed playbook: %s (%d steps)", name, len(playbook.steps))
        return None  # success

    def publish(self, playbook_id: str) -> dict:
        """Export a playbook for publishing to the marketplace."""
        pb = self._store.get(playbook_id)
        if not pb:
            return {"error": f"Playbook '{playbook_id}' not found locally."}

        export = pb.to_dict()
        export["author"] = "community"
        export["version"] = "1.0.0"

        # Save to export directory
        export_path = self._cache_dir / f"{pb.name}.json"
        export_path.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "exported": str(export_path),
            "name": pb.name,
            "steps": len(pb.steps),
            "instructions": f"Submit a PR to the koan-playbooks repo with this file at playbooks/{pb.name}.json",
        }

    def list_available(self) -> list[dict]:
        """List all playbooks in the marketplace."""
        return self._fetch_index() or []

    def list_installed(self) -> list[dict]:
        """List locally installed marketplace playbooks."""
        return [
            {"id": p.id, "name": p.name, "steps": len(p.steps), "confidence": p.confidence, "times_used": p.times_used}
            for p in self._store.all()
            if p.id.startswith("market_")
        ]

    def _fetch_index(self) -> list[dict]:
        """Fetch the marketplace index."""
        try:
            r = httpx.get(f"{self._registry}/{INDEX_FILE}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("playbooks", [])
        except Exception as exc:
            log.warning("Cannot reach marketplace: %s", exc)

        # Try cached index
        cache_path = self._cache_dir / INDEX_FILE
        if cache_path.is_file():
            try:
                return json.loads(cache_path.read_text()).get("playbooks", [])
            except Exception:
                pass
        return []
