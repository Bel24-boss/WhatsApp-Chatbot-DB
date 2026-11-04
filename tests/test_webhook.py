import hashlib
import hmac
import json
import logging
import os
from unittest.mock import AsyncMock, patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["MENU_CATALOGUE_V11_ENABLED"] = "false"

from fastapi.testclient import TestClient

from app.main import (
    app,
    deduplicator,
    extract_message_text,
    persistence_safe_inbound_body,
    repository,
    settings,
    whatsapp_client,
    workflow_engine,
)
from app.security import verify_meta_signature


client = TestClient(app)


def test_onboarding_identity_inputs_are_redacted_from_history():
    assert persistence_safe_inbound_body("63-123456-A-00", "onboarding_id_number") == "[REDACTED ID NUMBER]"
    assert persistence_safe_inbound_body("FLA-123456", "onboarding_reference") == "[REDACTED ACCOUNT REFERENCE]"
    assert persistence_safe_inbound_body("POL-123456", "policy_details_number") == "[REDACTED POLICY REFERENCE]"
    assert persistence_safe_inbound_body("+263771234567", "payment_mobile") == "[REDACTED PAYMENT CONTACT]"


def realistic_message_payload(
    message_id: str,
    *,
    wa_id: str = "263771230001",
    phone_number_id: str = "1298489380023613",
    text: str = "Hello",
) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102030405060708",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "263781380349",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test Customer"},
                                    "wa_id": wa_id,
                                }
                            ],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": message_id,
                                    "timestamp": "1791968400",
                                    "text": {"body": text},
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def signed_webhook_post(payload: dict, secret: str):
    raw_body = json.dumps(payload).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook",
        content=raw_body,
        headers={"X-Hub-Signature-256": f"sha256={digest}"},
    )


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "Fidelity Life Assurance WhatsApp Bot"
    assert data["status"] == "healthy"


def test_readiness_reports_missing_integrations():
    response = client.get("/readiness")
    assert response.status_code in {200, 503}
    data = response.json()
    assert "checks" in data
    assert "database" in data["checks"]
    assert data["commercial_capabilities"]["needs_capture"] is True


def test_payment_callback_requires_signature_and_is_idempotent():
    original_secret = settings.PAYMENT_CALLBACK_SECRET
    settings.PAYMENT_CALLBACK_SECRET = "callback-test-secret"
    try:
        conversation_id = repository.get_or_create_conversation("263771230099", "Callback Test")
        repository.create_transaction(
            conversation_id,
            "POL-CB-1",
            "10.00",
            "mobile_money",
            "pending",
            "PAY-CB-TEST-1",
        )
        payload = {"event_id": "EVT-CB-TEST-1", "reference": "PAY-CB-TEST-1", "status": "successful"}
        raw = json.dumps(payload).encode("utf-8")
        digest = hmac.new(settings.PAYMENT_CALLBACK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        headers = {"X-Payment-Signature": f"sha256={digest}"}
        first = client.post("/internal/payments/callback", content=raw, headers=headers)
        second = client.post("/internal/payments/callback", content=raw, headers=headers)
        assert first.status_code == 200
        assert first.json()["transaction_matched"] is True
        assert second.json()["status"] == "duplicate"
        assert client.post("/internal/payments/callback", content=raw).status_code == 401
    finally:
        settings.PAYMENT_CALLBACK_SECRET = original_secret


def test_commercial_analytics_requires_internal_key():
    original_key = settings.INTERNAL_API_KEY
    settings.INTERNAL_API_KEY = "analytics-test-key"
    try:
        assert client.get("/internal/analytics/commercial").status_code == 401
        response = client.get(
            "/internal/analytics/commercial",
            headers={"X-Internal-Key": "analytics-test-key"},
        )
        assert response.status_code == 200
        assert "verified_payment_value" in response.json()
    finally:
        settings.INTERNAL_API_KEY = original_key


def test_webhook_get_verification_success():
    original_token = settings.WHATSAPP_VERIFY_TOKEN
    settings.WHATSAPP_VERIFY_TOKEN = "test_verify_token_123"
    try:
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify_token_123",
                "hub.challenge": "challenge_string_9876",
            },
        )
        assert response.status_code == 200
        assert response.text == "challenge_string_9876"
    finally:
        settings.WHATSAPP_VERIFY_TOKEN = original_token


