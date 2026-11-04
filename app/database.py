import json
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    meta_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(80), default="main_menu")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    policy_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    amount: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[str] = mapped_column(Text)
    assigned_team: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ContentRecord(Base):
    __tablename__ = "content_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    service_id: Mapped[str] = mapped_column(String(40), index=True)
    content_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(160))
    source_reference: Mapped[str] = mapped_column(String(500))
    approval_state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    version: Mapped[str] = mapped_column(String(40))
    effective_from: Mapped[datetime] = mapped_column(DateTime, index=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PermissionRecord(Base):
    __tablename__ = "permission_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    scope: Mapped[str] = mapped_column(String(120), index=True)
    granted: Mapped[bool] = mapped_column(Boolean)
    notice_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class OperationalEvent(Base):
    __tablename__ = "operational_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    service_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    result_code: Mapped[str] = mapped_column(String(80), index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class SatisfactionResponse(Base):
    __tablename__ = "satisfaction_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    journey: Mapped[str] = mapped_column(String(80), index=True)
    journey_outcome: Mapped[str] = mapped_column(String(32), index=True)
    resolved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, index=True)
    rating: Mapped[Optional[str]] = mapped_column(String(1), nullable=True, index=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_contact_requested: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="en", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ServiceContact(Base):
    __tablename__ = "service_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team: Mapped[str] = mapped_column(String(120), index=True)
    telephone: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    purpose: Mapped[str] = mapped_column(String(240))
    availability: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    validation_date: Mapped[datetime] = mapped_column(DateTime)
    owner: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ServiceLink(Base):
    __tablename__ = "service_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(String(40), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    purpose: Mapped[str] = mapped_column(String(240))
    owner: Mapped[str] = mapped_column(String(160))
    validation_date: Mapped[datetime] = mapped_column(DateTime)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    platform: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    authentication_required: Mapped[bool] = mapped_column(Boolean, default=False)


class OnboardingAttempt(Base):
    __tablename__ = "onboarding_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    selected_service: Mapped[str] = mapped_column(String(80), index=True)
    journey: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="started", index=True)
    notice_version: Mapped[str] = mapped_column(String(40))
    external_attempt_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class DigitalProfile(Base):
    __tablename__ = "digital_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), unique=True, index=True)
    external_profile_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class CustomerRelationshipLink(Base):
    __tablename__ = "customer_relationship_links"
    __table_args__ = (
        UniqueConstraint("profile_id", "business", "source_relationship_id", name="uq_profile_business_relationship"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("digital_profiles.id"), index=True)
    business: Mapped[str] = mapped_column(String(80), index=True)
    source_relationship_id: Mapped[str] = mapped_column(String(160), index=True)
    masked_reference: Mapped[str] = mapped_column(String(120))
    customer_role: Mapped[str] = mapped_column(String(80))
    permitted_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    source_status: Mapped[str] = mapped_column(String(40), index=True)
    verification_evidence_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    link_status: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class SalesLead(Base):
    __tablename__ = "sales_leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    product_interest: Mapped[str] = mapped_column(String(80), index=True)
    language: Mapped[str] = mapped_column(String(8), default="en", index=True)
    status: Mapped[str] = mapped_column(String(40), default="captured", index=True)
    qualification_status: Mapped[str] = mapped_column(String(40), default="rules_pending", index=True)
    callback_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    follow_up_consent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    assigned_team: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class QuoteRequest(Base):
    __tablename__ = "quote_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    lead_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sales_leads.id"), nullable=True, index=True)
    product_interest: Mapped[str] = mapped_column(String(80), index=True)
    requirements_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(40), default="pricing_pending", index=True)
    premium_amount: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ApplicationIntent(Base):
    __tablename__ = "application_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    lead_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sales_leads.id"), nullable=True, index=True)
    quote_request_id: Mapped[Optional[str]] = mapped_column(ForeignKey("quote_requests.id"), nullable=True, index=True)
    product_interest: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="information_pending", index=True)
    checklist_json: Mapped[str] = mapped_column(Text, default="{}")
    consent_notice_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    lead_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sales_leads.id"), nullable=True, index=True)
    scenario: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(40), default="awaiting_configuration", index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    template_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    consent_basis: Mapped[str] = mapped_column(String(80))
    attempt_count: Mapped[str] = mapped_column(String(8), default="0")
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    external_reference: Mapped[str] = mapped_column(String(160), index=True)
    provider_status: Mapped[str] = mapped_column(String(40), index=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


Index("ix_conversation_contact_status", Conversation.contact_id, Conversation.status)
Index(
    "ux_messages_meta_message_id_not_null",
    Message.meta_message_id,
    unique=True,
    mssql_where=Message.meta_message_id.is_not(None),
    sqlite_where=Message.meta_message_id.is_not(None),
)


class ChatRepository:
    def __init__(self, database_url: str, session_ttl_seconds: int = 1800):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        parsed_url = make_url(database_url)
        if parsed_url.drivername.startswith("sqlite") and parsed_url.database not in {None, ":memory:"}:
            Path(parsed_url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        engine_options: dict[str, Any] = {
            "future": True,
            "pool_pre_ping": True,
            "connect_args": connect_args,
        }
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            engine_options["poolclass"] = StaticPool
        self.engine = create_engine(database_url, **engine_options)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.session_ttl_seconds = session_ttl_seconds
        self._initialized = False
        self._initialize_lock = Lock()

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            Base.metadata.create_all(self.engine)
            if self.engine.dialect.name == "mssql":
                self._migrate_sql_server_schema()
            self._initialized = True

    def _migrate_sql_server_schema(self) -> None:
        with self.engine.begin() as connection:
            nullable_unique_constraints = connection.execute(
                text(
                    """
                    SELECT SCHEMA_NAME(t.schema_id) AS schema_name, kc.name AS constraint_name
                    FROM sys.key_constraints AS kc
                    INNER JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
                    INNER JOIN sys.index_columns AS ic
                        ON ic.object_id = t.object_id
                        AND ic.index_id = kc.unique_index_id
                    INNER JOIN sys.columns AS c
                        ON c.object_id = t.object_id
                        AND c.column_id = ic.column_id
                    WHERE kc.[type] = 'UQ'
                        AND t.name = 'messages'
                        AND c.name = 'meta_message_id'
                        AND (
                            SELECT COUNT(*)
                            FROM sys.index_columns AS constraint_columns
                            WHERE constraint_columns.object_id = t.object_id
                                AND constraint_columns.index_id = kc.unique_index_id
                                AND constraint_columns.key_ordinal > 0
                        ) = 1
                    """
                )
            ).all()
            for schema_name, constraint_name in nullable_unique_constraints:
                safe_schema = schema_name.replace("]", "]]")
                safe_constraint = constraint_name.replace("]", "]]")
                connection.execute(
                    text(
                        f"ALTER TABLE [{safe_schema}].[messages] "
                        f"DROP CONSTRAINT [{safe_constraint}]"
                    )
                )

            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1
                        FROM sys.indexes AS i
                        INNER JOIN sys.tables AS t ON t.object_id = i.object_id
                        WHERE t.name = 'messages'
                            AND SCHEMA_NAME(t.schema_id) = 'dbo'
                            AND i.name = 'ux_messages_meta_message_id_not_null'
                    )
                    CREATE UNIQUE INDEX ux_messages_meta_message_id_not_null
                    ON dbo.messages (meta_message_id)
                    WHERE meta_message_id IS NOT NULL
                    """
                )
            )

    def ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_or_create_conversation(self, wa_id: str, display_name: Optional[str] = None) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            contact = db.scalar(select(Contact).where(Contact.wa_id == wa_id))
            if contact is None:
                contact = Contact(wa_id=wa_id, display_name=display_name)
                db.add(contact)
                db.flush()
            elif display_name and contact.display_name != display_name:
                contact.display_name = display_name
                contact.updated_at = utc_now()

            conversation = db.scalar(
                select(Conversation)
                .where(Conversation.contact_id == contact.id, Conversation.status == "active")
                .order_by(Conversation.started_at.desc())
            )
            if conversation is None:
                conversation = Conversation(contact_id=contact.id)
                db.add(conversation)
                db.flush()
            return conversation.id

    def record_message(
        self,
        conversation_id: str,
        direction: str,
        body: Optional[str],
        message_type: str = "text",
        meta_message_id: Optional[str] = None,
        status: str = "received",
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            if meta_message_id:
                existing = db.scalar(select(Message).where(Message.meta_message_id == meta_message_id))
                if existing:
                    return existing.id
            message = Message(
                conversation_id=conversation_id,
                direction=direction,
                body=body,
                message_type=message_type,
                meta_message_id=meta_message_id,
                status=status,
            )
            db.add(message)
            db.flush()
            return message.id

    def update_message_status(
        self,
        meta_message_id: str,
        status: str,
        error_details: Optional[str] = None,
    ) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            message = db.scalar(select(Message).where(Message.meta_message_id == meta_message_id))
            if message is None:
                return False
            message.status = status
            message.error_details = error_details
            return True

    def message_exists(self, meta_message_id: Optional[str]) -> bool:
        if not meta_message_id:
            return False
        self.initialize()
        with self.session_factory() as db:
            return db.scalar(select(Message.id).where(Message.meta_message_id == meta_message_id)) is not None

    def get_session(self, wa_id: str) -> Optional[dict[str, Any]]:
        self.initialize()
        with self.session_factory.begin() as db:
            session = db.scalar(select(ConversationSession).where(ConversationSession.wa_id == wa_id))
            if session is None:
                return None
            if session.expires_at <= utc_now():
                db.delete(session)
                return {"expired": True}
            return {
                "conversation_id": session.conversation_id,
                "state": session.state,
                "context": json.loads(session.context_json or "{}"),
                "expires_at": session.expires_at,
            }

    def save_session(
        self,
        wa_id: str,
        conversation_id: str,
        state: str,
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        self.initialize()
        expires_at = utc_now() + timedelta(seconds=self.session_ttl_seconds)
        context_json = json.dumps(context or {}, default=str)
        with self.session_factory.begin() as db:
            session = db.scalar(select(ConversationSession).where(ConversationSession.wa_id == wa_id))
            if session is None:
                db.add(
                    ConversationSession(
                        wa_id=wa_id,
                        conversation_id=conversation_id,
                        state=state,
                        context_json=context_json,
                        expires_at=expires_at,
                    )
                )
            else:
                session.conversation_id = conversation_id
                session.state = state
                session.context_json = context_json
                session.expires_at = expires_at
                session.updated_at = utc_now()

    def reset_session(self, wa_id: str) -> None:
        self.initialize()
        with self.session_factory.begin() as db:
            session = db.scalar(select(ConversationSession).where(ConversationSession.wa_id == wa_id))
            if session is not None:
                db.delete(session)

    def create_request(
        self,
        conversation_id: str,
        request_type: str,
        payload: dict[str, Any],
        status: str = "pending",
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            request = ServiceRequest(
                conversation_id=conversation_id,
                request_type=request_type,
                payload_json=json.dumps(payload, default=str),
                status=status,
            )
            db.add(request)
            db.flush()
            return request.id

    def create_onboarding_attempt(
        self,
        conversation_id: str,
        selected_service: str,
        journey: str,
        notice_version: str,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            attempt = OnboardingAttempt(
                conversation_id=conversation_id,
                selected_service=selected_service,
                journey=journey,
                notice_version=notice_version,
            )
            db.add(attempt)
            db.flush()
            return attempt.id

    def update_onboarding_attempt(
        self,
        attempt_id: str,
        status: str,
        external_attempt_id: Optional[str] = None,
    ) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            attempt = db.get(OnboardingAttempt, attempt_id)
            if attempt is None:
                return False
            attempt.status = status
            if external_attempt_id:
                attempt.external_attempt_id = external_attempt_id
            attempt.updated_at = utc_now()
            return True

    def save_onboarding_links(
        self,
        conversation_id: str,
        external_profile_id: str,
        links: list[dict[str, Any]],
        profile_status: str = "active",
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                raise ValueError("conversation does not exist")
            profile = db.scalar(select(DigitalProfile).where(DigitalProfile.contact_id == conversation.contact_id))
            if profile is None:
                profile = DigitalProfile(
                    contact_id=conversation.contact_id,
                    external_profile_id=external_profile_id,
                    status=profile_status,
                )
                db.add(profile)
                db.flush()
            else:
                profile.external_profile_id = external_profile_id
                profile.status = profile_status
                profile.updated_at = utc_now()

            for item in links:
                source_id = str(item.get("relationship_id") or item.get("source_relationship_id") or "").strip()
                business = str(item.get("business") or "").strip()
                if not source_id or not business:
                    continue
                link = db.scalar(
                    select(CustomerRelationshipLink).where(
                        CustomerRelationshipLink.profile_id == profile.id,
                        CustomerRelationshipLink.business == business,
                        CustomerRelationshipLink.source_relationship_id == source_id,
                    )
                )
                values = {
                    "masked_reference": str(item.get("masked_reference") or "Masked reference unavailable"),
                    "customer_role": str(item.get("role") or "customer"),
                    "permitted_actions_json": json.dumps(item.get("permitted_actions") or []),
                    "source_status": str(item.get("source_status") or "unknown"),
                    "verification_evidence_reference": item.get("verification_evidence_reference"),
                    "link_status": str(item.get("link_status") or item.get("status") or "unknown"),
                }
                if link is None:
                    db.add(CustomerRelationshipLink(profile_id=profile.id, source_relationship_id=source_id, business=business, **values))
                else:
                    for key, value in values.items():
                        setattr(link, key, value)
                    link.updated_at = utc_now()
            return profile.id

    def get_profile_links(self, wa_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as db:
            rows = db.execute(
                select(CustomerRelationshipLink)
                .join(DigitalProfile, CustomerRelationshipLink.profile_id == DigitalProfile.id)
                .join(Contact, DigitalProfile.contact_id == Contact.id)
                .where(Contact.wa_id == wa_id)
                .order_by(CustomerRelationshipLink.business, CustomerRelationshipLink.masked_reference)
            ).scalars().all()
            return [
                {
                    "business": row.business,
                    "relationship_id": row.source_relationship_id,
                    "masked_reference": row.masked_reference,
                    "role": row.customer_role,
                    "source_status": row.source_status,
                    "link_status": row.link_status,
                }
                for row in rows
            ]

    def update_request_status(
        self,
        request_id: str,
        status: str,
        external_reference: Optional[str] = None,
    ) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            request = db.get(ServiceRequest, request_id)
            if request is None:
                return False
            request.status = status
            if external_reference:
                request.external_reference = external_reference
            request.updated_at = utc_now()
            return True

    def record_permission(
        self,
        conversation_id: str,
        scope: str,
        granted: bool,
        notice_version: str,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            permission = PermissionRecord(
                conversation_id=conversation_id,
                scope=scope,
                granted=granted,
                notice_version=notice_version,
            )
            db.add(permission)
            db.flush()
            return permission.id

    def record_event(
        self,
        event_type: str,
        result_code: str,
        *,
        conversation_id: Optional[str] = None,
        service_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            event = OperationalEvent(
                conversation_id=conversation_id,
                event_type=event_type,
                service_id=service_id,
                result_code=result_code,
                correlation_id=correlation_id,
            )
            db.add(event)
            db.flush()
            return event.id

    def create_satisfaction_response(
        self,
        conversation_id: str,
        journey: str,
        journey_outcome: str,
        resolved: Optional[bool],
        rating: Optional[int],
        comment: Optional[str],
        agent_contact_requested: Optional[bool],
        language: str = "en",
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            response = SatisfactionResponse(
                conversation_id=conversation_id,
                journey=journey[:80],
                journey_outcome=journey_outcome[:32],
                resolved=resolved,
                rating=str(rating) if rating is not None else None,
                comment=comment,
                agent_contact_requested=agent_contact_requested,
                language=language[:8],
            )
            db.add(response)
            db.flush()
            return response.id

    def create_escalation(
        self,
        conversation_id: str,
        category: str,
        details: str,
        assigned_team: Optional[str] = None,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            escalation = Escalation(
                conversation_id=conversation_id,
                category=category,
                details=details,
                assigned_team=assigned_team,
            )
            db.add(escalation)
            db.flush()
            return escalation.id

    def create_transaction(
        self,
        conversation_id: str,
        policy_number: str,
        amount: str,
        payment_method: str,
        status: str,
        external_reference: Optional[str] = None,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            transaction = Transaction(
                conversation_id=conversation_id,
                policy_number=policy_number,
                amount=amount,
                payment_method=payment_method,
                status=status,
                external_reference=external_reference,
            )
            db.add(transaction)
            db.flush()
            return transaction.id

    def update_escalation_status(self, escalation_id: str, status: str) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            escalation = db.get(Escalation, escalation_id)
            if escalation is None:
                return False
            escalation.status = status
            escalation.updated_at = utc_now()
            return True

    def get_escalation_context(self, escalation_id: str) -> Optional[dict[str, str]]:
        self.initialize()
        with self.session_factory() as db:
            row = db.execute(
                select(Escalation, Contact.wa_id)
                .join(Conversation, Escalation.conversation_id == Conversation.id)
                .join(Contact, Conversation.contact_id == Contact.id)
                .where(Escalation.id == escalation_id)
            ).first()
            if row is None:
                return None
            escalation, wa_id = row
            return {
                "escalation_id": escalation.id,
                "conversation_id": escalation.conversation_id,
                "wa_id": wa_id,
                "category": escalation.category,
                "status": escalation.status,
            }

    def get_active_content(self, service_id: str, at: Optional[datetime] = None) -> list[dict[str, Any]]:
        self.initialize()
        effective_at = at or utc_now()
        with self.session_factory() as db:
            records = db.scalars(
                select(ContentRecord)
                .where(
                    ContentRecord.service_id == service_id,
                    ContentRecord.active.is_(True),
                    ContentRecord.approval_state == "approved",
                    ContentRecord.effective_from <= effective_at,
                    (ContentRecord.effective_to.is_(None) | (ContentRecord.effective_to > effective_at)),
                )
                .order_by(ContentRecord.content_type, ContentRecord.version.desc())
            ).all()
            return [
                {
                    "content_id": record.content_id,
                    "service_id": record.service_id,
                    "content_type": record.content_type,
                    "title": record.title,
                    "body": record.body,
                    "version": record.version,
                    "metadata": json.loads(record.metadata_json or "{}"),
                }
                for record in records
            ]

    def update_transaction_status(self, external_reference: str, status: str) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            transaction = db.scalar(
                select(Transaction).where(Transaction.external_reference == external_reference)
            )
            if transaction is None:
                return False
            transaction.status = status
            transaction.updated_at = utc_now()
            return True

    def get_pending_transactions(self) -> list[dict[str, str]]:
        self.initialize()
        with self.session_factory() as db:
            rows = db.execute(
                select(Transaction, Contact.wa_id)
                .join(Conversation, Transaction.conversation_id == Conversation.id)
                .join(Contact, Conversation.contact_id == Contact.id)
                .where(
                    Transaction.status.in_(["pending", "processing"]),
                    Transaction.external_reference.is_not(None),
                )
            ).all()
            return [
                {
                    "conversation_id": transaction.conversation_id,
                    "wa_id": wa_id,
                    "reference": transaction.external_reference or "",
                }
                for transaction, wa_id in rows
            ]

    def create_sales_lead(
        self,
        conversation_id: str,
        source: str,
        product_interest: str,
        details: dict[str, Any],
        *,
        language: str = "en",
        callback_number: Optional[str] = None,
        follow_up_consent: bool = False,
        assigned_team: Optional[str] = None,
        qualification_status: str = "rules_pending",
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            lead = SalesLead(
                conversation_id=conversation_id,
                source=source[:60],
                product_interest=product_interest[:80],
                language=language[:8],
                callback_number=callback_number,
                follow_up_consent=follow_up_consent,
                assigned_team=assigned_team,
                qualification_status=qualification_status,
                details_json=json.dumps(details, default=str),
            )
            db.add(lead)
            db.flush()
            return lead.id

    def create_quote_request(
        self,
        conversation_id: str,
        lead_id: Optional[str],
        product_interest: str,
        requirements: dict[str, Any],
        currency: Optional[str] = None,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            quote = QuoteRequest(
                conversation_id=conversation_id,
                lead_id=lead_id,
                product_interest=product_interest[:80],
                requirements_json=json.dumps(requirements, default=str),
                currency=currency,
                status="pricing_pending",
            )
            db.add(quote)
            db.flush()
            return quote.id

    def get_quote_request(self, quote_id: str, conversation_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as db:
            query = select(QuoteRequest).where(QuoteRequest.id == quote_id)
            if conversation_id:
                query = query.where(QuoteRequest.conversation_id == conversation_id)
            quote = db.scalar(query)
            if quote is None:
                return None
            status = quote.status
            if quote.expires_at and quote.expires_at <= utc_now() and status == "priced":
                status = "expired"
            return {
                "id": quote.id,
                "conversation_id": quote.conversation_id,
                "product_interest": quote.product_interest,
                "status": status,
                "premium_amount": quote.premium_amount,
                "currency": quote.currency,
                "external_reference": quote.external_reference,
                "expires_at": quote.expires_at.isoformat() if quote.expires_at else None,
            }

    def update_quote_pricing(
        self,
        quote_id: str,
        status: str,
        *,
        premium_amount: Optional[str] = None,
        currency: Optional[str] = None,
        external_reference: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            quote = db.get(QuoteRequest, quote_id)
            if quote is None:
                return False
            quote.status = status
            quote.premium_amount = premium_amount
            quote.currency = currency
            quote.external_reference = external_reference
            quote.expires_at = expires_at
            quote.updated_at = utc_now()
            return True

    def accept_quote_request(self, quote_id: str, conversation_id: str) -> bool:
        self.initialize()
        with self.session_factory.begin() as db:
            quote = db.scalar(
                select(QuoteRequest).where(
                    QuoteRequest.id == quote_id,
                    QuoteRequest.conversation_id == conversation_id,
                )
            )
            if quote is None or quote.status != "priced":
                return False
            if quote.expires_at is None or quote.expires_at <= utc_now():
                quote.status = "expired"
                return False
            quote.status = "accepted_pending_application"
            quote.accepted_at = utc_now()
            quote.updated_at = utc_now()
            return True

    def create_application_intent(
        self,
        conversation_id: str,
        product_interest: str,
        consent_notice_version: str,
        *,
        lead_id: Optional[str] = None,
        quote_request_id: Optional[str] = None,
        checklist: Optional[dict[str, Any]] = None,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            intent = ApplicationIntent(
                conversation_id=conversation_id,
                lead_id=lead_id,
                quote_request_id=quote_request_id,
                product_interest=product_interest[:80],
                checklist_json=json.dumps(checklist or {}, default=str),
                consent_notice_version=consent_notice_version,
            )
            db.add(intent)
            db.flush()
            return intent.id

    def create_follow_up(
        self,
        conversation_id: str,
        lead_id: str,
        scenario: str,
        due_at: datetime,
        consent_basis: str,
        *,
        status: str = "awaiting_configuration",
        template_name: Optional[str] = None,
    ) -> str:
        self.initialize()
        with self.session_factory.begin() as db:
            follow_up = FollowUp(
                conversation_id=conversation_id,
                lead_id=lead_id,
                scenario=scenario[:60],
                due_at=due_at,
                consent_basis=consent_basis[:80],
                status=status[:40],
                template_name=template_name,
            )
            db.add(follow_up)
            db.flush()
            return follow_up.id

    def record_payment_event(
        self,
        event_id: str,
        external_reference: str,
        provider_status: str,
    ) -> tuple[bool, bool]:
        """Persist a verified provider event and update a known transaction.

        Returns (created, transaction_matched). Duplicate events are idempotent.
        """
        self.initialize()
        with self.session_factory.begin() as db:
            transaction = db.scalar(
                select(Transaction).where(Transaction.external_reference == external_reference)
            )
            if db.scalar(select(PaymentEvent.id).where(PaymentEvent.event_id == event_id)):
                return False, transaction is not None
            db.add(
                PaymentEvent(
                    event_id=event_id[:160],
                    external_reference=external_reference[:160],
                    provider_status=provider_status[:40],
                    verified=True,
                )
            )
            if transaction is not None:
                transaction.status = provider_status[:32]
                transaction.updated_at = utc_now()
            return True, transaction is not None

    def due_follow_ups(self, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as db:
            rows = db.scalars(
                select(FollowUp)
                .where(
                    FollowUp.due_at <= utc_now(),
                    FollowUp.status.in_(["scheduled", "awaiting_configuration"]),
                )
                .order_by(FollowUp.due_at)
                .limit(limit)
            ).all()
            return [
                {
                    "id": row.id,
                    "scenario": row.scenario,
                    "status": row.status,
                    "due_at": row.due_at.isoformat(),
                    "template_name": row.template_name,
                    "consent_basis": row.consent_basis,
                }
                for row in rows
            ]

    def commercial_metrics(self) -> dict[str, Any]:
        """Return aggregate, non-PII funnel facts; pending is never counted as revenue."""
        self.initialize()
        with self.session_factory() as db:
            def grouped(model: Any) -> dict[str, int]:
                values = db.scalars(select(model.status)).all()
                return {status: values.count(status) for status in sorted(set(values))}

            successful = {"successful", "paid", "completed", "confirmed"}
            transactions = db.scalars(select(Transaction)).all()
            lead_products = db.scalars(select(SalesLead.product_interest)).all()
            verified_revenue = Decimal("0")
            for row in transactions:
                if row.status.lower() not in successful or not row.amount:
                    continue
                try:
                    verified_revenue += Decimal(row.amount)
                except InvalidOperation:
                    continue
            return {
                "leads": grouped(SalesLead),
                "leads_by_product": {
                    value: lead_products.count(value)
                    for value in sorted(set(lead_products))
                },
                "quote_requests": grouped(QuoteRequest),
                "application_intents": grouped(ApplicationIntent),
                "payments": grouped(Transaction),
                "follow_ups": grouped(FollowUp),
                "verified_payment_value": str(verified_revenue),
                "currency": "mixed_or_source_defined",
                "measurement_note": "Only provider-confirmed payment states contribute to value.",
            }

    def get_history(self, wa_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as db:
            contact = db.scalar(select(Contact).where(Contact.wa_id == wa_id))
            if contact is None:
                return []
            conversation = db.scalar(
                select(Conversation)
                .where(Conversation.contact_id == contact.id)
                .order_by(Conversation.started_at.desc())
            )
            if conversation is None:
                return []
            messages = db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            ).all()
            return [
                {
                    "direction": message.direction,
                    "message_type": message.message_type,
                    "body": message.body,
                    "status": message.status,
                    "created_at": message.created_at.isoformat(),
                }
                for message in reversed(messages)
            ]
