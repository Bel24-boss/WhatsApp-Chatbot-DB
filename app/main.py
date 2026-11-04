import asyncio
import hashlib
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app import __version__
from app.config import get_settings
from app.database import ChatRepository
from app.deduplication import MessageDeduplicator
from app.integrations import (
    AgentNotificationClient,
    FidelityCoreClient,
    FidelityPaymentClient,
    FidelityQuoteClient,
    FidelityCRMClient,
    InsureTechClient,
    IntegrationResponseError,
    IntegrationUnavailableError,
)
from app.security import verify_meta_signature
from app.whatsapp_client import WhatsAppClient, mask_identifier
from app.workflow import BotReply, FidelityWorkflowEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fidelity.main")

settings = get_settings()
repository = ChatRepository(settings.DATABASE_URL, settings.SESSION_TTL_SECONDS)
whatsapp_client = WhatsAppClient(settings=settings)
core_client = FidelityCoreClient(settings)
payment_client = FidelityPaymentClient(settings)
agent_notification_client = AgentNotificationClient(settings)
quote_client = FidelityQuoteClient(settings)
crm_client = FidelityCRMClient(settings)
insuretech_client = InsureTechClient(settings)
workflow_engine = FidelityWorkflowEngine(
    settings,
    repository,
    core_client,
    payment_client,
    insuretech_client,
)
deduplicator = MessageDeduplicator(ttl_seconds=settings.DEDUPLICATION_TTL_SECONDS)
payment_poll_tasks: set[asyncio.Task] = set()


class HandoffRequest(BaseModel):
    wa_id: str = Field(min_length=8, max_length=20, pattern=r"^[1-9][0-9]+$")
    workflow_id: str = Field(min_length=3, max_length=80)
    user_name: Optional[str] = Field(default=None, max_length=160)
    context: dict[str, Any] = Field(default_factory=dict)
    send_message: bool = False


class EscalationStatusUpdate(BaseModel):
    status: Literal[
        "queue_acknowledged",
        "takeover_acknowledged",
        "released",
        "resolved",
        "rejected",
    ]


class SimulatorMessageRequest(BaseModel):
    wa_id: str = Field(min_length=8, max_length=20, pattern=r"^[1-9][0-9]+$")
    text: str = Field(min_length=1, max_length=1000)
    user_name: Optional[str] = Field(default="Believe", max_length=160)


class SimulatorResetRequest(BaseModel):
    wa_id: str = Field(min_length=8, max_length=20, pattern=r"^[1-9][0-9]+$")


class QuotePricingUpdate(BaseModel):
    status: Literal["priced", "rejected"]
    premium_amount: Optional[str] = Field(default=None, max_length=40)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    external_reference: Optional[str] = Field(default=None, max_length=160)
    expires_at: Optional[datetime] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository.initialize()
    logger.info("Starting Fidelity Life Assurance WhatsApp Bot v%s", __version__)
    logger.info("Active configuration summary: %s", settings.masked_summary())
    if payment_client.configured:
        for pending in repository.get_pending_transactions():
            schedule_payment_poll(
                pending["wa_id"],
                pending["conversation_id"],
                pending["reference"],
            )
    yield
    for task in list(payment_poll_tasks):
        task.cancel()
    if payment_poll_tasks:
        await asyncio.gather(*payment_poll_tasks, return_exceptions=True)
    logger.info("Shutting down Fidelity Life Assurance WhatsApp Bot")


app = FastAPI(
    title="Fidelity Life Assurance WhatsApp Bot",
    description="WhatsApp self-service, transaction, and assisted-service orchestration API.",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": "Fidelity Life Assurance WhatsApp Bot",
        "version": __version__,
        "whatsapp_configured": settings.is_configured,
        "core_api_configured": core_client.configured,
        "payment_api_configured": payment_client.configured,
        "agent_notification_configured": agent_notification_client.configured,
        "graph_api_version": settings.META_GRAPH_API_VERSION,
    }


