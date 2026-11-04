import asyncio
from datetime import datetime, timedelta

from app.config import Settings
from app.database import ChatRepository
from app.workflow import FidelityWorkflowEngine


class CoreTestClient:
    configured = True

    async def verify_customer(self, customer_wa_id, reference, reference_type):
        return True

    async def get_policy_details(self, policy_number, customer_wa_id):
        return {
            "policy_number": policy_number,
            "product_name": "Test Product",
            "status": "Active",
            "premium_amount": "100.00",
        }

    async def get_payment_history(self, policy_number, customer_wa_id):
        return {"payments": [{"date": "2026-10-01", "amount": "100.00", "status": "Paid"}]}

    async def get_claim_status(self, reference, customer_wa_id):
        return {"reference": reference, "status": "In review"}

    async def start_onboarding(self, payload):
        return {
            "attempt_id": "ONB-NEW" if payload["journey"] == "new" else "ONB-100",
            "status": "verified",
            "identity_verified": True,
            "reference_matched": payload["journey"] not in {"new", "forgotten_reference"},
            "authority_verified": payload["journey"] == "representative",
            "existing_customer_found": False,
        }

    async def discover_relationships(self, attempt_id):
        if attempt_id == "ONB-NEW":
            return {"relationships": []}
        return {
            "relationships": [
                {
                    "relationship_id": "REL-1",
                    "business": "FLA",
                    "service": "Life Assurance",
                    "masked_reference": "****4582",
                    "status": "Active",
                    "role": "owner",
                    "eligible": True,
                },
                {
                    "relationship_id": "REL-2",
                    "business": "FLIMAS",
                    "service": "Medical Aid",
                    "masked_reference": "****9011",
                    "status": "Lapsed",
                    "role": "member",
                    "eligible": True,
                },
            ]
        }

    async def link_relationships(self, attempt_id, relationship_ids):
        source = {
            "REL-1": ("FLA", "****4582", "owner", "Active"),
            "REL-2": ("FLIMAS", "****9011", "member", "Lapsed"),
        }
        return {
            "profile_id": "PROFILE-100",
            "profile_status": "active",
            "links": [
                {
                    "relationship_id": relationship_id,
                    "business": source[relationship_id][0],
                    "masked_reference": source[relationship_id][1],
                    "role": source[relationship_id][2],
                    "source_status": source[relationship_id][3],
                    "link_status": "linked",
                    "permitted_actions": ["view"],
                }
                for relationship_id in relationship_ids
            ],
        }

    async def start_payment_verification(self, customer_wa_id, registered_mobile):
        return {"verification_id": "VERIFY-100", "status": "challenge_sent"}

    async def confirm_payment_verification(self, verification_id, code):
        return {
            "verified": code == "123456",
            "customer_name": "Test Customer",
            "policies": [
                {
                    "policy_number": "FLA-123456",
                    "product_name": "Life Assurance",
                    "account_name": "Test Customer",
                    "premium_due": "250.00",
                    "currency": "USD",
                }
            ],
        }

    async def get_payment_eligible_policies(self, verification_id):
        return {"policies": []}



class PaymentTestClient:
    configured = True

    async def initiate_payment(self, payload):
        if payload["payment_method"] == "card":
            return {
                "reference": "PAY-CARD-100",
                "status": "pending",
                "payment_url": "https://payments.example.test/PAY-CARD-100",
                "expires_at": "2026-10-20T14:15:00Z",
            }
        return {"reference": "PAY-100", "status": "pending"}

    async def prepare_payment(self, payload):
        return {
            "preparation_reference": "PREP-100",
            "amount": payload["amount_due"],
            "currency": payload["payment_currency"],
        }

    async def get_payment_status(self, reference):
        return {"reference": reference, "status": "successful"}


class UnconfiguredPaymentTestClient:
    configured = False


