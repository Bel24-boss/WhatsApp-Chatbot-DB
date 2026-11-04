import time
import threading
import logging

logger = logging.getLogger("cynex.deduplication")


class MessageDeduplicator:
    """
    In-memory message deduplication store with Time-To-Live (TTL).
    Prevents re-processing incoming WhatsApp messages if Meta re-delivers them.
    """

    def __init__(self, ttl_seconds: int = 900, max_entries: int = 10000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._seen_messages: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_duplicate(self, message_id: str) -> bool:
        """
        Check if a message ID has already been processed within the TTL window.
        If not seen, records the message ID and returns False.
        If already seen, returns True.
        """
        if not message_id:
            return False

        now = time.time()

        with self._lock:
            # Clean up expired items periodically if dict grows large
            if len(self._seen_messages) > self.max_entries:
                self._purge_expired(now)

            if message_id in self._seen_messages:
                last_seen = self._seen_messages[message_id]
                if now - last_seen < self.ttl_seconds:
                    masked_id = f"***{message_id[-4:]}" if len(message_id) > 4 else "***"
                    logger.info("Duplicate message detected and skipped: %s", masked_id)
                    return True

            # Register message with current timestamp
            self._seen_messages[message_id] = now
            return False

    def _purge_expired(self, current_time: float) -> None:
        """Remove entries older than the TTL."""
        expired_keys = [
            mid
            for mid, timestamp in self._seen_messages.items()
            if (current_time - timestamp) >= self.ttl_seconds
        ]
        for mid in expired_keys:
            del self._seen_messages[mid]
        logger.debug("Purged %d expired message IDs from deduplication cache", len(expired_keys))

    def clear(self) -> None:
        """Clear all stored message IDs (mainly for testing)."""
        with self._lock:
            self._seen_messages.clear()