@app.get("/readiness", tags=["Health"])
async def readiness_check():
    checks = {
        "database": repository.ping(),
        "whatsapp": settings.is_configured,
        "customer_verification": bool(settings.CUSTOMER_VERIFICATION_PATH),
        "whatsapp_onboarding": bool(
            settings.ONBOARDING_START_PATH
            and settings.ONBOARDING_RELATIONSHIPS_PATH
            and settings.ONBOARDING_LINK_PATH
        ),
        "core_api": core_client.configured,
        "payment_api": payment_client.configured,
        "payment_identity_verification": bool(
            settings.PAYMENT_VERIFICATION_START_PATH
            and settings.PAYMENT_VERIFICATION_CONFIRM_PATH
            and settings.PAYMENT_ELIGIBLE_POLICIES_PATH
        ),
        "agent_notification": agent_notification_client.configured,
        "handoff_authentication": bool(settings.HANDOFF_API_KEY),
        "escalation_matrix": bool(workflow_engine.escalation_matrix),
        "business_hours": bool(workflow_engine.business_hours),
        "payment_methods": bool(workflow_engine.payment_methods),
        "bank_transfer_instructions": bool(workflow_engine.bank_transfer_instructions),
        "insuretech_products": insuretech_client.configured,
        "insuretech_quotes": insuretech_client.configured,
        "insuretech_applications": insuretech_client.configured,
        "application_tracking_authorization": bool(
            settings.INSURETECH_APPLICATION_TRACKING_ENABLED
            and settings.CUSTOMER_VERIFICATION_PATH
        ),
    }
    ready = all(checks.values())
    content = {
        "status": "ready" if ready else "not_ready",
        "environment": settings.APP_ENV,
        "checks": checks,
        "missing": [name for name, configured in checks.items() if not configured],
        "commercial_capabilities": {
            "needs_capture": True,
            "approved_recommendation_rules": workflow_engine.commercial_rules.approved,
            "quotation_api": quote_client.configured,
            "crm_delivery": crm_client.configured,
            "payment_callback_authentication": bool(settings.PAYMENT_CALLBACK_SECRET),
            "follow_up_sending": bool(
                settings.FOLLOW_UP_ENABLED and workflow_engine.follow_up_templates
            ),
            "insuretech_products": insuretech_client.configured,
            "insuretech_quotes": insuretech_client.configured,
            "insuretech_applications": insuretech_client.configured,
            "policy_number_operations": bool(
                insuretech_client.configured and settings.INSURETECH_POLICY_NUMBER_ENABLED
            ),
            "cover_activation": bool(
                insuretech_client.configured and settings.INSURETECH_COVER_ACTIVATION_ENABLED
            ),
            "note": "Unconfigured capabilities remain fail-closed; requests are recorded as pending.",
        },
    }
    return JSONResponse(content, status_code=200 if ready else 503)


def require_internal_key(value: Optional[str]) -> None:
    configured = settings.INTERNAL_API_KEY or settings.HANDOFF_API_KEY
    if not configured:
        raise HTTPException(status_code=503, detail="Internal API access is not configured")
    if not value or not hmac.compare_digest(value, configured):
        raise HTTPException(status_code=401, detail="Invalid internal credentials")


@app.get("/diagnostics/whatsapp", tags=["Development"])
async def whatsapp_diagnostics():
    require_development_simulator()
    return await whatsapp_client.get_connection_status()


@app.get("/webhook", tags=["Webhook"])
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    if not hub_mode or not hub_verify_token:
        return Response(
            content="Missing required parameters",
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="text/plain",
        )

    configured_token = settings.WHATSAPP_VERIFY_TOKEN.strip()
    token_matches = hmac.compare_digest(hub_verify_token.strip(), configured_token)
    if hub_mode == "subscribe" and token_matches:
        logger.info("WhatsApp webhook verification succeeded")
        return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)

    logger.warning("WhatsApp webhook verification rejected")
    return Response(
        content="Verification token mismatch",
        status_code=status.HTTP_403_FORBIDDEN,
        media_type="text/plain",
    )


def extract_message_text(message: dict[str, Any]) -> Optional[str]:
    message_type = message.get("type")
    if message_type == "text":
        return message.get("text", {}).get("body")
    if message_type == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("list_reply") or interactive.get("button_reply") or {}
        return reply.get("id") or reply.get("title")
    if message_type == "button":
        return message.get("button", {}).get("payload") or message.get("button", {}).get("text")
    if message_type in {"image", "document"}:
        media_id = str(message.get(message_type, {}).get("id") or "").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{5,255}", media_id):
            return f"__media__:{message_type}:{media_id}"
    return None