class InsureTechTestClient:
    configured = True

    async def list_products(self):
        return [
            {"product_code": "LIFE-01", "name": "Life Protection"},
            {"product_code": "SAVE-02", "name": "Savings Plan"},
        ]

    async def get_product(self, product_code):
        return {
            "product_code": product_code,
            "name": "Life Protection" if product_code == "LIFE-01" else "Savings Plan",
            "description": "Verified product information from InsureTech.",
        }

    async def get_application(self, product_code, application_id):
        return {"application_id": application_id, "product_code": product_code, "status": "under_review"}

    async def request_quote(self, product_code, payload, idempotency_key=None):
        return {
            "quote_id": "QUOTE-100",
            "expires_at": "2026-11-01T12:00:00Z",
            "eligibility_status": "ELIGIBLE",
            "product": {"code": product_code, "name": "Life Protection", "currency": "USD"},
            "lives_assured": payload["lives_assured"],
            "annual_premium": "24.00",
            "total_payout": "2000.00",
        }

    async def create_application(self, product_code, payload, idempotency_key=None):
        return {
            "id": "APP-100",
            "application_number": "FLA-APP-100",
            "status": "DRAFT",
            "product": {"code": product_code},
            "applicant": payload["applicant"],
            "lives_assured": payload["lives_assured"],
        }

    async def submit_application(self, product_code, application_id, payload=None, idempotency_key=None):
        return {
            "id": application_id,
            "application_number": "FLA-APP-100",
            "status": "SUBMITTED",
            "product": {"code": product_code},
        }

    async def list_payment_methods(self):
        return [
            {"code": "ecocash", "name": "EcoCash", "checkout_type": "mobile_money"},
            {"code": "visa", "name": "Visa", "checkout_type": "card"},
        ]

    async def get_payment_status(self, payment_id):
        return {"payment_id": payment_id, "status": "completed"}


def build_engine(
    tmp_path,
    ttl=1800,
    catalogue_v11=False,
    insuretech_client=None,
    payment_client=None,
):
    settings = Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{tmp_path / 'chatbot.db'}",
        SESSION_TTL_SECONDS=ttl,
        MENU_CATALOGUE_V11_ENABLED=catalogue_v11,
        ESCALATION_MATRIX_JSON='{"complaint":"Customer Experience","claims":"Claims"}',
        PAYMENT_METHODS_JSON='{"ecocash":"EcoCash","omari":"O\'mari","innbucks":"InnBucks","bank_transfer":"Bank transfer","card":"Visa / Mastercard"}',
        BANK_TRANSFER_INSTRUCTIONS_JSON=(
            '{"USD":{"bank":"Test Bank","branch":"Test Branch","account_number":"TEST-USD-001"},'
            '"ZiG":{"bank":"Test Bank","branch":"Test Branch","account_number":"TEST-ZIG-001"}}'
        ),
    )
    repository = ChatRepository(settings.DATABASE_URL, settings.SESSION_TTL_SECONDS)
    repository.initialize()
    engine = FidelityWorkflowEngine(
        settings,
        repository,
        CoreTestClient(),
        payment_client or PaymentTestClient(),
        insuretech_client,
    )
    return engine, repository


def send(engine, wa_id, conversation_id, text, user_name=None):
    return asyncio.run(engine.process_message(wa_id, text, conversation_id, user_name))


def start(engine, wa_id, conversation_id, workflow_id):
    return asyncio.run(engine.start_workflow(wa_id, workflow_id, conversation_id))
