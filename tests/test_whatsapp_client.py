import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import Settings
from app.whatsapp_client import WhatsAppClient


def build_client() -> WhatsAppClient:
    settings = Settings(
        WHATSAPP_ACCESS_TOKEN="secret-token",
        WHATSAPP_PHONE_NUMBER_ID="1298489380023613",
        WHATSAPP_VERIFY_TOKEN="verify-token",
        META_GRAPH_API_VERSION="v26.0",
        _env_file=None,
    )
    return WhatsAppClient(settings)


def mock_async_client(response: MagicMock) -> MagicMock:
    context = AsyncMock()
    context.__aenter__.return_value.get.return_value = response
    return MagicMock(return_value=context)


def test_connection_status_reports_valid_credentials_without_secrets():
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "id": "1298489380023613",
        "display_phone_number": "+263781380349",
        "verified_name": "Fidelity Life Assurance",
        "quality_rating": "GREEN",
    }
    client = build_client()

    with patch("app.whatsapp_client.httpx.AsyncClient", mock_async_client(response)):
        result = asyncio.run(client.get_connection_status())

    assert result["authenticated"] is True
    assert result["phone_number_id_matches"] is True
    assert result["display_phone_number"] == "***0349"
    assert "secret-token" not in str(result)


def test_connection_status_reports_meta_error_codes_without_message():
    response = MagicMock(status_code=401)
    response.json.return_value = {
        "error": {
            "message": "Sensitive provider response",
            "type": "OAuthException",
            "code": 190,
            "error_subcode": 467,
        }
    }
    client = build_client()

    with patch("app.whatsapp_client.httpx.AsyncClient", mock_async_client(response)):
        result = asyncio.run(client.get_connection_status())

    assert result["reachable"] is True
    assert result["authenticated"] is False
    assert result["error_code"] == 190
    assert result["error_subcode"] == 467
    assert "Sensitive provider response" not in str(result)


def test_outbound_message_is_skipped_when_configuration_is_missing():
    settings = Settings(
        WHATSAPP_ACCESS_TOKEN="",
        WHATSAPP_PHONE_NUMBER_ID="",
        WHATSAPP_VERIFY_TOKEN="",
        _env_file=None,
    )
    client = WhatsAppClient(settings)

    with patch("app.whatsapp_client.httpx.AsyncClient") as async_client:
        result = asyncio.run(client.send_text_message("263771230006", "Hello"))

    assert result is None
    async_client.assert_not_called()