def extract_meta_message_id(response: Optional[dict[str, Any]]) -> Optional[str]:
    if not response:
        return None
    messages = response.get("messages")
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        return messages[0].get("id")
    return None


def persistence_safe_inbound_body(text: Optional[str], state: str) -> Optional[str]:
    """Exclude identifiers and payment-contact data from routine message history."""
    if text is None:
        return None
    if state == "onboarding_id_number":
        return "[REDACTED ID NUMBER]"
    if state == "onboarding_reference":
        return "[REDACTED ACCOUNT REFERENCE]"
    if state in {"policy_details_number", "payment_history_number"}:
        return "[REDACTED POLICY REFERENCE]"
    if state == "claim_status_reference":
        return "[REDACTED CLAIM REFERENCE]"
    if state == "payment_status_reference":
        return "[REDACTED PAYMENT REFERENCE]"
    if state == "payment_mobile":
        return "[REDACTED PAYMENT CONTACT]"
    if state == "payment_verify_mobile":
        return "[REDACTED REGISTERED MOBILE]"
    if state == "payment_verify_code":
        return "[REDACTED VERIFICATION CODE]"
    if state == "payment_pop_waiting":
        return "[REDACTED PAYMENT PROOF ATTACHMENT]"
    if state == "enquiry_callback_number":
        return "[REDACTED CALLBACK NUMBER]"
    return text


def summarize_webhook_payload(payload: dict[str, Any]) -> dict[str, int]:
    summary = {"entries": 0, "changes": 0, "messages": 0, "statuses": 0}
    entries = payload.get("entry", [])
    if not isinstance(entries, list):
        return summary
    summary["entries"] = len(entries)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue
        summary["changes"] += len(changes)
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            messages = value.get("messages", [])
            statuses = value.get("statuses", [])
            summary["messages"] += len(messages) if isinstance(messages, list) else 0
            summary["statuses"] += len(statuses) if isinstance(statuses, list) else 0
    return summary


def schedule_payment_poll(wa_id: str, conversation_id: str, reference: str) -> None:
    if not reference or not payment_client.configured:
        return
    task = asyncio.create_task(poll_payment_status(wa_id, conversation_id, reference))
    payment_poll_tasks.add(task)
    task.add_done_callback(payment_poll_tasks.discard)


async def poll_payment_status(wa_id: str, conversation_id: str, reference: str) -> None:
    terminal_success = {"successful", "success", "paid", "completed"}
    terminal_failure = {"failed", "declined", "cancelled"}
    for _ in range(max(1, settings.PAYMENT_POLL_MAX_ATTEMPTS)):
        await asyncio.sleep(max(1, settings.PAYMENT_POLL_INTERVAL_SECONDS))
        try:
            result = await payment_client.get_payment_status(reference)
        except (IntegrationUnavailableError, IntegrationResponseError):
            continue
        payment_status = str(result.get("status") or "pending").lower()
        repository.update_transaction_status(reference, payment_status)
        if payment_status not in terminal_success | terminal_failure:
            continue

        if payment_status in terminal_success:
            message = f"Your payment was completed successfully.\n\nReference/receipt: {reference}"
        else:
            message = (
                "Your payment was not completed. No successful payment has been recorded.\n\n"
                f"Reference: {reference}\nType *Agent* if you need assistance."
            )
        response = await whatsapp_client.send_text_message(wa_id, message)
        repository.record_message(
            conversation_id,
            direction="outbound",
            body=message,
            meta_message_id=extract_meta_message_id(response),
            status="sent" if response else "failed",
        )
        return