def test_department_menu_and_direct_route(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234567"
    conversation_id = repository.get_or_create_conversation(wa_id, "Alice")

    main = send(engine, wa_id, conversation_id, "hello", "Alice")
    assert "Protecting what matters most" in main.text
    life = send(engine, wa_id, conversation_id, "1")
    assert "Self Service" in life.text
    life = send(engine, wa_id, conversation_id, "1")
    assert "Explore Life Assurance" in life.text
    products = send(engine, wa_id, conversation_id, "2")
    assert "Vaka Yako" in products.text
    product = send(engine, wa_id, conversation_id, "1.2")
    assert "Endowment & Savings" in product.text
    assert "guarantees" in product.text


def test_secure_policy_lookup_remains_available_by_handoff(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234568"
    conversation_id = repository.get_or_create_conversation(wa_id)

    assert "Secure policy services" in start(engine, wa_id, conversation_id, "policy_enquiry").text
    assert "policy number" in send(engine, wa_id, conversation_id, "1").text.lower()
    result = send(engine, wa_id, conversation_id, "FLA-123456")
    assert "Policy details" in result.text
    assert "Active" in result.text


def test_invalid_input_offers_agent_after_two_attempts(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234569"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    first = send(engine, wa_id, conversation_id, "99")
    assert "numbers shown" in first.text
    second = send(engine, wa_id, conversation_id, "98")
    assert "Agent" in second.text


def test_urgent_bereavement_preempts_current_menu(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234570"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    urgent = send(engine, wa_id, conversation_id, "Someone has died and we need body removal")
    assert "sorry for your loss" in urgent.text
    assert "Toll-free" in urgent.text
    assert "does not confirm dispatch" in urgent.text


def test_enquiry_requires_permission_and_review(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234571"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "2")
    permission = send(engine, wa_id, conversation_id, "1")
    assert "may we share" in permission.text.lower()
    callback = send(engine, wa_id, conversation_id, "yes")
    assert wa_id[-4:] in callback.text
    purpose = send(engine, wa_id, conversation_id, "yes")
    assert "savings goal" in purpose.text
    review = send(engine, wa_id, conversation_id, "Education fund")
    assert "Please review" in review.text
    submitted = send(engine, wa_id, conversation_id, "1")
    assert submitted.escalation_id
    assert submitted.metadata["handover"] is True
    assert submitted.metadata["request_id"]


def test_main_menu_preserves_and_resumes_draft(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234578"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "4")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "1")
    suspended = send(engine, wa_id, conversation_id, "main menu")
    assert "unfinished request" in suspended.text
    resumed = send(engine, wa_id, conversation_id, "resume")
    assert "FLIMAS Corporate Team" in resumed.text


def test_permission_decline_does_not_create_request(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234572"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "3")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "1")
    declined = send(engine, wa_id, conversation_id, "no")
    assert "Flexi Combo" in declined.text


def test_complaint_requires_permission_and_creates_escalation(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234573"
    conversation_id = repository.get_or_create_conversation(wa_id)

    main = send(engine, wa_id, conversation_id, "complaint")
    assert "Welcome to Fidelity" in main.text
    permission = send(engine, wa_id, conversation_id, "complaint")
    assert "May we share" in permission.text
    send(engine, wa_id, conversation_id, "yes")
    reply = send(engine, wa_id, conversation_id, "I have not received a response to my policy request.")
    assert reply.escalation_id
    assert reply.metadata["assigned_team"] == "Customer Experience"
    assert reply.metadata["share_context"] is True


def test_human_takeover_suppresses_bot_reply(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234574"
    conversation_id = repository.get_or_create_conversation(wa_id)
    repository.save_session(wa_id, conversation_id, "human_takeover", {"escalation_id": "ESC-1"})

    reply = send(engine, wa_id, conversation_id, "menu")
    assert reply.metadata["suppress_send"] is True


def test_payment_capture_confirmation_and_status(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234575"
    conversation_id = repository.get_or_create_conversation(wa_id)

    start(engine, wa_id, conversation_id, "payments")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "+263771234575")
    profile = send(engine, wa_id, conversation_id, "123456")
    assert "Test Customer" in profile.text
    send(engine, wa_id, conversation_id, "6")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    confirmation = send(engine, wa_id, conversation_id, "+263771234575")
    assert "Please confirm" in confirmation.text
    submitted = send(engine, wa_id, conversation_id, "confirm")
    assert "PAY-100" in submitted.text
    assert "DONE" in submitted.text
    completed = send(engine, wa_id, conversation_id, "DONE")
    assert "Payment successful" in completed.text

    start(engine, wa_id, conversation_id, "payments")
    send(engine, wa_id, conversation_id, "3")
    status_reply = send(engine, wa_id, conversation_id, "PAY-100")
    assert "successful" in status_reply.text


def test_session_expiry(tmp_path):
    engine, repository = build_engine(tmp_path, ttl=-1)
    wa_id = "263771234576"
    conversation_id = repository.get_or_create_conversation(wa_id)
    repository.save_session(wa_id, conversation_id, "life_menu", {})
    expired = send(engine, wa_id, conversation_id, "1")
    assert "session has expired" in expired.text


def test_message_persistence_permissions_events_and_history(tmp_path):
    _, repository = build_engine(tmp_path)
    wa_id = "263771234577"
    conversation_id = repository.get_or_create_conversation(wa_id, "Test User")
    first_id = repository.record_message(conversation_id, "inbound", "hello", meta_message_id="wamid.1")
    duplicate_id = repository.record_message(conversation_id, "inbound", "hello", meta_message_id="wamid.1")
    repository.record_message(conversation_id, "outbound", "Welcome", status="sent")
    permission_id = repository.record_permission(conversation_id, "test", True, "v1")
    event_id = repository.record_event("test_event", "ok", conversation_id=conversation_id)
    history = repository.get_history(wa_id)
    assert first_id == duplicate_id
    assert repository.message_exists("wamid.1") is True
    assert permission_id
    assert event_id
    assert [item["direction"] for item in history] == ["inbound", "outbound"]


def test_existing_customer_onboarding_links_masked_relationships(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234580"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "1")
    services = send(engine, wa_id, conversation_id, "8")
    assert "Wealth Management" in services.text
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "63-123456-A-00")
    send(engine, wa_id, conversation_id, "FLA-123456")
    relationships = send(engine, wa_id, conversation_id, "yes")
    assert "****4582" in relationships.text
    assert "****9011" in relationships.text
    review = send(engine, wa_id, conversation_id, "A")
    assert "Review onboarding" in review.text
    complete = send(engine, wa_id, conversation_id, "1")
    assert "digital profile is ready" in complete.text
    assert "issue resolved" in complete.text
    links = repository.get_profile_links(wa_id)
    assert len(links) == 2
    assert {link["source_status"] for link in links} == {"Active", "Lapsed"}


def test_new_customer_can_complete_profile_without_existing_relationship(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234581"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "onboard")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "onboard")
    send(engine, wa_id, conversation_id, "4")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "continue")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "Zimbabwe")
    send(engine, wa_id, conversation_id, "P1234567")
    no_relationship = send(engine, wa_id, conversation_id, "yes")
    assert "without linking" in no_relationship.text
    review = send(engine, wa_id, conversation_id, "skip")
    assert "No existing account" in review.text
    complete = send(engine, wa_id, conversation_id, "1")
    assert "digital profile is ready" in complete.text


def test_personalized_english_only_entry_and_stale_language_session_recovery(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234590"
    conversation_id = repository.get_or_create_conversation(wa_id, "Tariro")

    greeting = send(engine, wa_id, conversation_id, "hello", "Tariro")
    assert "Hello Tariro" in greeting.text
    assert "Self Service" in greeting.text
    repository.save_session(wa_id, conversation_id, "language_selection", {"language": "legacy"})
    recovered = send(engine, wa_id, conversation_id, "hello", "Tariro")
    assert repository.get_session(wa_id)["state"] == "main_menu"
    assert "Hello Tariro" in recovered.text


def test_zero_returns_to_a_clean_main_menu_from_any_bot_workflow(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234593"
    conversation_id = repository.get_or_create_conversation(wa_id, "Restart Test")

    greeting = send(engine, wa_id, conversation_id, "hello", "Restart Test")
    assert greeting.text.endswith("0. Main Menu")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    assert repository.get_session(wa_id)["state"] == "life_menu"

    restarted = send(engine, wa_id, conversation_id, "0", "Restart Test")

    session = repository.get_session(wa_id)
    assert session["state"] == "main_menu"
    assert session["context"] == {"language": "en"}
    assert "Welcome to Fidelity Life Assurance Group" in restarted.text
    assert restarted.text.endswith("0. Main Menu")


def test_controlled_questions_use_approved_content_and_route_protected_work(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234591"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "2")
    answer = send(engine, wa_id, conversation_id, "What funeral plans do you have?")
    assert "Beloved Funeral Plans" in answer.text
    assert repository.get_session(wa_id)["state"] == "ask_question"

    secure = send(engine, wa_id, conversation_id, "check my policy status")
    assert "Secure policy services" in secure.text
    assert repository.get_session(wa_id)["state"] == "policy_menu"


def test_completed_question_journey_collects_satisfaction_response(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234592"
    conversation_id = repository.get_or_create_conversation(wa_id)

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "How do I contact Fidelity?")
    survey = send(engine, wa_id, conversation_id, "main menu")
    assert "issue resolved" in survey.text
    assert "rate this conversation" in send(engine, wa_id, conversation_id, "1").text.lower()
    assert "optional comment" in send(engine, wa_id, conversation_id, "5").text.lower()
    assert "agent to contact" in send(engine, wa_id, conversation_id, "Helpful").text.lower()
    thanks = send(engine, wa_id, conversation_id, "2")
    assert "Thank you" in thanks.text


def test_needs_assessment_captures_lead_without_inventing_recommendation(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771239901"
    conversation_id = repository.get_or_create_conversation(wa_id, "Tariro")

    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "1")
    reply = send(engine, wa_id, conversation_id, "10")
    assert "Quote Guidance" in reply.text
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "Protect my family")
    send(engine, wa_id, conversation_id, "4")
    send(engine, wa_id, conversation_id, "Not sure")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "2")
    reply = send(engine, wa_id, conversation_id, "1")

    assert "Needs assessment recorded" in reply.text
    assert "approved suitability rules have not yet been supplied" in reply.text
    assert "No premium" in reply.text
    metrics = repository.commercial_metrics()
    assert metrics["leads"] == {"captured": 1}
    assert metrics["leads_by_product"] == {"funeral": 1}
    assert metrics["follow_ups"] == {"awaiting_configuration": 1}


def test_quote_request_pricing_and_acceptance_lifecycle(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771239902"
    conversation_id = repository.get_or_create_conversation(wa_id, "Lindiwe")
    repository.save_session(
        wa_id,
        conversation_id,
        "commercial_result",
        {
            "language": "en",
            "lead_id": repository.create_sales_lead(
                conversation_id, "test", "life_protection", {"goal": "Protection"}
            ),
            "product_id": "life_protection",
            "team": "Life Assurance",
            "answers": {"currency": "USD"},
        },
    )
    reply = send(engine, wa_id, conversation_id, "1")
    quote_id = reply.metadata["quote_request_id"]
    pending = repository.get_quote_request(quote_id, conversation_id)
    assert pending and pending["status"] == "pricing_pending"
    assert pending["premium_amount"] is None

    assert repository.update_quote_pricing(
        quote_id,
        "priced",
        premium_amount="25.00",
        currency="USD",
        external_reference="AUTH-QUOTE-1",
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    send(engine, wa_id, conversation_id, "Quote Status")
    reply = send(engine, wa_id, conversation_id, quote_id)
    assert "USD 25.00" in reply.text
    reply = send(engine, wa_id, conversation_id, "1")
    assert "issue resolved" in reply.text
    assert repository.get_quote_request(quote_id, conversation_id)["status"] == "accepted_pending_application"
    assert repository.commercial_metrics()["application_intents"] == {"information_pending": 1}


def test_payment_callback_repository_is_idempotent_and_tracks_verified_value(tmp_path):
    _, repository = build_engine(tmp_path)
    conversation_id = repository.get_or_create_conversation("263771239903", "Noma")
    repository.create_transaction(
        conversation_id,
        "POL-100",
        "12.50",
        "mobile_money",
        "pending",
        "PAY-CALLBACK-1",
    )
    assert repository.record_payment_event("EVT-1", "PAY-CALLBACK-1", "successful") == (True, True)
    assert repository.record_payment_event("EVT-1", "PAY-CALLBACK-1", "successful")[0] is False
    metrics = repository.commercial_metrics()
    assert metrics["payments"] == {"successful": 1}
    assert metrics["verified_payment_value"] == "12.50"


def test_wireframe_exposes_seven_businesses_and_life_actions(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234599"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")
    businesses = send(engine, wa_id, conversation_id, "1")
    for label in (
        "Life Assurance", "Employee Benefits", "Funeral Services", "FLIMAS",
        "Financial Services & Loans", "Wealth Management", "Actuarial Services",
    ):
        assert label in businesses.text
    life = send(engine, wa_id, conversation_id, "1")
    for label in (
        "Explore Life Assurance", "View Products", "Get a Quote", "Apply for Cover",
        "Existing Policy", "Make a Payment", "Claims", "Documents", "FAQs",
    ):
        assert label in life.text


def test_agent_contact_menu_opens_contact_details(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234592"
    conversation_id = repository.get_or_create_conversation(wa_id, "Contact Test")
    repository.save_session(wa_id, conversation_id, "agent_menu", {"language": "en"})

    reply = send(engine, wa_id, conversation_id, "2")

    assert repository.get_session(wa_id)["state"] == "contact_details"
    assert "Speak to an Agent" in reply.text


def test_payment_verification_stops_after_three_failed_codes(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234598"
    conversation_id = repository.get_or_create_conversation(wa_id)
    start(engine, wa_id, conversation_id, "payments")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "0771234598")
    assert "Attempts remaining: 2" in send(engine, wa_id, conversation_id, "111111").text
    assert "Attempts remaining: 1" in send(engine, wa_id, conversation_id, "222222").text
    stopped = send(engine, wa_id, conversation_id, "333333")
    assert "No payment was started" in stopped.text
    assert repository.get_session(wa_id)["state"] == "payment_identity_notice"


def test_card_payment_uses_authorised_portal_link(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234597"
    conversation_id = repository.get_or_create_conversation(wa_id)
    start(engine, wa_id, conversation_id, "payments")
    for message in ("2", "1", "0771234597", "123456", "6", "1", "1", "5"):
        reply = send(engine, wa_id, conversation_id, message)
    assert "Card details are handled" in reply.text
    portal = send(engine, wa_id, conversation_id, "1")
    assert "https://payments.example.test/PAY-CARD-100" in portal.text
    assert "Never send card numbers" in portal.text
    assert repository.get_session(wa_id)["state"] == "payment_wallet_processing"


def test_bank_transfer_proof_is_pending_finance_verification(tmp_path):
    engine, repository = build_engine(tmp_path)
    wa_id = "263771234596"
    conversation_id = repository.get_or_create_conversation(wa_id)
    start(engine, wa_id, conversation_id, "payments")
    for message in ("2", "1", "0771234596", "123456", "6", "1", "1", "4"):
        reply = send(engine, wa_id, conversation_id, message)
    assert "TEST-USD-001" in reply.text
    assert "not credited until" in reply.text
    send(engine, wa_id, conversation_id, "1")
    submitted = send(engine, wa_id, conversation_id, "__media__:document:MEDIA_PROOF_100")
    assert submitted.escalation_id
    assert "does not confirm" in submitted.text
    assert submitted.metadata["assigned_team"] == "Finance"


def test_menu_catalogue_v11_exposes_six_direct_journeys(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
    )
    wa_id = "263771230101"
    conversation_id = repository.get_or_create_conversation(wa_id, "Tariro")

    reply = send(engine, wa_id, conversation_id, "hello", "Tariro")

    for label in (
        "Explore Insurance Products",
        "Get a Quote / Apply",
        "Track My Application",
        "Premium Payments",
        "Policy & Cover Services",
        "Adviser & Contact Details",
    ):
        assert label in reply.text
    assert [row["id"] for row in reply.interactive["sections"][0]["rows"]] == [
        "1", "2", "3", "4", "5", "6"
    ]


def test_menu_catalogue_v11_uses_authoritative_product_code_and_consent(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
    )
    wa_id = "263771230102"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")

    products = send(engine, wa_id, conversation_id, "1")
    assert "Life Protection" in products.text
    details = send(engine, wa_id, conversation_id, "1")
    assert "Verified product information from InsureTech" in details.text
    assert repository.get_session(wa_id)["context"]["product_code"] == "LIFE-01"
    consent = send(engine, wa_id, conversation_id, "1")
    assert "Do you agree" in consent.text
    declined = send(engine, wa_id, conversation_id, "2")
    assert "No information was submitted" in declined.text
    assert repository.get_session(wa_id)["state"] == "product_detail"


def test_menu_catalogue_v11_product_failure_is_fail_closed(tmp_path):
    engine, repository = build_engine(tmp_path, catalogue_v11=True)
    wa_id = "263771230103"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")

    reply = send(engine, wa_id, conversation_id, "1")

    assert "temporarily unavailable" in reply.text
    assert "No product list has been invented" in reply.text


def test_menu_catalogue_v11_tracking_fails_closed_without_authorisation(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
    )
    wa_id = "263771230104"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")
    prompt = send(engine, wa_id, conversation_id, "3")
    assert "application reference" in prompt.text.lower()

    reply = send(engine, wa_id, conversation_id, "APP-1001")

    assert "not enabled" in reply.text
    assert "No application information was disclosed" in reply.text


def test_insuretech_quote_uses_approved_lives_assured_schema(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
    )
    wa_id = "263771230105"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "1")
    lives_prompt = send(engine, wa_id, conversation_id, "1")
    assert "How many lives" in lives_prompt.text

    quote = send(engine, wa_id, conversation_id, "2")

    assert "Annual premium: USD 24.00" in quote.text
    assert "Total payout: USD 2000.00" in quote.text
    assert "QUOTE-100" in quote.text
    assert repository.get_session(wa_id)["state"] == "quote_result"


def test_insuretech_application_creates_traceable_draft(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
    )
    wa_id = "263771230106"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "1")
    send(engine, wa_id, conversation_id, "2")
    send(engine, wa_id, conversation_id, "1")
    for value in (
        "Tariro",
        "Moyo",
        "08-212-3471R-03",
        "+263771230106",
        "skip",
        "1",
        "Tariro",
        "Moyo",
        "08-212-3471R-03",
        "1990-01-01",
        "self",
    ):
        reply = send(engine, wa_id, conversation_id, value)
    assert "Review application draft" in reply.text

    created = send(engine, wa_id, conversation_id, "1")

    assert "Draft application created" in created.text
    assert "FLA-APP-100" in created.text
    assert "Cover is not active" in created.text
    assert repository.get_session(wa_id)["state"] == "application_result"

    submitted = send(engine, wa_id, conversation_id, "1")
    assert "Application submitted for review" in submitted.text
    assert "does not mean approval" in submitted.text

    tracked = send(engine, wa_id, conversation_id, "2")
    assert "Application status" in tracked.text
    assert "Under Review" in tracked.text


def test_application_allows_applicant_only_and_normalizes_contact_fields(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
    )
    wa_id = "263771230108"
    conversation_id = repository.get_or_create_conversation(wa_id)
    for message in ("hello", "2", "1", "2", "1"):
        send(engine, wa_id, conversation_id, message)

    for value in (
        "Tariro",
        "Moyo-Sibanda",
        "08-212-3471r-03",
        "0771230108",
        "Tariro.Moyo@Example.COM",
    ):
        send(engine, wa_id, conversation_id, value)
    review = send(engine, wa_id, conversation_id, "none")

    assert "Additional assured persons: None" in review.text
    context = repository.get_session(wa_id)["context"]
    assert context["applicant"]["mobile_number"] == "+263 77 123 0108"
    assert context["applicant"]["email"] == "tariro.moyo@example.com"
    assert context["applicant"]["national_id"] == "08-212-3471R-03"
    assert context["lives_assured"] == [
        {
            "first_name": "Tariro",
            "surname": "Moyo-Sibanda",
            "national_id": "08-212-3471R-03",
            "relationship_to_applicant": "self",
        }
    ]


def test_application_validation_rejects_malformed_contact_and_person_data(tmp_path):
    engine, _ = build_engine(tmp_path)

    assert engine._valid_person_name("Tariro Moyo") == "Tariro Moyo"
    assert engine._valid_person_name("12345") is None
    assert engine._valid_national_id("@@@") is None
    assert engine._valid_national_id("08-212-3471r-03") == "08-212-3471R-03"
    assert engine._valid_national_id("63-123456-A-12") is None
    assert engine._valid_application_mobile("0771234567") == "+263 77 123 4567"
    assert engine._valid_application_mobile("+263 78 123 4567") == "+263 78 123 4567"
    assert engine._valid_application_mobile("+263 79 123 4567") == "+263 79 123 4567"
    assert engine._valid_application_mobile("+263 71 234 5678") == "+263 71 234 5678"
    assert engine._valid_application_mobile("+263 73 345 6789") == "+263 73 345 6789"
    assert engine._valid_application_mobile("+263 72 345 6789") is None
    assert engine._valid_application_mobile("12345") is None
    assert engine._valid_email("person@example.com") == "person@example.com"
    assert engine._valid_email("person@example..com") is None


def test_v11_payments_use_insuretech_methods_and_status_when_payment_gateway_is_off(tmp_path):
    engine, repository = build_engine(
        tmp_path,
        catalogue_v11=True,
        insuretech_client=InsureTechTestClient(),
        payment_client=UnconfiguredPaymentTestClient(),
    )
    wa_id = "263771230107"
    conversation_id = repository.get_or_create_conversation(wa_id)
    send(engine, wa_id, conversation_id, "hello")
    menu = send(engine, wa_id, conversation_id, "4")
    assert "View Available Payment Methods" in menu.text

    methods = send(engine, wa_id, conversation_id, "1")
    assert "EcoCash" in methods.text
    assert "Visa" in methods.text

    status_prompt = send(engine, wa_id, conversation_id, "3")
    assert "payment reference" in status_prompt.text.lower()
    status = send(engine, wa_id, conversation_id, "PAY-100")
    assert "completed" in status.text
