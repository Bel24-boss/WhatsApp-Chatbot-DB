import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("fidelity.whatsapp_client")


def mask_identifier(value: Optional[str]) -> str:
    if not value:
        return "<missing>"
    return f"***{value[-4:]}" if len(value) > 4 else "***"


class WhatsAppClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        version = self.settings.META_GRAPH_API_VERSION.strip()
        phone_id = self.settings.WHATSAPP_PHONE_NUMBER_ID.strip()
        return f"https://graph.facebook.com/{version}/{phone_id}/messages"

    @property
    def phone_number_url(self) -> str:
        version = self.settings.META_GRAPH_API_VERSION.strip()
        phone_id = self.settings.WHATSAPP_PHONE_NUMBER_ID.strip()
        return f"https://graph.facebook.com/{version}/{phone_id}"

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.WHATSAPP_ACCESS_TOKEN.strip()}",
            "Content-Type": "application/json",
        }

    async def get_connection_status(self) -> dict[str, Any]:
        """Validate Meta credentials without returning any secret values."""
        result: dict[str, Any] = {
            "credentials_present": self.settings.is_configured,
            "reachable": False,
            "authenticated": False,
            "phone_number_id_matches": False,
            "http_status": None,
            "display_phone_number": None,
            "verified_name": None,
            "quality_rating": None,
            "error_code": None,
            "error_subcode": None,
            "error_type": None,
        }
        if not self.settings.is_configured:
            return result

        try:
            async with httpx.AsyncClient(timeout=self.settings.API_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    self.phone_number_url,
                    params={"fields": "id,display_phone_number,verified_name,quality_rating"},
                    headers=self._get_headers(),
                )
            result["reachable"] = True
            result["http_status"] = response.status_code
            try:
                data = response.json()
            except ValueError:
                data = {}

            if response.status_code == 200:
                response_phone_id = str(data.get("id", ""))
                result.update(
                    {
                        "authenticated": True,
                        "phone_number_id_matches": response_phone_id
                        == self.settings.WHATSAPP_PHONE_NUMBER_ID.strip(),
                        "display_phone_number": mask_identifier(data.get("display_phone_number")),
                        "verified_name": data.get("verified_name"),
                        "quality_rating": data.get("quality_rating"),
                    }
                )
                return result

            error = data.get("error", {}) if isinstance(data, dict) else {}
            result.update(
                {
                    "error_code": error.get("code"),
                    "error_subcode": error.get("error_subcode"),
                    "error_type": error.get("type"),
                }
            )
            return result
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            result["error_type"] = type(exc).__name__
            return result
        except Exception as exc:
            logger.exception("Unexpected WhatsApp diagnostic error: %s", type(exc).__name__)
            result["error_type"] = type(exc).__name__
            return result

    async def _post_payload(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.settings.is_configured:
            logger.warning("WhatsApp credentials are not fully configured; outbound message skipped")
            return None

        for attempt in range(max(0, self.settings.API_MAX_RETRIES) + 1):
            try:
                async with httpx.AsyncClient(timeout=self.settings.API_TIMEOUT_SECONDS) as client:
                    response = await client.post(self.base_url, json=payload, headers=self._get_headers())

                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < self.settings.API_MAX_RETRIES:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.status_code in {200, 201}:
                    data = response.json()
                    if payload.get("status") == "read":
                        logger.info(
                            "event=meta_read_receipt_succeeded message_id=%s",
                            mask_identifier(payload.get("message_id")),
                        )
                        return data
                    recipient = payload.get("to")
                    message_id = None
                    messages = data.get("messages") if isinstance(data, dict) else None
                    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
                        message_id = messages[0].get("id")
                    logger.info(
                        "event=meta_outbound_succeeded recipient=%s message_id=%s",
                        mask_identifier(recipient),
                        mask_identifier(message_id),
                    )
                    return data

                try:
                    error_data = response.json()
                    error = error_data.get("error", {})
                    error_code = error.get("code")
                    error_subcode = error.get("error_subcode")
                except Exception:
                    error_code = None
                    error_subcode = None
                logger.error(
                    "event=meta_outbound_failed http_status=%s error_code=%s "
                    "error_subcode=%s recipient=%s",
                    response.status_code,
                    error_code,
                    error_subcode,
                    mask_identifier(payload.get("to")),
                )
                return None
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self.settings.API_MAX_RETRIES:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                logger.error("WhatsApp network request failed: %s", type(exc).__name__)
                return None
            except Exception as exc:
                logger.exception("Unexpected WhatsApp client error: %s", type(exc).__name__)
                return None
        return None

    async def send_text_message(
        self,
        to_phone_number: str,
        message_text: str,
        preview_url: bool = False,
    ) -> Optional[dict[str, Any]]:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone_number,
            "type": "text",
            "text": {"preview_url": preview_url, "body": message_text},
        }
        return await self._post_payload(payload)

    async def send_interactive_list(
        self,
        to_phone_number: str,
        body: str,
        button_text: str,
        sections: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body[:1024]},
                "action": {"button": button_text[:20], "sections": sections},
            },
        }
        return await self._post_payload(payload)

    async def mark_message_as_read(self, message_id: str) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return await self._post_payload(payload) is not None
