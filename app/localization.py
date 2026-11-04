import json
from pathlib import Path
from typing import Any


SUPPORTED_LANGUAGES = {"en": "English"}


class Localizer:
    """Loads the replaceable English UI text catalog."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._catalog: dict[str, dict[str, Any]] = {}
        self._mtime_ns: int | None = None
        self._refresh()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _refresh(self) -> None:
        try:
            modified = self.path.stat().st_mtime_ns
        except OSError:
            return
        if modified == self._mtime_ns:
            return
        loaded = self._load()
        if loaded:
            self._catalog = loaded
        self._mtime_ns = modified

    def text(self, key: str, locale: str = "en", **values: Any) -> str:
        self._refresh()
        language = locale if locale in SUPPORTED_LANGUAGES else "en"
        template = self._catalog.get(language, {}).get(key)
        if template is None:
            template = self._catalog.get("en", {}).get(key, key)
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template

    def canonical_command(self, value: str, locale: str = "en") -> str:
        """Maps configurable English aliases to workflow commands."""
        self._refresh()
        normalized = " ".join(value.casefold().strip().split())
        commands = self._catalog.get("en", {}).get("_commands", {})
        if isinstance(commands, dict):
            for canonical, aliases in commands.items():
                if isinstance(aliases, list) and normalized in {
                    " ".join(str(alias).casefold().strip().split()) for alias in aliases
                }:
                    return str(canonical)
        return normalized