def test_webhook_get_verification_rejects_mismatch():
    original_token = settings.WHATSAPP_VERIFY_TOKEN
    settings.WHATSAPP_VERIFY_TOKEN = "correct_token"
    try:
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_123",
            },
        )
        assert response.status_code == 403
    finally:
        settings.WHATSAPP_VERIFY_TOKEN = original_token


def test_webhook_get_verification_requires_parameters():
    assert client.get("/webhook").status_code == 400


def test_webhook_post_signature_validation():
    original_secret = settings.META_APP_SECRET
    test_secret = "test_secret_abc123"
    settings.META_APP_SECRET = test_secret
    payload = {"object": "whatsapp_business_account", "entry": []}
    raw_body = json.dumps(payload).encode("utf-8")
    digest = hmac.new(test_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    try:
        valid = client.post(
            "/webhook",
            content=raw_body,
            headers={"X-Hub-Signature-256": f"sha256={digest}"},
        )
        assert valid.status_code == 200
        assert valid.json() == {"status": "ok"}

        invalid = client.post(
            "/webhook",
            content=raw_body,
            headers={"X-Hub-Signature-256": "sha256=invalid"},
        )
        assert invalid.status_code == 403
    finally:
        settings.META_APP_SECRET = original_secret


def test_webhook_rejects_malformed_and_wrong_object():
    original_secret = settings.META_APP_SECRET
    settings.META_APP_SECRET = ""
    try:
        malformed = client.post("/webhook", content=b"not-json")
        assert malformed.status_code == 400
        non_object = client.post("/webhook", json=[])
        assert non_object.status_code == 400
        wrong_object = client.post("/webhook", json={"object": "page", "entry": []})
        assert wrong_object.status_code == 400
    finally:
        settings.META_APP_SECRET = original_secret


def test_extracts_text_and_interactive_replies():
    assert extract_message_text({"type": "text", "text": {"body": "hello"}}) == "hello"
    assert (
        extract_message_text(
            {"type": "interactive", "interactive": {"list_reply": {"id": "policy_enquiry"}}}
        )
        == "policy_enquiry"
    )
    assert extract_message_text({"type": "image", "image": {"id": "MEDIA_IMAGE_1"}}) == "__media__:image:MEDIA_IMAGE_1"
    assert extract_message_text({"type": "document", "document": {"id": "MEDIA_DOC_1"}}) == "__media__:document:MEDIA_DOC_1"


def test_realistic_incoming_message_routes_and_sends_reply(caplog):
    original_secret = settings.META_APP_SECRET
    original_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    settings.META_APP_SECRET = "realistic-test-secret"
    settings.WHATSAPP_PHONE_NUMBER_ID = "1298489380023613"
    deduplicator.clear()
    payload = realistic_message_payload("wamid.integration-success-0001")
    caplog.set_level(logging.INFO, logger="fidelity.main")
    try:
        with (
            patch.object(
                whatsapp_client,
                "mark_message_as_read",
                new=AsyncMock(return_value=True),
            ) as mark_read,
            patch.object(
                whatsapp_client,
                "send_interactive_list",
                new=AsyncMock(return_value={"messages": [{"id": "wamid.outbound-0001"}]}),
            ) as send_interactive,
            patch.object(
                whatsapp_client,
                "send_text_message",
                new=AsyncMock(return_value={"messages": [{"id": "wamid.outbound-fallback"}]}),
            ) as send_text,
        ):
            response = signed_webhook_post(payload, settings.META_APP_SECRET)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mark_read.assert_awaited_once_with("wamid.integration-success-0001")
        send_interactive.assert_awaited_once()
        assert send_interactive.await_args.args[0] == "263771230001"
        assert "welcome to fidelity" in send_interactive.await_args.args[1].lower()
        send_text.assert_not_awaited()
        assert repository.message_exists("wamid.integration-success-0001")
        assert "event=whatsapp_webhook_accepted" in caplog.text
        assert "event=whatsapp_routing_completed" in caplog.text
        assert "event=whatsapp_outbound_result status=sent" in caplog.text
    finally:
        settings.META_APP_SECRET = original_secret
        settings.WHATSAPP_PHONE_NUMBER_ID = original_phone_id


def test_duplicate_incoming_message_is_not_replied_to_twice():
    original_secret = settings.META_APP_SECRET
    original_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    settings.META_APP_SECRET = "duplicate-test-secret"
    settings.WHATSAPP_PHONE_NUMBER_ID = "1298489380023613"
    deduplicator.clear()
    payload = realistic_message_payload(
        "wamid.integration-duplicate-0001",
        wa_id="263771230002",
    )
    try:
        with (
            patch.object(
                whatsapp_client,
                "mark_message_as_read",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                whatsapp_client,
                "send_interactive_list",
                new=AsyncMock(return_value={"messages": [{"id": "wamid.outbound-0002"}]}),
            ) as send_interactive,
            patch.object(
                whatsapp_client,
                "send_text_message",
                new=AsyncMock(return_value={"messages": [{"id": "wamid.outbound-language"}]}),
            ) as send_text,
        ):
            first = signed_webhook_post(payload, settings.META_APP_SECRET)
            second = signed_webhook_post(payload, settings.META_APP_SECRET)

        assert first.status_code == 200
        assert second.status_code == 200
        assert send_interactive.await_count == 1
        assert send_text.await_count == 0
    finally:
        settings.META_APP_SECRET = original_secret
        settings.WHATSAPP_PHONE_NUMBER_ID = original_phone_id


def test_workflow_failure_sends_safe_fallback():
    original_secret = settings.META_APP_SECRET
    original_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    settings.META_APP_SECRET = "workflow-failure-secret"
    settings.WHATSAPP_PHONE_NUMBER_ID = "1298489380023613"
    deduplicator.clear()
    payload = realistic_message_payload(
        "wamid.integration-workflow-failure",
        wa_id="263771230003",
    )
    try:
        with (
            patch.object(
                whatsapp_client,
                "mark_message_as_read",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                workflow_engine,
                "process_message",
                new=AsyncMock(side_effect=RuntimeError("sanitised test failure")),
            ),
            patch.object(
                whatsapp_client,
                "send_text_message",
                new=AsyncMock(return_value={"messages": [{"id": "wamid.outbound-0003"}]}),
            ) as send_text,
        ):
            response = signed_webhook_post(payload, settings.META_APP_SECRET)

        assert response.status_code == 200
        send_text.assert_awaited_once()
        assert "could not process" in send_text.await_args.args[1].lower()
    finally:
        settings.META_APP_SECRET = original_secret
        settings.WHATSAPP_PHONE_NUMBER_ID = original_phone_id


def test_outbound_failure_is_recorded_without_crashing_webhook():
    original_secret = settings.META_APP_SECRET
    original_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    settings.META_APP_SECRET = "outbound-failure-secret"
    settings.WHATSAPP_PHONE_NUMBER_ID = "1298489380023613"
    deduplicator.clear()
    wa_id = "263771230004"
    payload = realistic_message_payload("wamid.integration-outbound-failure", wa_id=wa_id)
    try:
        with (
            patch.object(
                whatsapp_client,
                "mark_message_as_read",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                whatsapp_client,
                "send_interactive_list",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                whatsapp_client,
                "send_text_message",
                new=AsyncMock(return_value=None),
            ),
        ):
            response = signed_webhook_post(payload, settings.META_APP_SECRET)

        history = repository.get_history(wa_id)
        assert response.status_code == 200
        assert history[-1]["direction"] == "outbound"
        assert history[-1]["status"] == "failed"
    finally:
        settings.META_APP_SECRET = original_secret
        settings.WHATSAPP_PHONE_NUMBER_ID = original_phone_id


def test_status_only_event_is_acknowledged_without_reply():
    original_secret = settings.META_APP_SECRET
    settings.META_APP_SECRET = "status-only-secret"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "102030405060708", "changes": [{"field": "messages", "value": {"statuses": []}}]}],
    }
    try:
        with patch.object(
            whatsapp_client,
            "send_text_message",
            new=AsyncMock(return_value=None),
        ) as send_text:
            response = signed_webhook_post(payload, settings.META_APP_SECRET)
        assert response.status_code == 200
        send_text.assert_not_awaited()
    finally:
        settings.META_APP_SECRET = original_secret