async def prepare_reply_for_delivery(
    wa_id: str,
    conversation_id: str,
    reply: BotReply,
) -> BotReply:
    if not reply.escalation_id or not reply.metadata.get("handover"):
        return reply.ensure_navigation()

    history = repository.get_history(wa_id, limit=20) if reply.metadata.get("share_context") else []
    notification = {
        "escalation_id": reply.escalation_id,
        "conversation_id": conversation_id,
        "customer_wa_id": wa_id,
        "category": reply.metadata.get("category"),
        "assigned_team": reply.metadata.get("assigned_team"),
        "conversation_history": history,
    }
    try:
        result = await agent_notification_client.notify(notification)
        if result.get("acknowledged") is False:
            raise IntegrationResponseError("agent notification service", 502, "queue did not acknowledge")
        external_reference = str(result.get("reference") or result.get("handover_id") or "")
        escalation_status = str(result.get("status") or "queue_acknowledged")
        repository.update_escalation_status(reply.escalation_id, escalation_status)
        request_id = reply.metadata.get("request_id")
        if request_id:
            repository.update_request_status(
                request_id,
                "acknowledged",
                external_reference or reply.escalation_id,
            )
        reply.text = reply.metadata.get("success_text") or reply.text
        if escalation_status == "takeover_acknowledged":
            repository.save_session(
                wa_id,
                conversation_id,
                "human_takeover",
                {"escalation_id": reply.escalation_id},
            )
    except (IntegrationUnavailableError, IntegrationResponseError) as exc:
        repository.update_escalation_status(reply.escalation_id, "notification_failed")
        request_id = reply.metadata.get("request_id")
        if request_id:
            repository.update_request_status(request_id, "delivery_unconfirmed")
        reply.text = reply.metadata.get("failure_text") or reply.text
        logger.error(
            "Escalation %s was saved but agent notification failed: %s",
            reply.escalation_id,
            type(exc).__name__,
        )
    return reply.ensure_navigation()


async def send_and_record_reply(
    wa_id: str,
    conversation_id: str,
    reply: BotReply,
) -> bool:
    if reply.metadata.get("suppress_send"):
        logger.info(
            "event=whatsapp_outbound_suppressed recipient=%s conversation=%s",
            mask_identifier(wa_id),
            mask_identifier(conversation_id),
        )
        return True

    reply = await prepare_reply_for_delivery(wa_id, conversation_id, reply)

    response: Optional[dict[str, Any]] = None
    if reply.interactive:
        logger.info(
            "event=whatsapp_outbound_attempt kind=interactive recipient=%s conversation=%s",
            mask_identifier(wa_id),
            mask_identifier(conversation_id),
        )
        response = await whatsapp_client.send_interactive_list(
            wa_id,
            reply.text,
            reply.interactive["button"],
            reply.interactive["sections"],
        )
        if response is None:
            logger.warning(
                "event=whatsapp_interactive_fallback recipient=%s conversation=%s",
                mask_identifier(wa_id),
                mask_identifier(conversation_id),
            )
    if response is None:
        logger.info(
            "event=whatsapp_outbound_attempt kind=text recipient=%s conversation=%s",
            mask_identifier(wa_id),
            mask_identifier(conversation_id),
        )
        response = await whatsapp_client.send_text_message(wa_id, reply.text)

    outbound_message_id = extract_meta_message_id(response)
    delivery_status = "sent" if response else "failed"

    repository.record_message(
        conversation_id,
        direction="outbound",
        body=reply.text,
        message_type="interactive" if reply.interactive else "text",
        meta_message_id=outbound_message_id,
        status=delivery_status,
    )
    logger.log(
        logging.INFO if response else logging.ERROR,
        "event=whatsapp_outbound_result status=%s recipient=%s conversation=%s message_id=%s",
        delivery_status,
        mask_identifier(wa_id),
        mask_identifier(conversation_id),
        mask_identifier(outbound_message_id),
    )

    payment_reference = reply.metadata.get("payment_reference")
    payment_status = reply.metadata.get("payment_status")
    if (
        payment_reference
        and payment_status in {"pending", "processing"}
        and not reply.metadata.get("manual_status_check")
    ):
        schedule_payment_poll(wa_id, conversation_id, payment_reference)
    return response is not None


def require_development_simulator() -> None:
    if settings.APP_ENV.lower() in {"production", "prod"}:
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/simulator", response_class=HTMLResponse, tags=["Development"])
async def simulator_page():
    require_development_simulator()
    page_path = Path(__file__).with_name("simulator.html")
    return HTMLResponse(page_path.read_text(encoding="utf-8"))


