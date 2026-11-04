import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class KnowledgeMatch:
    answer: str
    topic_id: str
    confidence: float


class ApprovedKnowledgeBase:
    """Retrieval-only public information engine; it never generates policy facts."""

    def __init__(self, path: str, threshold: float = 0.42):
        self.path = Path(path)
        self.threshold = threshold
        self._topics: list[dict[str, Any]] = []
        self._mtime_ns: int | None = None
        self._refresh()

    def _load(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        topics = payload.get("topics", []) if isinstance(payload, dict) else []
        return [item for item in topics if isinstance(item, dict) and item.get("approved") is True]

    def _refresh(self) -> None:
        try:
            modified = self.path.stat().st_mtime_ns
        except OSError:
            return
        if modified == self._mtime_ns:
            return
        loaded = self._load()
        if loaded:
            self._topics = loaded
        self._mtime_ns = modified

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))

    def answer(self, question: str, locale: str = "en") -> Optional[KnowledgeMatch]:
        self._refresh()
        query = self._normalize(question)
        if not query:
            return None
        query_tokens = set(query.split())
        best: tuple[float, Optional[dict[str, Any]]] = (0.0, None)
        for topic in self._topics:
            patterns = topic.get("patterns", {})
            candidates: list[str] = []
            if isinstance(patterns, dict):
                candidates.extend(patterns.get(locale, []) or [])
                if locale != "en":
                    candidates.extend(patterns.get("en", []) or [])
            for candidate in candidates:
                normalized = self._normalize(str(candidate))
                candidate_tokens = set(normalized.split())
                overlap = len(query_tokens & candidate_tokens) / max(1, len(query_tokens | candidate_tokens))
                sequence = SequenceMatcher(None, query, normalized).ratio()
                score = max(overlap, sequence * 0.72)
                if score > best[0]:
                    best = (score, topic)
        score, topic = best
        if topic is None or score < self.threshold:
            return None
        answers = topic.get("answers", {})
        answer = answers.get(locale) or answers.get("en") if isinstance(answers, dict) else None
        if not answer:
            return None
        return KnowledgeMatch(str(answer), str(topic.get("id", "unknown")), score)