def test_wrong_phone_number_id_is_ignored_safely():
    original_secret = settings.META_APP_SECRET
    original_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    settings.META_APP_SECRET = "wrong-phone-secret"
    settings.WHATSAPP_PHONE_NUMBER_ID = "1298489380023613"
    payload = realistic_message_payload(
        "wamid.integration-wrong-phone",
        wa_id="263771230005",
        phone_number_id="9999999999999999",
    )
    try:
        with patch.object(
            whatsapp_client,
            "send_text_message",
            new=AsyncMock(return_value=None),
        ) as send_text:
            response = signed_webhook_post(payload, settings.META_APP_SECRET)
        assert response.status_code == 200
        send_text.assert_not_awaited()
        assert repository.message_exists("wamid.integration-wrong-phone") is False
    finally:
        settings.META_APP_SECRET = original_secret
        settings.WHATSAPP_PHONE_NUMBER_ID = original_phone_id


def test_handoff_requires_configuration():
    original_key = settings.HANDOFF_API_KEY
    settings.HANDOFF_API_KEY = ""
    try:
        response = client.post(
            "/internal/handoff",
            json={"wa_id": "263771234567", "workflow_id": "policy_enquiry"},
        )
        assert response.status_code == 503
    finally:
        settings.HANDOFF_API_KEY = original_key