@app.get("/simulator/assets/fidelity-logo.png", include_in_schema=False)
async def simulator_logo():
    require_development_simulator()
    logo_path = Path(__file__).with_name("assets") / "fidelity-logo.png"
    return FileResponse(
        logo_path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/simulator/assets/montserrat.woff2", include_in_schema=False)
async def simulator_font():
    require_development_simulator()
    font_path = Path(__file__).with_name("assets") / "montserrat-latin.woff2"
    return FileResponse(
        font_path,
        media_type="font/woff2",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.post("/simulator/message", tags=["Development"])
async def simulator_message(message: SimulatorMessageRequest):
    require_development_simulator()
    conversation_id = repository.get_or_create_conversation(message.wa_id, message.user_name)
    existing_session = repository.get_session(message.wa_id)
    existing_state = (
        existing_session.get("state")
        if existing_session and not existing_session.get("expired")
        else "main_menu"
    )
    repository.record_message(
        conversation_id,
        direction="inbound",
        body=persistence_safe_inbound_body(message.text, existing_state),
        message_type="simulator",
        status="received",
    )
    reply = await workflow_engine.process_message(
        message.wa_id,
        message.text,
        conversation_id,
        message.user_name,
    )
    if not reply.metadata.get("suppress_send"):
        reply = await prepare_reply_for_delivery(message.wa_id, conversation_id, reply)
        repository.record_message(
            conversation_id,
            direction="outbound",
            body=reply.text,
            message_type="simulator",
            status="simulated",
        )
    session = repository.get_session(message.wa_id)
    return {
        "conversation_id": conversation_id,
        "reply": reply.text,
        "interactive": reply.interactive,
        "suppressed": bool(reply.metadata.get("suppress_send")),
        "state": session.get("state") if session and not session.get("expired") else "main_menu",
    }


@app.post("/simulator/reset", tags=["Development"])
async def simulator_reset(reset: SimulatorResetRequest):
    require_development_simulator()
    repository.reset_session(reset.wa_id)
    return {"status": "reset", "wa_id": reset.wa_id}


async def process_whatsapp_event(payload: dict[str, Any]) -> None:
    summary = summarize_webhook_payload(payload)
    logger.info(
        "event=whatsapp_processing_started entries=%s changes=%s messages=%s statuses=%s",
        summary["entries"],
        summary["changes"],
        summary["messages"],
        summary["statuses"],
    )
    try:
        entries = payload.get("entry", [])
        if not isinstance(entries, list):
            logger.warning("event=whatsapp_payload_ignored reason=entries_not_list")
            return
        for entry in entries:
            if not isinstance(entry, dict):
                logger.warning("event=whatsapp_entry_ignored reason=entry_not_object")
                continue
            changes = entry.get("changes", [])
            if not isinstance(changes, list):
                logger.warning("event=whatsapp_entry_ignored reason=changes_not_list")
                continue
            for change in changes:
                if not isinstance(change, dict):
                    logger.warning("event=whatsapp_change_ignored reason=change_not_object")
                    continue
                value = change.get("value", {})
                if not isinstance(value, dict):
                    logger.warning("event=whatsapp_change_ignored reason=value_not_object")
                    continue

                metadata = value.get("metadata", {})
                webhook_phone_id = metadata.get("phone_number_id") if isinstance(metadata, dict) else None
                configured_phone_id = settings.WHATSAPP_PHONE_NUMBER_ID.strip()
                if webhook_phone_id and configured_phone_id and webhook_phone_id != configured_phone_id:
                    logger.error(
                        "event=whatsapp_change_ignored reason=phone_number_id_mismatch "
                        "received_phone_id=%s configured_phone_id=%s",
                        mask_identifier(webhook_phone_id),
                        mask_identifier(configured_phone_id),
                    )
                    continue

                statuses = value.get("statuses", [])
                if not isinstance(statuses, list):
                    statuses = []
                for status_object in statuses:
                    if not isinstance(status_object, dict):
                        continue
                    message_id = status_object.get("id")
                    message_status = status_object.get("status", "unknown")
                    errors = status_object.get("errors")
                    if message_id:
                        repository.update_message_status(
                            message_id,
                            message_status,
                            json.dumps(errors) if errors else None,
                        )
                    logger.info(
                        "event=whatsapp_status_received status=%s message_id=%s",
                        message_status,
                        mask_identifier(message_id),
                    )

                contacts = value.get("contacts", [])
                user_name = contacts[0].get("profile", {}).get("name") if contacts else None

                messages = value.get("messages", [])
                if not isinstance(messages, list):
                    logger.warning("event=whatsapp_messages_ignored reason=messages_not_list")
                    continue
                for message in messages:
                    if not isinstance(message, dict):
                        logger.warning("event=whatsapp_message_ignored reason=message_not_object")
                        continue
                    message_id = message.get("id")
                    wa_id = message.get("from")
                    message_type = message.get("type", "unknown")
                    try:
                        if not message_id:
                            logger.warning("event=whatsapp_message_ignored reason=missing_message_id")
                            continue
                        if not wa_id or not re.fullmatch(r"[1-9][0-9]{7,19}", wa_id):
                            logger.warning(
                                "event=whatsapp_message_ignored reason=invalid_sender message_id=%s",
                                mask_identifier(message_id),
                            )
                            continue
                        if repository.message_exists(message_id) or deduplicator.is_duplicate(message_id):
                            logger.info(
                                "event=whatsapp_message_ignored reason=duplicate sender=%s message_id=%s",
                                mask_identifier(wa_id),
                                mask_identifier(message_id),
                            )
                            continue

                        conversation_id = repository.get_or_create_conversation(wa_id, user_name)
                        text = extract_message_text(message)
                        session_before = repository.get_session(wa_id)
                        state_before = (
                            session_before.get("state")
                            if session_before and not session_before.get("expired")
                            else "main_menu"
                        )
                        repository.record_message(
                            conversation_id,
                            direction="inbound",
                            body=persistence_safe_inbound_body(text, state_before),
                            message_type=message_type,
                            meta_message_id=message_id,
                            status="received",
                        )
                        logger.info(
                            "event=whatsapp_message_received type=%s sender=%s message_id=%s conversation=%s",
                            message_type,
                            mask_identifier(wa_id),
                            mask_identifier(message_id),
                            mask_identifier(conversation_id),
                        )

                        read_result = await whatsapp_client.mark_message_as_read(message_id)
                        logger.info(
                            "event=whatsapp_read_receipt status=%s message_id=%s",
                            "sent" if read_result else "failed",
                            mask_identifier(message_id),
                        )

                        logger.info(
                            "event=whatsapp_routing_started state=%s sender=%s message_id=%s",
                            state_before,
                            mask_identifier(wa_id),
                            mask_identifier(message_id),
                        )
                        if text is None:
                            reply = BotReply(
                                "This assistant currently accepts text and WhatsApp menu selections. "
                                "Please type *Main Menu* to continue."
                            )
                        else:
                            try:
                                reply = await workflow_engine.process_message(
                                    wa_id,
                                    text,
                                    conversation_id,
                                    user_name,
                                )
                            except Exception as exc:
                                logger.exception(
                                    "event=whatsapp_workflow_failed error=%s sender=%s message_id=%s",
                                    type(exc).__name__,
                                    mask_identifier(wa_id),
                                    mask_identifier(message_id),
                                )
                                reply = BotReply(
                                    "We could not process that message right now. "
                                    "Please try again or type *Agent* for assistance."
                                )
                        session_after = repository.get_session(wa_id)
                        state_after = (
                            session_after.get("state")
                            if session_after and not session_after.get("expired")
                            else state_before
                        )
                        logger.info(
                            "event=whatsapp_routing_completed from_state=%s to_state=%s "
                            "reply_kind=%s sender=%s message_id=%s",
                            state_before,
                            state_after,
                            "interactive" if reply.interactive else "text",
                            mask_identifier(wa_id),
                            mask_identifier(message_id),
                        )
                        await send_and_record_reply(wa_id, conversation_id, reply)
                    except Exception as exc:
                        logger.exception(
                            "event=whatsapp_message_failed error=%s sender=%s message_id=%s",
                            type(exc).__name__,
                            mask_identifier(wa_id),
                            mask_identifier(message_id),
                        )
    except Exception as exc:
        logger.exception("event=whatsapp_processing_failed error=%s", type(exc).__name__)
    finally:
        logger.info("event=whatsapp_processing_finished messages=%s", summary["messages"])


@app.post("/webhook", tags=["Webhook"])
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    raw_body = await request.body()
    logger.info(
        "event=whatsapp_webhook_received bytes=%s signature_present=%s",
        len(raw_body),
        bool(x_hub_signature_256),
    )
    if not verify_meta_signature(
        raw_body,
        x_hub_signature_256,
        settings.META_APP_SECRET,
        allow_unsigned=settings.APP_ENV.lower() not in {"production", "prod"},
    ):
        logger.warning("Unauthorized webhook POST rejected")
        return JSONResponse({"error": "Invalid signature"}, status_code=status.HTTP_403_FORBIDDEN)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("event=whatsapp_webhook_rejected reason=malformed_json")
        return JSONResponse({"error": "Malformed JSON"}, status_code=status.HTTP_400_BAD_REQUEST)

    if not isinstance(payload, dict):
        logger.warning("event=whatsapp_webhook_rejected reason=payload_not_object")
        return JSONResponse({"error": "Invalid payload"}, status_code=status.HTTP_400_BAD_REQUEST)

    if payload.get("object") != "whatsapp_business_account":
        logger.warning("event=whatsapp_webhook_rejected reason=unsupported_object")
        return JSONResponse({"error": "Unsupported webhook object"}, status_code=status.HTTP_400_BAD_REQUEST)

    summary = summarize_webhook_payload(payload)
    logger.info(
        "event=whatsapp_webhook_accepted entries=%s changes=%s messages=%s statuses=%s",
        summary["entries"],
        summary["changes"],
        summary["messages"],
        summary["statuses"],
    )
    background_tasks.add_task(process_whatsapp_event, payload)
    return {"status": "ok"}


@app.post("/internal/handoff", tags=["Handoff"])
async def start_handoff(
    handoff: HandoffRequest,
    x_handoff_key: Optional[str] = Header(None, alias="X-Handoff-Key"),
):
    if not settings.HANDOFF_API_KEY:
        raise HTTPException(status_code=503, detail="AI handoff is not configured")
    if not x_handoff_key or not hmac.compare_digest(x_handoff_key, settings.HANDOFF_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid handoff credentials")

    conversation_id = repository.get_or_create_conversation(handoff.wa_id, handoff.user_name)
    try:
        reply = await workflow_engine.start_workflow(
            handoff.wa_id,
            handoff.workflow_id,
            conversation_id,
            handoff.context,
            handoff.user_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if handoff.send_message:
        await send_and_record_reply(handoff.wa_id, conversation_id, reply)

    return {
        "status": "accepted",
        "conversation_id": conversation_id,
        "workflow_id": handoff.workflow_id,
        "message_sent": handoff.send_message,
        "entry_message": reply.text,
    }


@app.post("/internal/payments/callback", tags=["Payments"])
async def payment_provider_callback(
    request: Request,
    x_payment_signature: Optional[str] = Header(None, alias="X-Payment-Signature"),
):
    """Accept only authenticated, idempotent payment-provider outcomes."""
    if not settings.PAYMENT_CALLBACK_SECRET:
        raise HTTPException(status_code=503, detail="Payment callback authentication is not configured")
    raw_body = await request.body()
    expected = "sha256=" + hmac.new(
        settings.PAYMENT_CALLBACK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not x_payment_signature or not hmac.compare_digest(x_payment_signature, expected):
        raise HTTPException(status_code=401, detail="Invalid payment callback signature")
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Invalid callback payload")
    event_id = str(payload.get("event_id") or "").strip()
    reference = str(payload.get("reference") or payload.get("payment_reference") or "").strip()
    provider_status = str(payload.get("status") or "").strip().lower()
    allowed = {
        "pending", "processing", "successful", "paid", "completed", "confirmed",
        "failed", "declined", "cancelled", "expired", "reversed", "refunded",
    }
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{4,160}", event_id):
        raise HTTPException(status_code=422, detail="Invalid event identifier")
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{4,160}", reference):
        raise HTTPException(status_code=422, detail="Invalid payment reference")
    if provider_status not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported payment status")
    created, matched = repository.record_payment_event(event_id, reference, provider_status)
    repository.record_event(
        "payment_callback",
        "matched" if matched else "unmatched",
        correlation_id=reference,
    )
    return {
        "status": "accepted" if created else "duplicate",
        "transaction_matched": matched,
        "payment_reference": reference,
    }


@app.get("/internal/analytics/commercial", tags=["Operations"])
async def commercial_analytics(
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
):
    require_internal_key(x_internal_key)
    return repository.commercial_metrics()


@app.post("/internal/quotes/{quote_id}/pricing", tags=["Operations"])
async def update_quote_pricing(
    quote_id: str,
    update: QuotePricingUpdate,
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
):
    require_internal_key(x_internal_key)
    if update.status == "priced":
        if not update.premium_amount or not update.currency or not update.expires_at:
            raise HTTPException(
                status_code=422,
                detail="A priced quote requires premium_amount, currency and expires_at",
            )
        try:
            if Decimal(update.premium_amount) <= 0:
                raise ValueError
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid premium amount") from exc
        expiry = update.expires_at.replace(tzinfo=None) if update.expires_at.tzinfo else update.expires_at
        if expiry <= datetime.utcnow():
            raise HTTPException(status_code=422, detail="Quote expiry must be in the future")
    else:
        expiry = None
    updated = repository.update_quote_pricing(
        quote_id,
        update.status,
        premium_amount=update.premium_amount if update.status == "priced" else None,
        currency=update.currency if update.status == "priced" else None,
        external_reference=update.external_reference,
        expires_at=expiry,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Quote request not found")
    repository.record_event("quote_pricing", update.status, correlation_id=quote_id)
    return {"quote_id": quote_id, "status": update.status}


@app.get("/internal/follow-ups/due", tags=["Operations"])
async def due_follow_ups(
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
    limit: int = Query(100, ge=1, le=500),
):
    require_internal_key(x_internal_key)
    return {
        "items": repository.due_follow_ups(limit),
        "sending_enabled": bool(settings.FOLLOW_UP_ENABLED and workflow_engine.follow_up_templates),
        "note": "This endpoint exposes scheduled work only; it does not send WhatsApp messages.",
    }


@app.get("/internal/conversations/{wa_id}/history", tags=["Handoff"])
async def conversation_history(
    wa_id: str,
    x_handoff_key: Optional[str] = Header(None, alias="X-Handoff-Key"),
    limit: int = Query(50, ge=1, le=200),
):
    if not settings.HANDOFF_API_KEY:
        raise HTTPException(status_code=503, detail="Internal conversation access is not configured")
    if not x_handoff_key or not hmac.compare_digest(x_handoff_key, settings.HANDOFF_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid handoff credentials")
    if not re.fullmatch(r"[1-9][0-9]{7,19}", wa_id):
        raise HTTPException(status_code=422, detail="Invalid WhatsApp identifier")
    return {"wa_id": wa_id, "messages": repository.get_history(wa_id, limit=limit)}


@app.post("/internal/escalations/{escalation_id}/status", tags=["Handoff"])
async def update_escalation_lifecycle(
    escalation_id: str,
    update: EscalationStatusUpdate,
    x_handoff_key: Optional[str] = Header(None, alias="X-Handoff-Key"),
):
    if not settings.HANDOFF_API_KEY:
        raise HTTPException(status_code=503, detail="AI handoff is not configured")
    if not x_handoff_key or not hmac.compare_digest(x_handoff_key, settings.HANDOFF_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid handoff credentials")

    escalation = repository.get_escalation_context(escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    repository.update_escalation_status(escalation_id, update.status)

    if update.status == "takeover_acknowledged":
        repository.save_session(
            escalation["wa_id"],
            escalation["conversation_id"],
            "human_takeover",
            {"escalation_id": escalation_id},
        )
    elif update.status in {"released", "resolved", "rejected"}:
        repository.save_session(
            escalation["wa_id"],
            escalation["conversation_id"],
            "main_menu",
            {},
        )

    return {"status": update.status, "escalation_id": escalation_id}