def test_production_signature_verification_fails_closed_without_secret():
    assert verify_meta_signature(b"{}", None, "", allow_unsigned=False) is False


def test_agent_takeover_and_release_lifecycle():
    original_key = settings.HANDOFF_API_KEY
    settings.HANDOFF_API_KEY = "test-handoff-key"
    wa_id = "263771299999"
    conversation_id = repository.get_or_create_conversation(wa_id)
    escalation_id = repository.create_escalation(
        conversation_id,
        "general",
        "Customer requested assistance",
        "General Customer Care",
    )
    try:
        takeover = client.post(
            f"/internal/escalations/{escalation_id}/status",
            headers={"X-Handoff-Key": "test-handoff-key"},
            json={"status": "takeover_acknowledged"},
        )
        assert takeover.status_code == 200
        assert repository.get_session(wa_id)["state"] == "human_takeover"

        released = client.post(
            f"/internal/escalations/{escalation_id}/status",
            headers={"X-Handoff-Key": "test-handoff-key"},
            json={"status": "released"},
        )
        assert released.status_code == 200
        assert repository.get_session(wa_id)["state"] == "main_menu"
    finally:
        settings.HANDOFF_API_KEY = original_key


def test_development_simulator_uses_real_workflow():
    original_environment = settings.APP_ENV
    settings.APP_ENV = "development"
    wa_id = "263781380349"
    try:
        page = client.get("/simulator")
        assert page.status_code == 200
        assert "Fidelity Assistant" in page.text
        assert "--wa-green" in page.text
        assert "Search or start a new chat" in page.text

        logo = client.get("/simulator/assets/fidelity-logo.png")
        assert logo.status_code == 200
        assert logo.headers["content-type"] == "image/png"

        font = client.get("/simulator/assets/montserrat.woff2")
        assert font.status_code == 200
        assert font.headers["content-type"] == "font/woff2"

        reset = client.post("/simulator/reset", json={"wa_id": wa_id})
        assert reset.status_code == 200

        message = client.post(
            "/simulator/message",
            json={"wa_id": wa_id, "text": "Hello", "user_name": "Believe"},
        )
        assert message.status_code == 200
        data = message.json()
        assert data["state"] == "main_menu"
        assert "welcome to fidelity" in data["reply"].lower()
        assert data["interactive"]
    finally:
        settings.APP_ENV = original_environment


def test_simulator_is_hidden_in_production():
    original_environment = settings.APP_ENV
    settings.APP_ENV = "production"
    try:
        assert client.get("/simulator").status_code == 404
        assert client.get("/simulator/assets/fidelity-logo.png").status_code == 404
        assert client.get("/simulator/assets/montserrat.woff2").status_code == 404
    finally:
        settings.APP_ENV = original_environment
