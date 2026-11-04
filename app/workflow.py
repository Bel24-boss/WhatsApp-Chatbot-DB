import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.catalog import (
    CATALOGUE_ROUTE_ALIASES,
    DIRECT_ROUTE_STATES,
    DIRECT_ROUTE_STATES_V11,
    ESCALATION_CATEGORIES,
    MAIN_MENU,
    MAIN_MENU_V11,
    MENUS,
    ONBOARDING_SERVICES,
    SELF_SERVICE_MENU,
    SELF_SERVICE_ROUTE_STATES,
    SERVICES,
)
from app.config import Settings
from app.commercial import CommercialRules
from app.database import ChatRepository
from app.knowledge import ApprovedKnowledgeBase
from app.localization import Localizer, SUPPORTED_LANGUAGES
from app.integrations import (
    FidelityCoreClient,
    FidelityPaymentClient,
    InsureTechClient,
    IntegrationResponseError,
    IntegrationUnavailableError,
)


@dataclass
class BotReply:
    text: str
    interactive: Optional[dict[str, Any]] = None
    escalation_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ensure_navigation()

    def ensure_navigation(self) -> "BotReply":
        if self.text:
            self.text = self.text.replace("\n\n0. Main Menu", "").rstrip() + "\n\n0. Main Menu"
        return self


class FidelityWorkflowEngine:
    WORKFLOW_STATES = {
        "main_menu": "main_menu",
        "life_assurance": "life_menu",
        "funeral_services": "funeral_menu",
        "flimas": "flimas_menu",
        "customer_service": "agent_menu",
        "policy_enquiry": "policy_menu",
        "payment_history": "payment_history_number",
        "payments": "payments_menu",
        "claims": "claims_menu",
        "complaints": "escalation_permission",
        "human_agent": "escalation_category",
        "onboarding": "onboarding_service",
        "ask_question": "ask_question",
        "sales_guidance": "commercial_product",
        "quote_status": "quote_status_reference",
        "explore_products": "product_catalog",
        "apply_for_insurance": "application_product_catalog",
        "track_application": "application_tracking_reference",
        "policy_cover_assistance": "policy_cover_menu",
    }

    LEGACY_PARENT_STATES = {
        "policy_menu": "main_menu",
        "policy_details_number": "policy_menu",
        "payment_history_number": "policy_menu",
        "payments_menu": "main_menu",
        "payment_identity_notice": "life_menu",
        "payment_verify_mobile": "payment_identity_notice",
        "payment_verify_code": "payment_verify_mobile",
        "payment_profile_menu": "payment_identity_notice",
        "payment_policy_select": "payment_profile_menu",
        "payment_currency": "payment_policy_select",
        "payment_method": "payments_menu",
        "payment_mobile": "payments_menu",
        "payment_confirm": "payments_menu",
        "payment_wallet_processing": "payments_menu",
        "payment_bank_transfer": "payments_menu",
        "payment_pop_waiting": "payments_menu",
        "payment_card_link": "payments_menu",
        "payment_retry": "payments_menu",
        "payment_status_reference": "payments_menu",
        "claims_menu": "main_menu",
        "claim_status_reference": "claims_menu",
        "product_catalog": "main_menu",
        "application_product_catalog": "main_menu",
        "product_detail": "product_catalog",
        "quote_consent": "product_detail",
        "application_consent": "product_detail",
        "quote_lives_assured": "quote_consent",
        "quote_result": "product_detail",
        "application_first_name": "application_consent",
        "application_surname": "application_first_name",
        "application_national_id": "application_surname",
        "application_mobile": "application_national_id",
        "application_email": "application_mobile",
        "application_life_count": "application_email",
        "application_life_first_name": "application_life_count",
        "application_life_surname": "application_life_first_name",
        "application_life_national_id": "application_life_surname",
        "application_life_dob": "application_life_national_id",
        "application_life_relationship": "application_life_dob",
        "application_review": "application_life_relationship",
        "application_result": "main_menu",
        "application_tracking_reference": "main_menu",
        "application_tracking_product": "application_tracking_reference",
        "application_tracking_result": "main_menu",
        "policy_cover_menu": "main_menu",
        "legacy_services_menu": "product_catalog",
    }

    FORM_STATES = {
        "enquiry_permission",
        "enquiry_callback_confirm",
        "enquiry_callback_number",
        "enquiry_field",
        "enquiry_review",
        "escalation_permission",
        "escalation_details",
        "commercial_product",
        "commercial_goal",
        "commercial_household",
        "commercial_budget",
        "commercial_currency",
        "commercial_existing_cover",
        "commercial_consent",
        "commercial_result",
        "quote_status_reference",
        "quote_accept",
        "payment_verify_mobile",
        "payment_verify_code",
        "payment_profile_menu",
        "payment_policy_select",
        "payment_currency",
        "payment_method",
        "payment_mobile",
        "payment_confirm",
        "payment_wallet_processing",
        "payment_bank_transfer",
        "payment_pop_waiting",
        "payment_card_link",
        "payment_retry",
        "quote_consent",
        "application_consent",
        "quote_lives_assured",
        "application_first_name",
        "application_surname",
        "application_national_id",
        "application_mobile",
        "application_email",
        "application_life_count",
        "application_life_first_name",
        "application_life_surname",
        "application_life_national_id",
        "application_life_dob",
        "application_life_relationship",
        "application_review",
        "application_tracking_reference",
        "application_tracking_product",
    }

    ONBOARDING_STATES = {
        "onboarding_service",
        "onboarding_journey",
        "onboarding_notice",
        "onboarding_id_type",
        "onboarding_id_country",
        "onboarding_id_number",
        "onboarding_reference",
        "onboarding_contact_confirm",
        "onboarding_relationship_selection",
        "onboarding_link_review",
        "onboarding_complete",
    }

    URGENT_PATTERN = re.compile(
        r"\b(bereavement|body removal|someone (has )?died|death|funeral emergency|urgent funeral)\b",
        re.IGNORECASE,
    )
    SENSITIVE_PATTERN = re.compile(r"\b(password|passcode|pin|otp|one[- ]time code|cvv)\b", re.IGNORECASE)

    def __init__(
        self,
        settings: Settings,
        repository: ChatRepository,
        core_client: FidelityCoreClient,
        payment_client: FidelityPaymentClient,
        insuretech_client: Optional[InsureTechClient] = None,
    ):
        self.settings = settings
        self.repository = repository
        self.core_client = core_client
        self.payment_client = payment_client
        self.insuretech_client = insuretech_client
        self.localizer = Localizer(settings.LANGUAGE_CATALOG_PATH)
        self.knowledge = ApprovedKnowledgeBase(
            settings.APPROVED_KNOWLEDGE_PATH,
            settings.KNOWLEDGE_MATCH_THRESHOLD,
        )
        self.commercial_rules = CommercialRules(settings.COMMERCIAL_RULES_PATH)
        try:
            templates = json.loads(settings.FOLLOW_UP_TEMPLATES_JSON or "{}")
            self.follow_up_templates = templates if isinstance(templates, dict) else {}
        except json.JSONDecodeError:
            self.follow_up_templates = {}
        try:
            matrix = json.loads(getattr(settings, "ESCALATION_MATRIX_JSON", "{}") or "{}")
            self.escalation_matrix = matrix if isinstance(matrix, dict) else {}
        except json.JSONDecodeError:
            self.escalation_matrix = {}
        try:
            payment_methods = json.loads(settings.PAYMENT_METHODS_JSON or "{}")
            self.payment_methods = payment_methods if isinstance(payment_methods, dict) else {}
        except json.JSONDecodeError:
            self.payment_methods = {}
        aliases = {"bank_card": "card", "visa_mastercard": "card", "mobile_money": "ecocash"}
        self.payment_methods = {
            aliases.get(str(method_id), str(method_id)): str(label)
            for method_id, label in self.payment_methods.items()
            if str(method_id).strip() and str(label).strip()
        }
        if not self.payment_methods:
            self.payment_methods = {
                "ecocash": "EcoCash",
                "omari": "O'mari",
                "innbucks": "InnBucks",
                "bank_transfer": "Bank Transfer",
                "card": "Visa / Mastercard",
            }
        try:
            bank_instructions = json.loads(settings.BANK_TRANSFER_INSTRUCTIONS_JSON or "{}")
            self.bank_transfer_instructions = bank_instructions if isinstance(bank_instructions, dict) else {}
        except json.JSONDecodeError:
            self.bank_transfer_instructions = {}
        try:
            business_hours = json.loads(settings.BUSINESS_HOURS_JSON or "{}")
            self.business_hours = business_hours if isinstance(business_hours, dict) else {}
        except json.JSONDecodeError:
            self.business_hours = {}

    def _locale(self, context: Optional[dict[str, Any]] = None) -> str:
        return "en"

    def welcome_message(self, user_name: Optional[str] = None, locale: str = "en") -> str:
        greeting = "Hello"
        if user_name:
            greeting += f" {user_name}"
        return f"{greeting}.\n\n{self.localizer.text('welcome', locale)}"

    def _main_menu_text(self, locale: str = "en") -> str:
        return MAIN_MENU_V11 if self.settings.MENU_CATALOGUE_V11_ENABLED else self.localizer.text("welcome", locale)

    def _interactive_menu(
        self,
        button: str,
        rows: list[tuple[str, str]],
        section_title: str = "Available services",
    ) -> dict[str, Any]:
        return {
            "button": button,
            "sections": [
                {
                    "title": section_title[:24],
                    "rows": [{"id": row_id, "title": title[:24]} for row_id, title in rows[:10]],
                }
            ],
        }

    def _main_reply(
        self,
        user_name: Optional[str] = None,
        resume_available: bool = False,
        locale: str = "en",
    ) -> BotReply:
        if self.settings.MENU_CATALOGUE_V11_ENABLED:
            greeting = f"Hello {user_name}.\n\n" if user_name else ""
            text = greeting + MAIN_MENU_V11
        else:
            text = self.welcome_message(user_name, locale)
        if resume_available:
            text += "\n\nYou also have an unfinished request. Type *Resume* to continue it."
        return BotReply(
            text,
            self._interactive_menu(
                self.localizer.text("entry_button", locale),
                (
                    [
                        ("1", "Explore Products"),
                        ("2", "Quote / Apply"),
                        ("3", "Track Application"),
                        ("4", "Premium Payments"),
                        ("5", "Policy & Cover"),
                        ("6", "Adviser / Contacts"),
                    ]
                    if self.settings.MENU_CATALOGUE_V11_ENABLED
                    else [
                        ("1", self.localizer.text("entry_self_service", locale)),
                        ("2", self.localizer.text("entry_ask", locale)),
                        ("3", self.localizer.text("entry_urgent", locale)),
                        ("4", self.localizer.text("entry_agent", locale)),
                    ]
                ),
                self.localizer.text("entry_section", locale),
            ),
        )

    def _product_catalog_unavailable_reply(self, application_mode: bool = False) -> BotReply:
        heading = "Apply for Insurance" if application_mode else "Explore Insurance Products"
        return BotReply(
            f"*{heading}*\n\n"
            "Online product information is temporarily unavailable. No product list has been invented. "
            "You can try again, view other Fidelity services, or speak to an adviser.\n\n"
            "1. Retry\n2. Other Fidelity Services\n3. Speak to an Agent\n4. Main Menu"
        )

    def _product_catalog_reply(
        self,
        products: list[dict[str, Any]],
        application_mode: bool = False,
    ) -> BotReply:
        heading = "📝 *Apply for Insurance*" if application_mode else "💼 *Explore Insurance Products*"
        intro = (
            "Please choose the product you would like to apply for."
            if application_mode
            else "Choose a product to learn more. You can request a quote or apply after viewing its details."
        )
        lines = [heading, "", intro, ""]
        rows: list[tuple[str, str]] = []
        for index, product in enumerate(products, start=1):
            label = self._product_label(product)
            lines.append(f"{index}. {label}")
            rows.append((str(index), label))
        lines.extend(["", "N. Other Fidelity Services", "B. Back", "M. Main Menu", "A. Speak to an Agent"])
        return BotReply("\n".join(lines), self._interactive_menu("Choose a product", rows, "Insurance products"))

    @staticmethod
    def _product_code(product: dict[str, Any]) -> str:
        return str(product.get("product_code") or product.get("code") or product.get("id") or "").strip()

    @staticmethod
    def _product_label(product: dict[str, Any]) -> str:
        return str(product.get("name") or product.get("product_name") or product.get("title") or "Insurance product").strip()

    def _product_detail_reply(self, product: dict[str, Any]) -> BotReply:
        label = self._product_label(product)
        lines = [f"*{label}*"]
        currency = str(product.get("currency") or "").strip()
        price = str(product.get("price_per_life") or "").strip()
        payout = str(product.get("payout_per_life") or "").strip()
        if price:
            lines.extend(["", f"Annual premium per life: {currency} {price}".strip()])
        if payout:
            lines.append(f"Payout per life: {currency} {payout}".strip())
        relationships = product.get("allowed_relationships")
        if isinstance(relationships, list) and relationships:
            lines.append("Allowed relationships: " + ", ".join(str(item) for item in relationships[:10]))
        for key in ("description", "eligibility", "benefits", "terms"):
            value = product.get(key)
            if isinstance(value, str) and value.strip():
                lines.extend(["", value.strip()])
            elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
                lines.extend(["", "\n".join(f"• {item}" for item in value[:8])])
        lines.extend(
            [
                "",
                "What would you like to do next?",
                "",
                "1. Request a Quote",
                "2. Apply for This Product",
                "3. View Other Products",
                "4. Main Menu",
                "5. Speak to an Agent",
            ]
        )
        return BotReply("\n".join(lines))

    @staticmethod
    def _application_review_reply(context: dict[str, Any]) -> BotReply:
        applicant = context.get("applicant") or {}
        lives = context.get("lives_assured") or []
        lines = [
            "*Review application draft*",
            "",
            f"Product: {context.get('product_label', context.get('product_code', 'Selected product'))}",
            f"Applicant: {applicant.get('first_name', '')} {applicant.get('surname', '')}".strip(),
            f"Mobile: {applicant.get('mobile_number', '')}",
            f"Lives assured: {len(lives)}",
        ]
        if context.get("no_additional_lives"):
            lines.append("Additional assured persons: None (applicant only)")
        for index, life in enumerate(lives, start=1):
            lines.append(
                f"{index}. {life.get('first_name', '')} {life.get('surname', '')} "
                f"({life.get('relationship_to_applicant', '')})"
            )
        lines.extend(
            [
                "",
                "This creates a draft application only. Cover is not active until all required "
                "documents, declarations, payment and approvals are completed.",
                "",
                "1. Create draft application",
                "2. Cancel",
                "3. Speak to an Agent",
            ]
        )
        return BotReply("\n".join(lines))

    def _policy_cover_reply(self) -> BotReply:
        return BotReply(
            "📄 *Policy & Cover Services*\n\n"
            "Policy-number allocation and cover activation are available only after Fidelity confirms "
            "the required application, payment, underwriting, approval and authorisation conditions.\n\n"
            "1. Application Policy Number\n2. Cover Activation Help\n"
            "3. Track an Application\n4. Existing Policy Adviser\n5. Main Menu"
        )

    @staticmethod
    def _insuretech_payment_methods_reply(methods: list[dict[str, Any]]) -> BotReply:
        lines = ["💳 *Available Premium Payment Methods*", ""]
        for method in methods[:20]:
            name = str(
                method.get("display_name")
                or method.get("name")
                or method.get("label")
                or method.get("code")
                or "Payment method"
            ).strip()
            checkout = str(method.get("checkout_type") or method.get("type") or "").strip()
            lines.append(f"• {name}" + (f" — {checkout.replace('_', ' ')}" if checkout else ""))
        lines.extend(
            [
                "",
                "These methods are supplied by InsureTech. Payment initiation remains adviser-assisted "
                "until secure policy and customer verification is configured.",
                "",
                "Reply 3 to check a payment status, 4 for help, or 5 for the Main Menu.",
            ]
        )
        return BotReply("\n".join(lines))

    async def _open_product_catalog(
        self,
        wa_id: str,
        conversation_id: str,
        *,
        application_mode: bool = False,
    ) -> BotReply:
        state = "application_product_catalog" if application_mode else "product_catalog"
        context: dict[str, Any] = {"language": "en", "application_mode": application_mode}
        if self.insuretech_client is None or not self.insuretech_client.configured:
            self._save(wa_id, conversation_id, state, context)
            self._record_event(conversation_id, "product_catalog", "integration_unavailable")
            return self._product_catalog_unavailable_reply(application_mode)
        try:
            products = await self.insuretech_client.list_products()
        except (IntegrationUnavailableError, IntegrationResponseError):
            self._save(wa_id, conversation_id, state, context)
            self._record_event(conversation_id, "product_catalog", "retrieval_failed")
            return self._product_catalog_unavailable_reply(application_mode)
        valid_products = [
            product
            for product in products
            if isinstance(product, dict) and self._product_code(product)
        ][:8]
        if not valid_products:
            self._save(wa_id, conversation_id, state, context)
            self._record_event(conversation_id, "product_catalog", "empty")
            return self._product_catalog_unavailable_reply(application_mode)
        context["product_map"] = {
            str(index): self._product_code(product)
            for index, product in enumerate(valid_products, start=1)
        }
        context["product_labels"] = {
            self._product_code(product): self._product_label(product)
            for product in valid_products
        }
        self._save(wa_id, conversation_id, state, context)
        self._record_event(conversation_id, "product_catalog", "displayed")
        return self._product_catalog_reply(valid_products, application_mode)

    async def _open_product_detail(
        self,
        wa_id: str,
        conversation_id: str,
        context: dict[str, Any],
        selection: str,
    ) -> BotReply:
        product_code = str(context.get("product_map", {}).get(selection) or "")
        if not product_code or self.insuretech_client is None or not self.insuretech_client.configured:
            return self._invalid(
                wa_id,
                conversation_id,
                "application_product_catalog" if context.get("application_mode") else "product_catalog",
                context,
                "Please choose one of the displayed products.",
            )
        try:
            product = await self.insuretech_client.get_product(product_code)
        except (IntegrationUnavailableError, IntegrationResponseError):
            return BotReply(
                "Sorry, we cannot retrieve the full details of this product right now. "
                "Type *Back* to try again or *Agent* for assistance."
            )
        if not isinstance(product, dict):
            return BotReply("The product response could not be verified. Type *Back* or *Agent* for assistance.")
        context.update(
            {
                "product_code": product_code,
                "product_label": self._product_label(product),
                "product_allowed_relationships": (
                    product.get("allowed_relationships")
                    if isinstance(product.get("allowed_relationships"), list)
                    else []
                ),
                "product_parent_state": (
                    "application_product_catalog" if context.get("application_mode") else "product_catalog"
                ),
            }
        )
        self._save(wa_id, conversation_id, "product_detail", context)
        self._record_event(conversation_id, "product_detail", "displayed", product_code)
        return self._product_detail_reply(product)

    def _self_service_reply(self, locale: str = "en") -> BotReply:
        return BotReply(
            self.localizer.text("self_service", locale),
            self._interactive_menu(
                self.localizer.text("entry_button", locale),
                [
                    ("1", "Life Assurance"),
                    ("2", "Employee Benefits"),
                    ("3", "Funeral Services"),
                    ("4", "FLIMAS"),
                    ("5", "Financial Services & Loans"),
                    ("6", "Wealth Management"),
                    ("7", "Actuarial Services"),
                    ("8", self.localizer.text("self_service_register", locale)),
                    ("9", self.localizer.text("self_service_contact", locale)),
                    ("10", self._commercial_label(locale)),
                ],
                self.localizer.text("entry_section", locale),
            ),
        )

    def _commercial_label(self, locale: str) -> str:
        return "Needs & Quote Guidance"

    def _commercial_product_reply(self, locale: str) -> BotReply:
        heading = "*Needs & Quote Guidance*\n\nWhat are you interested in?"
        labels = {
            "life_protection": "Life protection",
            "funeral": "Funeral cover",
            "medical_aid": "Medical aid",
            "retirement_savings": "Retirement or savings",
            "property_investment": "Vaka Yako property",
            "employee_benefits": "Employee benefits",
        }
        products = self.commercial_rules.products
        lines, rows = [heading], []
        for index, product in enumerate(products, start=1):
            label = labels.get(str(product.get("id")), str(product.get("label")))
            lines.append(f"{index}. {label}")
            rows.append((str(index), label))
        lines.append("\nType *Quote Status* to check an existing quote request.")
        return BotReply("\n".join(lines), self._interactive_menu("Choose", rows, "Guidance"))

    def _commercial_prompt(self, state: str, locale: str) -> BotReply:
        prompts = {
            "commercial_goal": "What is the main outcome you want? Briefly describe it.",
            "commercial_household": "How many people should the solution consider? Reply with a number from 1 to 20.",
            "commercial_budget": "What monthly budget range should an adviser consider? You may reply *Not sure*. This is not a premium quote.",
            "commercial_currency": "Which currency should be considered?\n\n1. USD\n2. ZiG\n3. Not sure",
            "commercial_existing_cover": "Do you already have similar cover or a plan?\n\n1. Yes\n2. No\n3. Not sure",
            "commercial_consent": "May Fidelity record these needs and use your WhatsApp number for an adviser to follow up?\n\n1. Yes\n2. No",
        }
        return BotReply(prompts.get(state, "Please provide the requested information."))

    def _ask_question_reply(self, locale: str = "en") -> BotReply:
        return BotReply(self.localizer.text("ask_prompt", locale))

    def _survey_reply(
        self,
        wa_id: str,
        conversation_id: str,
        journey: str,
        outcome: str,
        locale: str,
    ) -> BotReply:
        if not self.settings.SATISFACTION_SURVEY_ENABLED:
            self._save(wa_id, conversation_id, "main_menu", {"language": locale})
            return self._main_reply(locale=locale)
        context = {"language": locale, "journey": journey, "journey_outcome": outcome}
        self._save(wa_id, conversation_id, "survey_resolved", context)
        return BotReply(self.localizer.text("survey_resolved", locale))

    def _menu_reply(self, state: str) -> BotReply:
        menu = MENUS[state]
        text = f"*{menu['title']}*\n\n" + "\n".join(menu["lines"])
        rows = [(choice, line.split(". ", 1)[-1]) for choice, line in zip(menu["choices"], menu["lines"])]
        return BotReply(text, self._interactive_menu("Choose an option", rows))

    def _save(self, wa_id: str, conversation_id: str, state: str, context: dict[str, Any]) -> None:
        if "language" not in context:
            session = self.repository.get_session(wa_id)
            existing = session.get("context", {}) if session and not session.get("expired") else {}
            if existing.get("language") in SUPPORTED_LANGUAGES:
                context = {**context, "language": existing["language"]}
            else:
                context = {**context, "language": "en"}
        self.repository.save_session(wa_id, conversation_id, state, context)

    def _record_event(
        self,
        conversation_id: str,
        event_type: str,
        result_code: str,
        service_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        self.repository.record_event(
            event_type,
            result_code,
            conversation_id=conversation_id,
            service_id=service_id,
            correlation_id=correlation_id,
        )

    def _contact_text(self) -> str:
        lines = ["*Fidelity contact details*"]
        if self.settings.HEAD_OFFICE_ADDRESS:
            lines.append(f"Head Office: {self.settings.HEAD_OFFICE_ADDRESS}")
        if self.settings.TOLL_FREE_NUMBER:
            lines.append(f"Toll-free: {self.settings.TOLL_FREE_NUMBER}")
        if self.settings.CUSTOMER_CARE_EMAIL:
            lines.append(f"Email: {self.settings.CUSTOMER_CARE_EMAIL}")
        return "\n".join(lines)

    def _urgent_reply(self) -> BotReply:
        numbers = []
        if self.settings.FUNERAL_EMERGENCY_PHONE:
            numbers.append(self.settings.FUNERAL_EMERGENCY_PHONE)
        if self.settings.TOLL_FREE_NUMBER:
            numbers.append(f"Toll-free: {self.settings.TOLL_FREE_NUMBER}")
        contact_lines = "\n".join(numbers) if numbers else "Type *Agent* for urgent assistance."
        return BotReply(
            "We are sorry for your loss. For immediate funeral assistance, please call:\n"
            f"{contact_lines}\n\n"
            "Fidelity's funeral team can assist with removal, required documents and repatriation enquiries. "
            "A chat request does not confirm dispatch.\n\n"
            "1. Request Urgent Staff Assistance\n2. Back\n3. Main Menu"
        )

    def _service_reply(self, service_id: str) -> BotReply:
        service = SERVICES[service_id]
        if service_id == "2.3":
            return self._urgent_reply()
        approved = self.repository.get_active_content(service_id)
        summary = "\n\n".join(record["body"] for record in approved) if approved else service["summary"]
        return BotReply(f"*{service['title']}*\n\n{summary}\n\n{service['options']}")

    def _link_reply(self, route: str) -> BotReply:
        links = {
            "3.3.1": (self.settings.FLIMAS_MEMBER_URL, "FLIMAS member service", True),
            "3.3.2": (self.settings.FLIMAS_PROVIDER_DIRECTORY_URL, "FLIMAS provider directory", False),
            "android": (self.settings.FLIMAS_ANDROID_URL, "FLIMAS Android app", False),
            "ios": (self.settings.FLIMAS_IOS_URL, "FLIMAS iOS app", False),
        }
        url, label, secure = links[route]
        if not url:
            return BotReply(
                f"The approved {label} link is not currently configured. "
                "Please type *Agent* or use Fidelity's contact details for assistance."
            )
        security = " Sign in on that service; do not send passwords or one-time codes in this chat." if secure else ""
        return BotReply(
            f"Continue to the approved {label}:\n{url}\n\n{security}\n\n"
            "Type *Back* for member services, *Main Menu*, or *Agent*."
        )

    def _service_context(self, service_id: str, subtype: Optional[str] = None) -> dict[str, Any]:
        service = SERVICES[service_id]
        fields = list(service.get("fields", []))
        if subtype == "corporate":
            fields = list(service.get("corporate_fields", [])) + fields
        return {
            "service_id": service_id,
            "team": service["team"],
            "priority": service.get("priority", "routine"),
            "customer_type": subtype,
            "fields": fields,
            "field_index": 0,
            "values": {},
            "permission_granted": False,
        }

    def _review_enquiry(self, context: dict[str, Any]) -> BotReply:
        service = SERVICES[context["service_id"]]
        lines = [
            f"Service: {service['title']}",
            f"Callback number: {context['callback_number']}",
        ]
        if context.get("customer_type"):
            lines.append(f"Customer type: {context['customer_type']}")
        labels = {key: prompt.rstrip("?") for key, prompt in context.get("fields", [])}
        for key, value in context.get("values", {}).items():
            lines.append(f"{labels.get(key, key.replace('_', ' ').title())}: {value}")
        return BotReply(
            "*Please review your request*\n\n"
            + "\n".join(lines)
            + "\n\n1. Submit\n2. Edit\n3. Cancel"
        )

    def _onboarding_service_reply(self) -> BotReply:
        lines = ["*Register or link your Fidelity accounts*", "", "Choose a service:"]
        rows = []
        for choice, (_, label, _) in ONBOARDING_SERVICES.items():
            lines.append(f"{choice}. {label}")
            rows.append((choice, label))
        lines.append("\nPublic information and urgent funeral assistance do not require onboarding.")
        return BotReply("\n".join(lines), self._interactive_menu("Choose a service", rows))

    def _onboarding_journey_reply(self) -> BotReply:
        return BotReply(
            "*How would you like to continue?*\n\n"
            "1. I have an existing policy or account\n"
            "2. I am new\n"
            "3. I cannot find my reference\n"
            "4. I am acting for someone else or an organisation"
        )

    def _onboarding_notice_reply(self, context: dict[str, Any]) -> BotReply:
        return BotReply(
            f"To onboard for {context.get('selected_service_name', 'this service')}, Fidelity will use "
            "your identity, contact and account-reference details to check your record and authority, "
            "find eligible relationships and link only those you approve. Marketing consent is separate.\n\n"
            f"Notice version: {self.settings.CONSENT_NOTICE_VERSION}\n1. Continue\n2. Cancel"
        )

    def _onboarding_support_reply(
        self,
        conversation_id: str,
        context: dict[str, Any],
        reason: str,
    ) -> BotReply:
        context.pop("id_number", None)
        context.pop("reference", None)
        team = f"{context.get('selected_service_name', 'Fidelity')} Onboarding Support"
        escalation_id = self.repository.create_escalation(
            conversation_id,
            "onboarding_recovery",
            reason,
            assigned_team=team,
        )
        if context.get("local_attempt_id"):
            self.repository.update_onboarding_attempt(context["local_attempt_id"], "assisted_review")
        return BotReply(
            "This onboarding request needs staff review. Sending it to assisted support...",
            escalation_id=escalation_id,
            metadata={
                "handover": True,
                "share_context": False,
                "category": "onboarding_recovery",
                "assigned_team": team,
                "success_text": f"Your assisted onboarding case was created. Reference: {escalation_id}",
                "failure_text": f"We could not confirm delivery to support.\n\n{self._contact_text()}",
            },
        )

    async def _submit_onboarding(
        self,
        wa_id: str,
        conversation_id: str,
        context: dict[str, Any],
    ) -> BotReply:
        payload = {
            "channel": "whatsapp",
            "customer_wa_id": wa_id,
            "selected_service": context["selected_service"],
            "journey": context["journey"],
            "identity": {
                "type": context["id_type"],
                "country": context.get("id_country"),
                "value": context["id_number"],
            },
            "reference": context.get("reference"),
            "preferred_contact": wa_id,
            "notice_version": self.settings.CONSENT_NOTICE_VERSION,
        }
        try:
            result = await self.core_client.start_onboarding(payload)
        except (IntegrationUnavailableError, IntegrationResponseError):
            context.pop("id_number", None)
            context.pop("reference", None)
            self.repository.update_onboarding_attempt(context["local_attempt_id"], "service_unavailable")
            self._save(wa_id, conversation_id, "onboarding_notice", context)
            return BotReply(
                "Onboarding verification is temporarily unavailable. No private records were displayed and no "
                "account was linked. Try again later or type *Agent*."
            )

        external_attempt_id = str(result.get("attempt_id") or "").strip()
        context.pop("id_number", None)
        context.pop("reference", None)
        if not external_attempt_id:
            self.repository.update_onboarding_attempt(context["local_attempt_id"], "invalid_response")
            return BotReply("The onboarding result could not be confirmed. No account was linked.")
        context["external_attempt_id"] = external_attempt_id
        outcome = str(result.get("status") or "unknown").lower()
        self.repository.update_onboarding_attempt(context["local_attempt_id"], outcome, external_attempt_id)

        if outcome in {"assisted_review", "recovery_required", "ambiguous", "conflict"}:
            return self._onboarding_support_reply(conversation_id, context, f"Backend outcome: {outcome}")
        if outcome not in {"verified", "approved", "complete", "completed"}:
            self._save(wa_id, conversation_id, "onboarding_notice", context)
            return BotReply(
                "We could not complete onboarding with the details provided. No private records were displayed "
                "and no account was linked. Try again or type *Agent*."
            )
        if result.get("identity_verified") is not True:
            self._save(wa_id, conversation_id, "onboarding_notice", context)
            return BotReply(
                "We could not verify the details provided. No private records were displayed and no account was linked. "
                "Try again or type *Agent*."
            )
        if context["journey"] in {"existing", "representative"} and result.get("reference_matched") is not True:
            return self._onboarding_support_reply(conversation_id, context, "Reference matching requires review.")
        if context["journey"] == "representative" and result.get("authority_verified") is not True:
            return self._onboarding_support_reply(conversation_id, context, "Representative authority requires review.")
        if context["journey"] == "new" and result.get("existing_customer_found") is True:
            return self._onboarding_support_reply(conversation_id, context, "Existing customer record requires recovery.")

        try:
            discovery = await self.core_client.discover_relationships(external_attempt_id)
        except (IntegrationUnavailableError, IntegrationResponseError):
            return BotReply(
                "Your details were verified, but account discovery is temporarily unavailable. "
                "No account was linked. Type *Agent* for assistance."
            )
        relationships = []
        raw_relationships = discovery.get("relationships")
        if isinstance(raw_relationships, list):
            for item in raw_relationships[:9]:
                if not isinstance(item, dict) or item.get("eligible") is not True:
                    continue
                relationship_id = str(item.get("relationship_id") or "").strip()
                if not relationship_id:
                    continue
                relationships.append(
                    {
                        "relationship_id": relationship_id,
                        "business": str(item.get("business") or "Fidelity"),
                        "service": str(item.get("service") or "Account"),
                        "masked_reference": str(item.get("masked_reference") or "****"),
                        "source_status": str(item.get("status") or "Unknown"),
                        "role": str(item.get("role") or "customer"),
                    }
                )
        context["relationships"] = relationships
        self._save(wa_id, conversation_id, "onboarding_relationship_selection", context)
        if not relationships:
            if context["journey"] == "new":
                return BotReply(
                    "No existing eligible relationship was found.\n\n"
                    "Type *Skip* to complete the verified digital profile without linking.\n"
                    "1. Get assistance\n2. Cancel"
                )
            return BotReply(
                "No eligible relationship is available to display. This does not mean that no account exists.\n\n"
                "1. Get assisted matching\n2. Cancel"
            )
        lines = ["*Choose accounts to link*", ""]
        for index, item in enumerate(relationships, start=1):
            lines.append(f"{index}. {item['service']} - {item['masked_reference']} - {item['source_status']}")
        lines.extend(["A. Link all eligible accounts shown", "Type *Skip* to continue without linking"])
        return BotReply("\n".join(lines))

    async def start_workflow(
        self,
        wa_id: str,
        workflow_id: str,
        conversation_id: str,
        context: Optional[dict[str, Any]] = None,
        user_name: Optional[str] = None,
    ) -> BotReply:
        if workflow_id in SERVICES:
            self._save(wa_id, conversation_id, "service_detail", {"service_id": workflow_id})
            return self._service_reply(workflow_id)
        state = self.WORKFLOW_STATES.get(workflow_id)
        if state is None:
            raise ValueError("Unknown workflow identifier")
        next_context = dict(context or {})
        next_context.setdefault("language", "en")
        if workflow_id == "complaints":
            next_context.update({"category": "complaint", "team": "Customer Care / Complaints"})
        self._save(wa_id, conversation_id, state, next_context)
        return self._prompt_for_state(state, user_name, next_context)

    def _prompt_for_state(
        self,
        state: str,
        user_name: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> BotReply:
        context = dict(context or {})
        locale = self._locale(context)
        if state == "language_selection":
            return self._main_reply(user_name, locale="en")
        if state == "main_menu":
            return self._main_reply(user_name, bool(context.get("suspended_draft")), locale)
        if state in {"product_catalog", "application_product_catalog"}:
            return self._product_catalog_unavailable_reply(state == "application_product_catalog")
        if state == "product_detail":
            return BotReply(
                f"*{context.get('product_label', 'Selected product')}*\n\n"
                "1. Request a Quote\n2. Apply for This Product\n3. View Other Products\n"
                "4. Main Menu\n5. Speak to an Agent"
            )
        if state == "quote_consent":
            return BotReply(
                "To prepare your quote, Fidelity needs product-specific information. "
                "Do you agree to share the information you provide for this purpose?\n\n"
                "1. Yes, continue\n2. No, cancel\n3. Speak to an Agent"
            )
        if state == "application_consent":
            return BotReply(
                "Before an insurance application can be created, Fidelity needs approved product-specific "
                "information and your consent to process it.\n\n"
                "1. Yes, continue\n2. No, cancel\n3. Speak to an Agent"
            )
        if state == "quote_lives_assured":
            return BotReply("How many lives should the quote cover? Enter a number from 1 to 100.")
        if state == "quote_result":
            return BotReply("1. Apply for this product\n2. View other products\n3. Main Menu")
        if state == "application_first_name":
            return BotReply("Enter the applicant's first name.")
        if state == "application_surname":
            return BotReply("Enter the applicant's surname.")
        if state == "application_national_id":
            return BotReply(
                "Enter the applicant's Zimbabwe national ID in this format: *08-212-3471R-03*. "
                "Do not send an ID photograph."
            )
        if state == "application_mobile":
            return BotReply(
                "Enter the applicant's Zimbabwe mobile number. Accepted networks and format:\n"
                "Econet: +263 77 123 4567, +263 78 123 4567 or +263 79 123 4567\n"
                "NetOne: +263 71 234 5678\n"
                "Telecel: +263 73 345 6789"
            )
        if state == "application_email":
            return BotReply("Enter the applicant's email address, or type *Skip*.")
        if state == "application_life_count":
            return BotReply(
                "How many people will be assured? Enter 1 to 100. If the applicant is the only "
                "person to be assured, reply *0* or *None*. Beneficiaries are handled separately "
                "after the application stage."
            )
        if state == "application_life_first_name":
            number = len(context.get("lives_assured") or []) + 1
            return BotReply(f"Life {number}: enter the first name.")
        if state == "application_life_surname":
            number = len(context.get("lives_assured") or []) + 1
            return BotReply(f"Life {number}: enter the surname.")
        if state == "application_life_national_id":
            number = len(context.get("lives_assured") or []) + 1
            return BotReply(
                f"Life {number}: enter the Zimbabwe national ID in the format *08-212-3471R-03*, "
                "or type *Skip*. Do not send a photograph."
            )
        if state == "application_life_dob":
            number = len(context.get("lives_assured") or []) + 1
            return BotReply(f"Life {number}: enter the date of birth as YYYY-MM-DD, or type *Skip*.")
        if state == "application_life_relationship":
            number = len(context.get("lives_assured") or []) + 1
            allowed = [
                str(value).strip()
                for value in context.get("product_allowed_relationships") or []
                if str(value).strip()
            ]
            options = f" Allowed values: {', '.join(allowed)}." if allowed else ""
            return BotReply(
                f"Life {number}: enter the relationship to the applicant, for example self, spouse or child."
                + options
            )
        if state == "application_review":
            return self._application_review_reply(context)
        if state == "application_result":
            return BotReply(
                "1. Submit for Review\n2. Track This Application\n"
                "3. View Other Products\n4. Main Menu"
            )
        if state == "application_tracking_reference":
            return BotReply(
                "🔎 *Track an Application*\n\nEnter your application reference. "
                "Do not send passwords, PINs, OTPs or identity-document photographs."
            )
        if state == "application_tracking_product":
            return BotReply("Enter the product code associated with this application, or type *Agent* for assistance.")
        if state == "application_tracking_result":
            return BotReply("1. Check Another Application\n2. Speak to an Agent\n3. Main Menu")
        if state == "policy_cover_menu":
            return self._policy_cover_reply()
        if state == "self_service_menu":
            return self._self_service_reply(locale)
        if state == "ask_question":
            return self._ask_question_reply(locale)
        if state == "commercial_product":
            return self._commercial_product_reply(locale)
        if state.startswith("commercial_"):
            return self._commercial_prompt(state, locale)
        if state == "quote_status_reference":
            return BotReply("Enter your quote-request reference.")
        if state == "quote_accept":
            return BotReply("Reply 1 to accept this priced quote for application follow-up, or 2 to return to the Main Menu.")
        if state == "onboarding_service":
            return self._onboarding_service_reply()
        if state == "onboarding_journey":
            return self._onboarding_journey_reply()
        if state == "onboarding_notice":
            return self._onboarding_notice_reply(context)
        if state == "onboarding_id_type":
            return BotReply("Select your ID type:\n\n1. National ID\n2. Passport\n3. Alternative verification assistance")
        if state == "onboarding_id_country":
            return BotReply("Enter the country that issued your passport.")
        if state == "onboarding_id_number":
            return BotReply("Enter your ID number. Do not send an identity-document photograph.")
        if state == "onboarding_reference":
            return BotReply("Enter the relevant policy, membership, account, loan, investment, or engagement reference.")
        if state == "onboarding_contact_confirm":
            return BotReply("Use this WhatsApp number as the preferred digital-profile contact? Reply *Yes* or *No*.")
        if state in MENUS:
            return self._menu_reply(state)
        if state == "service_detail" and context.get("service_id") in SERVICES:
            return self._service_reply(context["service_id"])
        if state == "policy_menu":
            return BotReply("*Secure policy services*\n\n1. View policy details\n2. View payment history\n3. Policy assistance")
        if state == "payments_menu":
            if self.settings.MENU_CATALOGUE_V11_ENABLED and not self.payment_client.configured:
                return BotReply(
                    "💳 *Premium Payments*\n\n"
                    "1. View Available Payment Methods\n2. Make a Premium Payment\n"
                    "3. Check Payment Status\n4. Receipt / Payment Help\n5. Main Menu"
                )
            return BotReply("*Secure payment services*\n\n1. View payment history\n2. Make a payment\n3. Check payment status\n4. Payment assistance")
        if state == "payment_identity_notice":
            return BotReply(
                "*Make a Payment*\n\nPayments linked to your policy require identity verification. "
                "Verification is performed by Fidelity's approved service; the chatbot does not generate or validate codes locally.\n\n"
                "1. Verify Identity\n2. Back"
            )
        if state == "payment_verify_mobile":
            return BotReply("Enter the mobile number registered on your Fidelity policy, including the country code.")
        if state == "payment_verify_code":
            return BotReply(
                "Enter the verification code sent by Fidelity. The code will be redacted from chat history. "
                "Never disclose passwords, wallet PINs or card security codes."
            )
        if state == "payment_profile_menu":
            return self._payment_profile_reply(context)
        if state == "payment_policy_select":
            return self._payment_policies_reply(context)
        if state == "payment_currency":
            return self._payment_currency_reply(context)
        if state == "payment_method":
            return self._payment_methods_reply()
        if state == "payment_mobile":
            label = self.payment_methods.get(context.get("payment_method", ""), "mobile wallet")
            return BotReply(f"Enter the {label} registered mobile number, including the country code.")
        if state == "payment_confirm":
            return BotReply(
                "Please confirm the payment details shown. Reply *Confirm* to continue or *Back* to change the payment method."
            )
        if state == "payment_wallet_processing":
            return BotReply("Reply *DONE* to check the provider result, or *Cancel* to stop.")
        if state == "payment_pop_waiting":
            return BotReply("Attach a JPG, PNG or PDF proof of payment, or type *Back*.")
        if state == "payment_retry":
            return BotReply("1. Try again\n2. Return to Profile Menu")
        if state == "claims_menu":
            return BotReply("*Secure claim services*\n\n1. Check claim status\n2. Claim assistance\n3. Claim requirements")
        if state in {"policy_details_number", "payment_history_number"}:
            return BotReply("Please enter your policy number.")
        if state == "claim_status_reference":
            return BotReply("Please enter your claim reference number.")
        if state == "payment_status_reference":
            return BotReply("Please enter your payment reference number.")
        if state == "escalation_category":
            return BotReply(
                "Which team do you need?\n\n1. Life Assurance\n2. Funeral Services\n"
                "3. FLIMAS\n4. Complaints\n5. General Customer Care"
            )
        if state == "escalation_permission":
            return BotReply(
                "May we share the relevant conversation context and your WhatsApp contact number "
                "with the selected Fidelity team? Reply *Yes* or *No*."
            )
        if state == "enquiry_permission" and context.get("service_id") in SERVICES:
            return BotReply(
                "May we share your callback details with "
                f"{SERVICES[context['service_id']]['team']}? Reply *Yes* or *No*."
            )
        if state == "enquiry_callback_confirm":
            return BotReply("Use this WhatsApp number as the preferred callback number? Reply *Yes* or *No*.")
        if state == "enquiry_callback_number":
            return BotReply("Enter the preferred callback number, including the country code.")
        if state == "enquiry_field" and context.get("fields"):
            field_index = min(int(context.get("field_index", 0)), len(context["fields"]) - 1)
            return BotReply(context["fields"][field_index][1])
        if state == "enquiry_review" and context.get("callback_number"):
            return self._review_enquiry(context)
        if state == "escalation_details":
            return BotReply("Briefly describe what you need help with. Do not include passwords, PINs or card details.")
        return BotReply("Please provide the requested information.")

    def _invalid(
        self,
        wa_id: str,
        conversation_id: str,
        state: str,
        context: dict[str, Any],
        prompt: str,
    ) -> BotReply:
        attempts = int(context.get("invalid_attempts", 0)) + 1
        context["invalid_attempts"] = attempts
        self._save(wa_id, conversation_id, state, context)
        self._record_event(
            conversation_id,
            "invalid_input",
            "agent_offered" if attempts >= 2 else "retry",
            context.get("service_id"),
        )
        if attempts >= 2:
            return BotReply(f"{prompt}\n\nYou can try again, type *Main Menu*, or type *Agent* for assistance.")
        return BotReply(prompt)

    def _valid_identifier(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-/]{3,39}", value.strip()))

    def _valid_phone(self, value: str) -> Optional[str]:
        normalized = re.sub(r"[^0-9]", "", value)
        return normalized if re.fullmatch(r"[1-9][0-9]{7,14}", normalized) else None

    @staticmethod
    def _valid_person_name(value: str) -> Optional[str]:
        normalized = " ".join(value.strip().split())
        if not 1 <= len(normalized) <= 100 or not any(character.isalpha() for character in normalized):
            return None
        if any(not (character.isalpha() or character in " '-") for character in normalized):
            return None
        return normalized

    @staticmethod
    def _valid_national_id(value: str, *, optional: bool = False) -> Optional[str]:
        del optional  # The format is identical when an assured person's ID is supplied.
        compact = re.sub(r"[\s-]", "", value.strip().upper())
        match = re.fullmatch(r"(\d{2})(\d{3})(\d{4})([A-Z])(\d{2})", compact)
        if match is None:
            return None
        district, sequence_prefix, sequence_suffix, check_letter, origin = match.groups()
        return f"{district}-{sequence_prefix}-{sequence_suffix}{check_letter}-{origin}"

    @staticmethod
    def _valid_email(value: str) -> Optional[str]:
        normalized = value.strip().lower()
        if len(normalized) > 254 or normalized.count("@") != 1:
            return None
        local, domain = normalized.rsplit("@", 1)
        if not local or len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
            return None
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local, re.IGNORECASE):
            return None
        if len(domain) > 253 or "." not in domain:
            return None
        labels = domain.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not re.fullmatch(r"[a-z0-9-]+", label, re.IGNORECASE)
            for label in labels
        ):
            return None
        if len(labels[-1]) < 2 or not labels[-1].isalpha():
            return None
        return normalized

    @staticmethod
    def _valid_application_mobile(value: str) -> Optional[str]:
        digits = re.sub(r"\D", "", value.strip())
        if digits.startswith("0") and len(digits) == 10:
            digits = "263" + digits[1:]
        elif len(digits) == 9 and digits[:2] in {"71", "73", "77", "78", "79"}:
            digits = "263" + digits
        match = re.fullmatch(r"263(71|73|77|78|79)(\d{3})(\d{4})", digits)
        if match is None:
            return None
        prefix, middle, final = match.groups()
        return f"+263 {prefix} {middle} {final}"

    def _valid_payment_mobile(self, value: str) -> Optional[str]:
        normalized = re.sub(r"[^0-9]", "", value)
        if re.fullmatch(r"0[0-9]{9}", normalized):
            normalized = "263" + normalized[1:]
        return normalized if re.fullmatch(r"[1-9][0-9]{7,14}", normalized) else None

    def _integration_failure(self, error: Exception) -> BotReply:
        if isinstance(error, IntegrationResponseError) and error.status_code == 404:
            return BotReply("We could not find a matching record. Check the reference and try again, or type *Agent*.")
        return BotReply("That service is temporarily unavailable. Please try again later or type *Agent* for assistance.")

    def _is_after_hours(self) -> Optional[bool]:
        if not self.business_hours:
            return None
        now = datetime.now(ZoneInfo(self.settings.BUSINESS_TIMEZONE))
        hours = self.business_hours.get(now.strftime("%A").lower())
        if not isinstance(hours, list) or len(hours) != 2:
            return True
        try:
            opening = datetime.strptime(hours[0], "%H:%M").time()
            closing = datetime.strptime(hours[1], "%H:%M").time()
        except (TypeError, ValueError):
            return None
        return not (opening <= now.time() <= closing)

    def _format_policy(self, data: dict[str, Any]) -> str:
        fields = [
            ("Policy number", data.get("policy_number")),
            ("Product", data.get("product_name")),
            ("Status", data.get("status")),
            ("Premium", data.get("premium_amount")),
            ("Frequency", data.get("premium_frequency")),
            ("Next due date", data.get("next_due_date")),
        ]
        lines = [f"{label}: {value}" for label, value in fields if value not in {None, ""}]
        return "*Policy details*\n\n" + ("\n".join(lines) if lines else "Policy information was returned successfully.")

    def _format_payments(self, data: dict[str, Any]) -> str:
        payments = data.get("payments")
        if not isinstance(payments, list) or not payments:
            return "No payment history was returned for this policy."
        lines = ["*Recent payments*"]
        for payment in payments[:10]:
            if isinstance(payment, dict):
                lines.append(
                    f"{payment.get('date', 'Date unavailable')}: "
                    f"{payment.get('amount', 'Amount unavailable')} - "
                    f"{payment.get('status', 'Status unavailable')}"
                )
        return "\n".join(lines)

    def _normalized_payment_policies(self, data: dict[str, Any]) -> list[dict[str, str]]:
        source = data.get("policies")
        if not isinstance(source, list):
            return []
        policies: list[dict[str, str]] = []
        for item in source[:9]:
            if not isinstance(item, dict):
                continue
            policy_number = str(item.get("policy_number") or "").strip()
            product_name = str(item.get("product_name") or "").strip()
            account_name = str(item.get("account_name") or "").strip()
            currency = str(item.get("currency") or "").strip().upper()
            raw_due = str(item.get("premium_due") or item.get("amount_due") or "").strip()
            try:
                due = Decimal(raw_due)
                if due <= 0 or due.as_tuple().exponent < -2:
                    continue
            except (InvalidOperation, ValueError):
                continue
            if not self._valid_identifier(policy_number) or not product_name or currency not in {"USD", "ZIG"}:
                continue
            policies.append(
                {
                    "policy_number": policy_number,
                    "product_name": product_name[:120],
                    "account_name": account_name[:160] or "Verified customer",
                    "premium_due": f"{due:.2f}",
                    "currency": "ZiG" if currency == "ZIG" else "USD",
                }
            )
        return policies

    def _payment_profile_reply(self, context: dict[str, Any]) -> BotReply:
        name = context.get("customer_name") or "Verified Customer"
        return BotReply(
            f"*Welcome, {name}*\n\n"
            "1. View My Policies\n2. My Claims\n3. My Payments\n4. My Documents\n"
            "5. Main Menu\n6. Proceed with Payment\n7. Cancel Payment"
        )

    def _payment_policies_reply(self, context: dict[str, Any]) -> BotReply:
        lines = ["*Make a Payment*", "", "Select a policy:"]
        rows: list[tuple[str, str]] = []
        for index, policy in enumerate(context.get("payment_policies") or [], start=1):
            lines.append(
                f"{index}. {policy['policy_number']} - {policy['product_name']} - "
                f"{policy['currency']} {policy['premium_due']}"
            )
            rows.append((str(index), f"{policy['product_name']} {policy['premium_due']}"))
        lines.append("\nType *Back* to return.")
        return BotReply("\n".join(lines), self._interactive_menu("Select a policy", rows, "Payment policies"))

    def _payment_currency_reply(self, context: dict[str, Any]) -> BotReply:
        policy = context["selected_policy"]
        return BotReply(
            "*Confirm policy details*\n\n"
            f"Policy: {policy['product_name']}\nPolicy number: {policy['policy_number']}\n"
            f"Account name: {policy['account_name']}\n"
            f"Current premium due: {policy['currency']} {policy['premium_due']}\n\n"
            "Select your preferred payment currency:\n\n1. USD\n2. ZiG\n3. Back"
        )

    def _payment_methods_reply(self) -> BotReply:
        lines = ["*Choose a payment method:*", ""]
        rows = []
        for index, (method_id, label) in enumerate(self.payment_methods.items(), start=1):
            lines.append(f"{index}. {label}")
            rows.append((str(index), label))
        lines.append(f"{len(rows) + 1}. Back")
        return BotReply("\n".join(lines), self._interactive_menu("Payment method", rows, "Payment methods"))

    def _payment_result_reply(self, data: dict[str, Any], context: dict[str, Any]) -> BotReply:
        status = str(data.get("status") or "unknown").lower()
        reference = str(data.get("reference") or data.get("transaction_reference") or context.get("payment_reference") or "")
        if status in {"successful", "success", "paid", "completed", "confirmed"}:
            lines = ["*Payment successful*", "", "Your payment was confirmed by the payment provider."]
            values = [
                ("Receipt number", data.get("receipt_number") or reference),
                ("Policy number", context.get("policy_number")),
                ("Amount paid", f"{context.get('currency', '')} {context.get('amount', '')}".strip()),
                ("New account balance", data.get("new_account_balance")),
                ("Next premium due date", data.get("next_premium_due_date")),
            ]
            lines.extend(f"{label}: {value}" for label, value in values if value not in {None, ""})
            receipt_url = str(data.get("receipt_url") or "").strip()
            if receipt_url.startswith("https://"):
                lines.append(f"Receipt: {receipt_url}")
            return BotReply("\n".join(lines), metadata={"payment_reference": reference, "payment_status": status})
        if status in {"failed", "declined", "cancelled", "expired"}:
            return BotReply(
                "*Transaction failed*\n\nThe provider did not confirm the payment. Common causes can include "
                "insufficient funds, an incorrect wallet approval, or a timeout.\n\n"
                "1. Try again\n2. Return to Profile Menu",
                metadata={"payment_reference": reference, "payment_status": status},
            )
        return BotReply(
            "*Payment processing*\n\nThe payment result is not yet confirmed. Do not repeat the payment. "
            f"Reference: {reference or 'Pending assignment'}\n\nReply *DONE* to check again or *Cancel* to stop.",
            metadata={"payment_reference": reference, "payment_status": status},
        )

    async def _submit_payment(
        self,
        wa_id: str,
        conversation_id: str,
        context: dict[str, Any],
        locale: str,
    ) -> BotReply:
        payload = {
            "policy_number": context["policy_number"],
            "amount": context["amount"],
            "currency": context["currency"],
            "payment_method": context["payment_method"],
            "mobile_number": context.get("mobile_number"),
            "preparation_reference": context.get("preparation_reference"),
            "verification_id": context.get("verification_id"),
        }
        data = await self.payment_client.initiate_payment(payload)
        reference = str(data.get("reference") or data.get("transaction_reference") or "").strip()
        status = str(data.get("status") or "pending").lower()
        if not reference:
            raise IntegrationResponseError("Fidelity payment API", 502, "missing transaction reference")
        self.repository.create_transaction(
            conversation_id,
            context["policy_number"],
            context["amount"],
            context["payment_method"],
            status,
            reference,
        )
        context["payment_reference"] = reference
        context["payment_attempts"] = int(context.get("payment_attempts", 0)) + 1
        result = self._payment_result_reply(data, context)
        if status in {"successful", "success", "paid", "completed", "confirmed"}:
            self._save(
                wa_id,
                conversation_id,
                "survey_resolved",
                {"language": locale, "journey": "payment", "journey_outcome": "successful"},
            )
            result.text += "\n\n" + self.localizer.text("survey_resolved", locale)
            return result
        if status in {"failed", "declined", "cancelled", "expired"}:
            self._save(wa_id, conversation_id, "payment_retry", context)
            return result
        redirect_url = str(data.get("redirect_url") or data.get("payment_url") or "").strip()
        if context["payment_method"] == "card":
            if not redirect_url.startswith("https://"):
                raise IntegrationResponseError("Fidelity payment API", 502, "missing secure card-payment URL")
            expiry = str(data.get("expires_at") or "the expiry time shown on the secure portal")
            result.text = (
                "*Secure card payment*\n\nUse the authorised encrypted payment link below. "
                "Never send card numbers, CVV or PINs in WhatsApp.\n\n"
                f"{redirect_url}\n\nLink expiry: {expiry}\n"
                f"Reference: {reference}\n\nAfter completing the portal payment, reply *DONE* to verify the result."
            )
        else:
            method_label = self.payment_methods.get(context["payment_method"], "wallet")
            result.text = (
                f"*Processing {method_label} payment*\n\nAn authorisation request was submitted for "
                f"{context.get('masked_mobile', 'your registered mobile')}. Approve it only in the official "
                "wallet application or USSD interface. Never type your wallet PIN in this chat.\n\n"
                f"Reference: {reference}\n\nReply *DONE* to verify, or *Cancel* to stop."
            )
        self._save(wa_id, conversation_id, "payment_wallet_processing", context)
        result.metadata.update(
            {
                "payment_reference": reference,
                "payment_status": status,
                "manual_status_check": True,
            }
        )
        return result

    def _open_destination(
        self,
        wa_id: str,
        conversation_id: str,
        destination: str,
        context: Optional[dict[str, Any]] = None,
    ) -> BotReply:
        if context is None:
            session = self.repository.get_session(wa_id)
            context = dict(session.get("context", {})) if session and not session.get("expired") else {}
        else:
            context = dict(context)
        locale = self._locale(context)
        if destination in {"product_catalog", "application_product_catalog"}:
            application_mode = destination == "application_product_catalog"
            self._save(
                wa_id,
                conversation_id,
                destination,
                {"language": locale, "application_mode": application_mode},
            )
            return self._product_catalog_unavailable_reply(application_mode)
        if destination in {"application_tracking_reference", "policy_cover_menu"}:
            self._save(wa_id, conversation_id, destination, {"language": locale})
            return self._prompt_for_state(destination, context={"language": locale})
        if destination == "main_menu":
            self._save(wa_id, conversation_id, "main_menu", {"language": locale})
            return self._main_reply(locale=locale)
        if destination == "self_service_menu":
            self._save(wa_id, conversation_id, destination, {"language": locale})
            return self._self_service_reply(locale)
        if destination == "ask_question":
            self._save(wa_id, conversation_id, destination, {"language": locale})
            return self._ask_question_reply(locale)
        if destination == "commercial_product":
            self._save(wa_id, conversation_id, destination, {"language": locale})
            return self._commercial_product_reply(locale)
        if destination == "urgent_assistance":
            self._save(wa_id, conversation_id, "service_detail", {"service_id": "2.3", "language": locale})
            return self._urgent_reply()
        if destination in {"policy_menu", "payments_menu", "claims_menu"}:
            self._save(wa_id, conversation_id, destination, {"language": locale})
            return self._prompt_for_state(destination, context={"language": locale})
        if destination == "payment_identity_notice":
            self._save(wa_id, conversation_id, destination, {"language": locale})
            return self._prompt_for_state(destination, context={"language": locale})
        if destination == "life_apply_start":
            self._save(
                wa_id,
                conversation_id,
                "commercial_goal",
                {
                    "language": locale,
                    "product_id": "life_protection",
                    "product_label": "Life protection",
                    "team": "Life Assurance",
                    "answers": {},
                    "application_requested": True,
                },
            )
            return BotReply(
                "*Apply for Cover - preparation*\n\nThis journey records your needs and application intent. "
                "It does not approve cover or issue a policy.\n\n"
                + self._commercial_prompt("commercial_goal", locale).text
            )
        if destination == "life_documents":
            next_context = {"language": locale, "category": "life_documents", "team": "Life Assurance", "share_context": True}
            self._save(wa_id, conversation_id, "escalation_details", next_context)
            return BotReply(
                "Describe the policy or application document you need. Do not attach identity documents, passwords, PINs or card details."
            )
        if destination == "onboarding_service":
            self._save(wa_id, conversation_id, destination, {})
            return self._onboarding_service_reply()
        if destination in MENUS:
            self._save(wa_id, conversation_id, destination, {})
            return self._menu_reply(destination)
        if destination in SERVICES:
            self._save(wa_id, conversation_id, "service_detail", {"service_id": destination})
            return self._service_reply(destination)
        if destination in {"3.3.1", "3.3.2"}:
            self._save(wa_id, conversation_id, "link_result", {"parent": "flimas_self_service"})
            return self._link_reply(destination)
        if destination == "app_platform":
            self._save(wa_id, conversation_id, "app_platform", {})
            return BotReply("Choose your platform:\n\n1. Android\n2. iOS\n3. Back")
        if destination == "escalation_category":
            self._save(wa_id, conversation_id, destination, context)
            return self._prompt_for_state(destination)
        if destination == "4.2":
            self._save(wa_id, conversation_id, "contact_details", {"language": locale})
            return BotReply(self._contact_text() + "\n\n1. Speak to an Agent\n2. Main Menu")
        raise ValueError(f"Unknown destination: {destination}")

    def _handle_back(
        self,
        wa_id: str,
        conversation_id: str,
        state: str,
        context: dict[str, Any],
    ) -> BotReply:
        if state == "service_detail":
            service = SERVICES.get(context.get("service_id", ""))
            if service:
                parent = service["parent"]
                if parent.startswith("service:"):
                    return self._open_destination(wa_id, conversation_id, parent.split(":", 1)[1])
                return self._open_destination(wa_id, conversation_id, parent)
        if state == "flimas_self_service":
            return self._open_destination(wa_id, conversation_id, "flimas_menu")
        if state == "life_products_menu":
            return self._open_destination(wa_id, conversation_id, "life_menu", context)
        payment_previous = {
            "payment_verify_mobile": "payment_identity_notice",
            "payment_verify_code": "payment_verify_mobile",
            "payment_profile_menu": "payment_identity_notice",
            "payment_policy_select": "payment_profile_menu",
            "payment_currency": "payment_policy_select",
            "payment_method": "payment_currency",
            "payment_mobile": "payment_method",
            "payment_confirm": "payment_method",
            "payment_card_link": "payment_method",
            "payment_bank_transfer": "payment_method",
            "payment_pop_waiting": "payment_bank_transfer",
            "payment_retry": "payment_profile_menu",
        }.get(state)
        if payment_previous:
            self._save(wa_id, conversation_id, payment_previous, context)
            return self._prompt_for_state(payment_previous, context=context)
        if state in {"life_menu", "funeral_menu", "flimas_menu", "agent_menu", "onboarding_service", "commercial_product"}:
            return self._open_destination(wa_id, conversation_id, "self_service_menu", context)
        if state.startswith("commercial_"):
            previous = {
                "commercial_goal": "commercial_product",
                "commercial_household": "commercial_goal",
                "commercial_budget": "commercial_household",
                "commercial_currency": "commercial_budget",
                "commercial_existing_cover": "commercial_currency",
                "commercial_consent": "commercial_existing_cover",
                "commercial_result": "commercial_product",
            }.get(state, "commercial_product")
            self._save(wa_id, conversation_id, previous, context)
            return self._prompt_for_state(previous, context=context)
        if state in {"self_service_menu", "ask_question"}:
            return self._open_destination(wa_id, conversation_id, "main_menu", context)
        if state in self.ONBOARDING_STATES:
            previous = {
                "onboarding_journey": "onboarding_service",
                "onboarding_notice": "onboarding_journey",
                "onboarding_id_type": "onboarding_notice",
                "onboarding_id_country": "onboarding_id_type",
                "onboarding_id_number": "onboarding_id_type",
                "onboarding_reference": "onboarding_id_number",
                "onboarding_contact_confirm": (
                    "onboarding_reference"
                    if context.get("journey") in {"existing", "representative"}
                    else "onboarding_id_number"
                ),
            }.get(state)
            if previous:
                self._save(wa_id, conversation_id, previous, context)
                return self._prompt_for_state(previous, context=context)
            return self._open_destination(wa_id, conversation_id, "main_menu")
        if state == "link_result":
            return self._open_destination(
                wa_id,
                conversation_id,
                context.get("parent", "flimas_self_service"),
            )
        if state == "contact_details":
            return self._open_destination(wa_id, conversation_id, "agent_menu")
        if state == "app_platform":
            return self._open_destination(wa_id, conversation_id, "flimas_self_service")
        if state in self.FORM_STATES and context.get("service_id"):
            if state == "enquiry_review" and context.get("fields"):
                context["field_index"] = max(0, len(context["fields"]) - 1)
                self._save(wa_id, conversation_id, "enquiry_field", context)
                return BotReply(context["fields"][context["field_index"]][1])
            if state == "enquiry_field" and context.get("field_index", 0) > 0:
                context["field_index"] -= 1
                self._save(wa_id, conversation_id, "enquiry_field", context)
                return BotReply(context["fields"][context["field_index"]][1])
            if state in {"enquiry_field", "enquiry_callback_number"}:
                self._save(wa_id, conversation_id, "enquiry_callback_confirm", context)
                return BotReply("Use this WhatsApp number as the preferred callback number? Reply *Yes* or *No*.")
            if state == "enquiry_callback_confirm":
                self._save(wa_id, conversation_id, "enquiry_permission", context)
                return BotReply("May we share your callback details with the selected Fidelity team? Reply *Yes* or *No*.")
            return self._open_destination(wa_id, conversation_id, context["service_id"])
        parent = self.LEGACY_PARENT_STATES.get(state, "main_menu")
        return self._open_destination(wa_id, conversation_id, parent)

    async def process_message(
        self,
        wa_id: str,
        text: str,
        conversation_id: str,
        user_name: Optional[str] = None,
    ) -> BotReply:
        cleaned = (text or "").strip()
        command = cleaned.lower()
        session = self.repository.get_session(wa_id)
        if session and session.get("expired"):
            self._save(wa_id, conversation_id, "main_menu", {})
            menu_text = MAIN_MENU_V11 if self.settings.MENU_CATALOGUE_V11_ENABLED else MAIN_MENU
            return BotReply(f"Your session has expired. Type *Menu* to start again.\n\n{menu_text}")
        state = session["state"] if session else "main_menu"
        context = session["context"] if session else {}
        locale = self._locale(context)
        command = self.localizer.canonical_command(cleaned, locale)
        if command == "b":
            command = "back"
        elif command == "m":
            command = "main menu"

        if state == "language_selection":
            state = "main_menu"
            context = {"language": "en"}
            locale = "en"
            self._save(wa_id, conversation_id, state, context)

        if state == "human_takeover":
            return BotReply("", metadata={"suppress_send": True})

        if command == "0":
            if state in self.ONBOARDING_STATES and context.get("local_attempt_id"):
                self.repository.update_onboarding_attempt(context["local_attempt_id"], "cancelled")
            self._record_event(conversation_id, "main_menu_restart", "completed", state)
            self._save(wa_id, conversation_id, "main_menu", {"language": "en"})
            return self._main_reply(user_name, locale="en")

        if self.URGENT_PATTERN.search(cleaned):
            self._save(
                wa_id,
                conversation_id,
                "service_detail",
                {"service_id": "2.3", "language": locale},
            )
            self._record_event(conversation_id, "urgent_route", "contacts_displayed", "2.3")
            return self._urgent_reply()

        if session is None:
            self._save(wa_id, conversation_id, "main_menu", {"language": "en"})
            return self._main_reply(user_name, locale="en")

        if command in {"main", "main menu", "menu", "home", "start", "hi", "hello", "hey", "fidelity"}:
            if state == "ask_question" and context.get("answer_given"):
                return self._survey_reply(
                    wa_id, conversation_id, "approved_information", "completed", locale
                )
            suspended = None
            if state in self.FORM_STATES:
                suspended = {"state": state, "context": context}
            if state in self.ONBOARDING_STATES and context.get("local_attempt_id"):
                self.repository.update_onboarding_attempt(context["local_attempt_id"], "cancelled")
            next_context = {"language": locale}
            if suspended:
                next_context["suspended_draft"] = suspended
            self._save(wa_id, conversation_id, "main_menu", next_context)
            return self._main_reply(user_name, bool(suspended), locale)
        if command == "resume":
            suspended = context.get("suspended_draft") if state == "main_menu" else None
            if not isinstance(suspended, dict) or not suspended.get("state"):
                return BotReply("There is no unfinished request to resume.\n\n" + self._main_menu_text(locale))
            resumed_context = suspended.get("context") or {}
            self._save(wa_id, conversation_id, suspended["state"], resumed_context)
            return self._prompt_for_state(suspended["state"], user_name, resumed_context)
        if command == "cancel":
            service_id = context.get("service_id")
            if state in self.ONBOARDING_STATES and context.get("local_attempt_id"):
                self.repository.update_onboarding_attempt(context["local_attempt_id"], "cancelled")
            self._record_event(conversation_id, "draft_cancelled", "cancelled", service_id)
            if state in {"quote_consent", "application_consent"}:
                self._save(wa_id, conversation_id, "product_detail", context)
                return self._prompt_for_state("product_detail", context=context)
            if state in {"main_menu", "self_service_menu"}:
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            return self._survey_reply(
                wa_id,
                conversation_id,
                service_id or state,
                "abandoned",
                locale,
            )
        if command == "back":
            if state in {"product_catalog", "application_product_catalog"}:
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            if state == "product_detail":
                return await self._open_product_catalog(
                    wa_id,
                    conversation_id,
                    application_mode=context.get("product_parent_state") == "application_product_catalog",
                )
            return self._handle_back(wa_id, conversation_id, state, context)
        if command in {"agent", "talk to agent"}:
            self._save(wa_id, conversation_id, "escalation_category", {})
            return self._prompt_for_state("escalation_category")
        if command in {"complaint", "complaints"}:
            next_context = {
                "category": "complaint",
                "team": self.escalation_matrix.get("complaint", "Customer Care / Complaints"),
            }
            self._save(wa_id, conversation_id, "escalation_permission", next_context)
            return self._prompt_for_state("escalation_permission")
        if command in {"onboard", "onboarding", "register", "link account", "link accounts"}:
            return self._open_destination(wa_id, conversation_id, "onboarding_service")
        if command == "self service":
            return self._open_destination(wa_id, conversation_id, "self_service_menu", context)
        if command == "ask a question":
            return self._open_destination(wa_id, conversation_id, "ask_question", context)
        if command in {"quote", "needs analysis", "recommendation", "sales guidance"}:
            return self._open_destination(wa_id, conversation_id, "commercial_product", context)
        if command in {"quote status", "check quote", "my quote"}:
            self._save(wa_id, conversation_id, "quote_status_reference", {"language": locale})
            return self._prompt_for_state("quote_status_reference", context={"language": locale})

        if self.settings.MENU_CATALOGUE_V11_ENABLED and command in CATALOGUE_ROUTE_ALIASES:
            destination = CATALOGUE_ROUTE_ALIASES[command]
            if destination == "product_catalog":
                return await self._open_product_catalog(wa_id, conversation_id)
            if destination == "application_product_catalog":
                return await self._open_product_catalog(wa_id, conversation_id, application_mode=True)
            return self._open_destination(wa_id, conversation_id, destination, context)

        if session is None and command.isdigit():
            self._save(wa_id, conversation_id, "main_menu", {})
            return BotReply("Please select from the main menu so we know which options you are viewing.\n\n" + self._main_menu_text(locale))

        if command in SERVICES:
            return self._open_destination(wa_id, conversation_id, command)
        if command == "4.1":
            return self._open_destination(wa_id, conversation_id, "escalation_category")
        if command == "4.2":
            self._save(wa_id, conversation_id, "contact_details", {})
            return BotReply(self._contact_text() + "\n\n1. Speak to an Agent\n2. Main Menu")
        if command in {"3.3.1", "3.3.2"}:
            return self._open_destination(wa_id, conversation_id, command)

        if state == "main_menu":
            routes = DIRECT_ROUTE_STATES_V11 if self.settings.MENU_CATALOGUE_V11_ENABLED else DIRECT_ROUTE_STATES
            destination = routes.get(command)
            if destination is None:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Please reply with one of the numbers shown, type *Menu*, or type *Agent*.",
                )
            if destination == "product_catalog":
                return await self._open_product_catalog(wa_id, conversation_id)
            if destination == "application_product_catalog":
                return await self._open_product_catalog(wa_id, conversation_id, application_mode=True)
            return self._open_destination(wa_id, conversation_id, destination)

        if state in {"product_catalog", "application_product_catalog"}:
            if command == "a":
                return self._open_destination(wa_id, conversation_id, "escalation_category", context)
            if command == "n":
                return self._open_destination(wa_id, conversation_id, "legacy_services_menu", context)
            if command == "2" and not context.get("product_map"):
                return self._open_destination(wa_id, conversation_id, "legacy_services_menu", context)
            if command == "3" and not context.get("product_map"):
                return self._open_destination(wa_id, conversation_id, "escalation_category", context)
            if command == "4" and not context.get("product_map"):
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            if command == "1" and not context.get("product_map"):
                return await self._open_product_catalog(
                    wa_id,
                    conversation_id,
                    application_mode=state == "application_product_catalog",
                )
            return await self._open_product_detail(wa_id, conversation_id, context, command)

        if state == "product_detail":
            if command == "1":
                self._save(wa_id, conversation_id, "quote_consent", context)
                return self._prompt_for_state("quote_consent", context=context)
            if command == "2":
                self._save(wa_id, conversation_id, "application_consent", context)
                return self._prompt_for_state("application_consent", context=context)
            if command == "3":
                return await self._open_product_catalog(
                    wa_id,
                    conversation_id,
                    application_mode=context.get("product_parent_state") == "application_product_catalog",
                )
            if command == "4":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            if command == "5":
                return self._open_destination(wa_id, conversation_id, "escalation_category", context)
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, 3, 4 or 5.")

        if state in {"quote_consent", "application_consent"}:
            if command in {"2", "no", "n"}:
                permission_type = "insuretech_quote" if state == "quote_consent" else "insuretech_application"
                self.repository.record_permission(
                    conversation_id,
                    permission_type,
                    False,
                    self.settings.CONSENT_NOTICE_VERSION,
                )
                self._save(wa_id, conversation_id, "product_detail", context)
                return BotReply("No information was submitted.\n\n" + self._prompt_for_state("product_detail", context=context).text)
            if command == "3":
                return self._open_destination(wa_id, conversation_id, "escalation_category", context)
            if command not in {"1", "yes", "y"}:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2 or 3.")
            permission_type = "insuretech_quote" if state == "quote_consent" else "insuretech_application"
            self.repository.record_permission(
                conversation_id,
                permission_type,
                True,
                self.settings.CONSENT_NOTICE_VERSION,
            )
            self._record_event(
                conversation_id,
                permission_type,
                "consent_recorded",
                context.get("product_code"),
            )
            next_state = "quote_lives_assured" if state == "quote_consent" else "application_first_name"
            if next_state == "application_first_name":
                context["applicant"] = {}
                context["lives_assured"] = []
            self._save(wa_id, conversation_id, next_state, context)
            return self._prompt_for_state(next_state, context=context)

        if state == "quote_lives_assured":
            if not cleaned.isdigit() or not 1 <= int(cleaned) <= 100:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Enter a whole number from 1 to 100.",
                )
            if self.insuretech_client is None or not self.insuretech_client.configured:
                return BotReply("The quotation service is not configured. No quote was submitted. Type *Agent* for help.")
            request_key = str(context.get("quote_idempotency_key") or f"wa-quote-{uuid.uuid4()}")
            context["quote_idempotency_key"] = request_key
            self._save(wa_id, conversation_id, state, context)
            try:
                quote = await self.insuretech_client.request_quote(
                    str(context.get("product_code") or ""),
                    {"lives_assured": int(cleaned)},
                    idempotency_key=request_key,
                )
            except (IntegrationUnavailableError, IntegrationResponseError):
                self._record_event(conversation_id, "insuretech_quote", "submission_failed", context.get("product_code"))
                return BotReply("The quote could not be created right now. No premium has been invented. Please retry or type *Agent*.")
            context["quote"] = quote
            context.pop("quote_idempotency_key", None)
            self._save(wa_id, conversation_id, "quote_result", context)
            self._record_event(conversation_id, "insuretech_quote", "created", context.get("product_code"), quote.get("quote_id"))
            currency = str((quote.get("product") or {}).get("currency") or "")
            status = str(quote.get("eligibility_status") or "UNAVAILABLE").replace("_", " ").title()
            return BotReply(
                "*InsureTech quote*\n\n"
                f"Product: {self._product_label(quote.get('product') or {})}\n"
                f"Lives assured: {quote.get('lives_assured', cleaned)}\n"
                f"Annual premium: {currency} {quote.get('annual_premium', 'Unavailable')}\n"
                f"Total payout: {currency} {quote.get('total_payout', 'Unavailable')}\n"
                f"Eligibility: {status}\n"
                f"Quote reference: {quote.get('quote_id') or 'Not issued'}\n"
                f"Expires: {quote.get('expires_at') or 'Not specified'}\n\n"
                "1. Apply for this product\n2. View other products\n3. Main Menu"
            )

        if state == "quote_result":
            if command == "1":
                context["applicant"] = {}
                context["lives_assured"] = []
                self._save(wa_id, conversation_id, "application_first_name", context)
                return self._prompt_for_state("application_first_name", context=context)
            if command == "2":
                return await self._open_product_catalog(wa_id, conversation_id)
            if command == "3":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2 or 3.")

        if state == "application_first_name":
            name = self._valid_person_name(cleaned)
            if name is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid first name.")
            context.setdefault("applicant", {})["first_name"] = name
            self._save(wa_id, conversation_id, "application_surname", context)
            return self._prompt_for_state("application_surname", context=context)

        if state == "application_surname":
            surname = self._valid_person_name(cleaned)
            if surname is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid surname.")
            context.setdefault("applicant", {})["surname"] = surname
            self._save(wa_id, conversation_id, "application_national_id", context)
            return self._prompt_for_state("application_national_id", context=context)

        if state == "application_national_id":
            national_id = self._valid_national_id(cleaned)
            if national_id is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid national ID number.")
            context.setdefault("applicant", {})["national_id"] = national_id
            self._save(wa_id, conversation_id, "application_mobile", context)
            return self._prompt_for_state("application_mobile", context=context)

        if state == "application_mobile":
            mobile = self._valid_application_mobile(cleaned)
            if mobile is None:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Enter a valid Econet (77/78/79), NetOne (71), or Telecel (73) number, "
                    "for example +263 77 123 4567.",
                )
            context.setdefault("applicant", {})["mobile_number"] = mobile
            self._save(wa_id, conversation_id, "application_email", context)
            return self._prompt_for_state("application_email", context=context)

        if state == "application_email":
            email = None if command == "skip" else self._valid_email(cleaned)
            if command != "skip" and email is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid email address or type *Skip*.")
            if command != "skip":
                context.setdefault("applicant", {})["email"] = email
            self._save(wa_id, conversation_id, "application_life_count", context)
            return self._prompt_for_state("application_life_count", context=context)

        if state == "application_life_count":
            if command in {"0", "none", "no", "applicant only", "self only"}:
                applicant = context.get("applicant") or {}
                context["life_count"] = 1
                context["lives_assured"] = [
                    {
                        "first_name": applicant.get("first_name"),
                        "surname": applicant.get("surname"),
                        "national_id": applicant.get("national_id"),
                        "relationship_to_applicant": "self",
                    }
                ]
                context["no_additional_lives"] = True
                self._save(wa_id, conversation_id, "application_review", context)
                return self._prompt_for_state("application_review", context=context)
            if not cleaned.isdigit() or not 1 <= int(cleaned) <= 100:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Enter a whole number from 1 to 100, or reply 0 / None for applicant only.",
                )
            context["life_count"] = int(cleaned)
            context.pop("no_additional_lives", None)
            context["current_life"] = {}
            self._save(wa_id, conversation_id, "application_life_first_name", context)
            return self._prompt_for_state("application_life_first_name", context=context)

        if state == "application_life_first_name":
            name = self._valid_person_name(cleaned)
            if name is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid first name.")
            context.setdefault("current_life", {})["first_name"] = name
            self._save(wa_id, conversation_id, "application_life_surname", context)
            return self._prompt_for_state("application_life_surname", context=context)

        if state == "application_life_surname":
            surname = self._valid_person_name(cleaned)
            if surname is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid surname.")
            context.setdefault("current_life", {})["surname"] = surname
            self._save(wa_id, conversation_id, "application_life_national_id", context)
            return self._prompt_for_state("application_life_national_id", context=context)

        if state == "application_life_national_id":
            national_id = None if command == "skip" else self._valid_national_id(cleaned, optional=True)
            if command != "skip" and national_id is None:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid national ID or type *Skip*.")
            if command != "skip":
                context.setdefault("current_life", {})["national_id"] = national_id
            self._save(wa_id, conversation_id, "application_life_dob", context)
            return self._prompt_for_state("application_life_dob", context=context)

        if state == "application_life_dob":
            if command != "skip":
                try:
                    date_of_birth = datetime.strptime(cleaned, "%Y-%m-%d").date()
                except ValueError:
                    return self._invalid(wa_id, conversation_id, state, context, "Use YYYY-MM-DD or type *Skip*.")
                if date_of_birth > datetime.now().date() or date_of_birth.year < 1900:
                    return self._invalid(
                        wa_id,
                        conversation_id,
                        state,
                        context,
                        "Enter a valid past date from 1900 onward, or type *Skip*.",
                    )
                context.setdefault("current_life", {})["date_of_birth"] = cleaned
            self._save(wa_id, conversation_id, "application_life_relationship", context)
            return self._prompt_for_state("application_life_relationship", context=context)

        if state == "application_life_relationship":
            allowed = [
                str(value).strip()
                for value in context.get("product_allowed_relationships") or []
                if str(value).strip()
            ]
            canonical = next((value for value in allowed if value.casefold() == cleaned.casefold()), cleaned)
            if not 1 <= len(canonical) <= 50 or (allowed and canonical not in allowed):
                suffix = f" Choose one of: {', '.join(allowed)}." if allowed else ""
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Enter a valid relationship." + suffix,
                )
            current_life = context.setdefault("current_life", {})
            current_life["relationship_to_applicant"] = canonical
            context.setdefault("lives_assured", []).append(dict(current_life))
            context["current_life"] = {}
            if len(context["lives_assured"]) < int(context.get("life_count") or 0):
                next_state = "application_life_first_name"
            else:
                next_state = "application_review"
            self._save(wa_id, conversation_id, next_state, context)
            return self._prompt_for_state(next_state, context=context)

        if state == "application_review":
            if command == "2":
                self._save(wa_id, conversation_id, "product_detail", context)
                return BotReply("The draft was cancelled and nothing was submitted.\n\n" + self._prompt_for_state("product_detail", context=context).text)
            if command == "3":
                return self._open_destination(wa_id, conversation_id, "escalation_category", context)
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2 or 3.")
            if self.insuretech_client is None or not self.insuretech_client.configured:
                return BotReply("The application service is not configured. No application was created. Type *Agent* for help.")
            request_key = str(context.get("application_idempotency_key") or f"wa-application-{uuid.uuid4()}")
            context["application_idempotency_key"] = request_key
            self._save(wa_id, conversation_id, state, context)
            payload = {
                "quote_id": (context.get("quote") or {}).get("quote_id"),
                "source": "whatsapp",
                "source_reference": conversation_id,
                "applicant": context.get("applicant") or {},
                "lives_assured": context.get("lives_assured") or [],
            }
            if not payload["quote_id"]:
                payload.pop("quote_id")
            try:
                application = await self.insuretech_client.create_application(
                    str(context.get("product_code") or ""),
                    payload,
                    idempotency_key=request_key,
                )
            except (IntegrationUnavailableError, IntegrationResponseError):
                self._record_event(conversation_id, "insuretech_application", "submission_failed", context.get("product_code"))
                return BotReply("The draft application could not be created right now. Please retry or type *Agent*. No duplicate will be created when you retry.")
            context["application"] = application
            context.pop("application_idempotency_key", None)
            self._save(wa_id, conversation_id, "application_result", context)
            reference = application.get("application_number") or application.get("id") or "Unavailable"
            self._record_event(conversation_id, "insuretech_application", "draft_created", context.get("product_code"), str(reference))
            return BotReply(
                "*Draft application created*\n\n"
                f"Reference: {reference}\n"
                f"Status: {str(application.get('status') or 'DRAFT').replace('_', ' ').title()}\n\n"
                "Cover is not active. Fidelity must still complete all required documents, declarations, "
                "payment and approval steps.\n\n"
                "1. Submit for Review\n2. Track This Application\n"
                "3. View Other Products\n4. Main Menu"
            )

        if state == "application_result":
            if command == "1":
                application = context.get("application") or {}
                application_id = str(application.get("id") or application.get("application_id") or "").strip()
                product_code = str(context.get("product_code") or "").strip()
                if not application_id or not product_code:
                    return BotReply("The draft is missing its InsureTech identifiers. Type *Agent* for assistance; nothing was submitted.")
                if str(application.get("status") or "").upper() == "SUBMITTED":
                    return BotReply("This application has already been submitted for review.\n\n2. Track This Application\n3. View Other Products\n4. Main Menu")
                request_key = str(context.get("application_submit_idempotency_key") or f"wa-submit-{uuid.uuid4()}")
                context["application_submit_idempotency_key"] = request_key
                self._save(wa_id, conversation_id, state, context)
                try:
                    submitted = await self.insuretech_client.submit_application(
                        product_code,
                        application_id,
                        idempotency_key=request_key,
                    )
                except (IntegrationUnavailableError, IntegrationResponseError):
                    self._record_event(conversation_id, "insuretech_application", "submit_failed", product_code, application_id)
                    return BotReply("The application could not be submitted right now. Please retry or type *Agent*. The same request key will be reused safely.")
                context["application"] = {**application, **submitted}
                context.pop("application_submit_idempotency_key", None)
                self._save(wa_id, conversation_id, state, context)
                self._record_event(conversation_id, "insuretech_application", "submitted", product_code, application_id)
                status = str(submitted.get("status") or "SUBMITTED").replace("_", " ").title()
                return BotReply(
                    "*Application submitted for review*\n\n"
                    f"Reference: {submitted.get('application_number') or application.get('application_number') or application_id}\n"
                    f"Status: {status}\n\n"
                    "Submission does not mean approval and cover is not yet active.\n\n"
                    "2. Track This Application\n3. View Other Products\n4. Main Menu"
                )
            if command == "2":
                application = context.get("application") or {}
                application_id = str(application.get("id") or application.get("application_id") or "").strip()
                product_code = str(context.get("product_code") or "").strip()
                if not application_id or not product_code:
                    return BotReply("This conversation is not linked to a traceable application. Type *Agent* for assistance.")
                try:
                    current = await self.insuretech_client.get_application(product_code, application_id)
                except (IntegrationUnavailableError, IntegrationResponseError):
                    return BotReply("The current application status could not be retrieved. Please retry or type *Agent*.")
                context["application"] = {**application, **current}
                self._save(wa_id, conversation_id, state, context)
                reference = current.get("application_number") or application.get("application_number") or application_id
                status = str(current.get("status") or "Unavailable").replace("_", " ").title()
                return BotReply(f"*Application status*\n\nReference: {reference}\nStatus: {status}\n\n2. Refresh Status\n3. View Other Products\n4. Main Menu")
            if command == "3":
                return await self._open_product_catalog(wa_id, conversation_id)
            if command == "4":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, 3 or 4.")

        if state == "application_tracking_reference":
            if self.SENSITIVE_PATTERN.search(cleaned) or not re.fullmatch(r"[A-Za-z0-9-]{4,100}", cleaned):
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid application reference.")
            if not self.settings.INSURETECH_APPLICATION_TRACKING_ENABLED:
                self._record_event(conversation_id, "application_tracking", "authorization_unavailable")
                return BotReply(
                    "Secure application tracking is not enabled because the customer-authorisation process "
                    "has not yet been approved. No application information was disclosed. Type *Agent* for assistance."
                )
            context["application_id"] = cleaned
            self._save(wa_id, conversation_id, "application_tracking_product", context)
            return self._prompt_for_state("application_tracking_product", context=context)

        if state == "application_tracking_product":
            product_code = cleaned
            application_id = str(context.get("application_id") or "")
            try:
                verified = await self.core_client.verify_customer(wa_id, application_id, "application")
                if not verified:
                    raise IntegrationResponseError("customer verification", 403, "not authorised")
                if self.insuretech_client is None or not self.insuretech_client.configured:
                    raise IntegrationUnavailableError("InsureTech API is not configured")
                application = await self.insuretech_client.get_application(product_code, application_id)
            except (IntegrationUnavailableError, IntegrationResponseError):
                self._record_event(conversation_id, "application_tracking", "not_retrieved")
                return BotReply(
                    "We could not retrieve the application using the details provided. Please check your "
                    "reference or type *Agent* for assistance."
                )
            status_value = str(application.get("status") or "status unavailable")
            self._record_event(conversation_id, "application_tracking", "retrieved", product_code, application_id)
            self._save(wa_id, conversation_id, "application_tracking_result", {"language": locale})
            return BotReply(
                f"*Application status*\n\nReference: {application_id}\nStatus: {status_value}\n\n"
                "1. Check Another Application\n2. Speak to an Agent\n3. Main Menu"
            )

        if state == "application_tracking_result":
            if command == "1":
                self._save(wa_id, conversation_id, "application_tracking_reference", {"language": locale})
                return self._prompt_for_state("application_tracking_reference")
            if command == "2":
                return self._open_destination(wa_id, conversation_id, "escalation_category", context)
            if command == "3":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2 or 3.")

        if state == "self_service_menu":
            destination = SELF_SERVICE_ROUTE_STATES.get(command)
            if destination is None:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Choose a Self Service option from 1 to 10, or type *Back*.",
                )
            return self._open_destination(wa_id, conversation_id, destination, context)

        if state == "commercial_product":
            products = self.commercial_rules.products
            try:
                product = products[int(command) - 1]
            except (ValueError, IndexError):
                return self._invalid(wa_id, conversation_id, state, context, "Choose one of the products shown.")
            context.update(
                {
                    "product_id": str(product.get("id") or "general"),
                    "product_label": str(product.get("label") or "General guidance"),
                    "team": str(product.get("team") or "Customer Care"),
                    "answers": {},
                }
            )
            self._save(wa_id, conversation_id, "commercial_goal", context)
            return self._commercial_prompt("commercial_goal", locale)

        if state == "quote_status_reference":
            if not re.fullmatch(r"[A-Za-z0-9-]{4,80}", cleaned):
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid quote-request reference.")
            quote = self.repository.get_quote_request(cleaned, conversation_id)
            if quote is None:
                return BotReply("No quote request with that reference was found in this conversation. Check it or type *Agent*.")
            if quote["status"] != "priced":
                self._record_event(conversation_id, "quote_status", quote["status"], quote.get("product_interest"), quote["id"])
                return BotReply(
                    f"*Quote request status*\n\nReference: {quote['id']}\nStatus: {quote['status'].replace('_', ' ').title()}\n\n"
                    "No premium or acceptance is available unless an authorised pricing service returns a valid priced quote."
                )
            context["quote_id"] = quote["id"]
            self._save(wa_id, conversation_id, "quote_accept", context)
            return BotReply(
                f"*Priced quote*\n\nReference: {quote['id']}\nPremium: {quote['currency']} {quote['premium_amount']}\n"
                f"Expires: {quote['expires_at']}\n\n1. Accept for application follow-up\n2. Main Menu"
            )

        if state == "quote_accept":
            if command == "2":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 or 2.")
            quote = self.repository.get_quote_request(context.get("quote_id", ""), conversation_id)
            if not quote or not self.repository.accept_quote_request(quote["id"], conversation_id):
                return BotReply("This quote cannot be accepted because it is missing, expired, or no longer in a priced state. Type *Agent* for help.")
            intent_id = self.repository.create_application_intent(
                conversation_id,
                quote["product_interest"],
                self.settings.CONSENT_NOTICE_VERSION,
                quote_request_id=quote["id"],
                checklist={"status": "authorised_application_process_required"},
            )
            self._record_event(conversation_id, "quote_acceptance", "accepted_pending_application", quote["product_interest"], quote["id"])
            return self._survey_reply(wa_id, conversation_id, f"quote_acceptance:{intent_id}", "accepted_pending_application", locale)

        if state == "commercial_goal":
            if self.SENSITIVE_PATTERN.search(cleaned) or not 3 <= len(cleaned) <= 300:
                return self._invalid(wa_id, conversation_id, state, context, "Provide a short goal without passwords, PINs or private account details.")
            context.setdefault("answers", {})["goal"] = cleaned
            self._save(wa_id, conversation_id, "commercial_household", context)
            return self._commercial_prompt("commercial_household", locale)

        if state == "commercial_household":
            if not command.isdigit() or not 1 <= int(command) <= 20:
                return self._invalid(wa_id, conversation_id, state, context, "Reply with a number from 1 to 20.")
            context.setdefault("answers", {})["people_count"] = int(command)
            self._save(wa_id, conversation_id, "commercial_budget", context)
            return self._commercial_prompt("commercial_budget", locale)

        if state == "commercial_budget":
            if self.SENSITIVE_PATTERN.search(cleaned) or not 2 <= len(cleaned) <= 80:
                return self._invalid(wa_id, conversation_id, state, context, "Give a short budget range or reply *Not sure*.")
            context.setdefault("answers", {})["budget_range"] = cleaned
            self._save(wa_id, conversation_id, "commercial_currency", context)
            return self._commercial_prompt("commercial_currency", locale)

        if state == "commercial_currency":
            currency = {"1": "USD", "2": "ZiG", "3": "not_sure"}.get(command)
            if currency is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2 or 3.")
            context.setdefault("answers", {})["currency"] = currency
            self._save(wa_id, conversation_id, "commercial_existing_cover", context)
            return self._commercial_prompt("commercial_existing_cover", locale)

        if state == "commercial_existing_cover":
            existing = {"1": "yes", "2": "no", "3": "not_sure"}.get(command)
            if existing is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2 or 3.")
            context.setdefault("answers", {})["existing_cover"] = existing
            self._save(wa_id, conversation_id, "commercial_consent", context)
            return self._commercial_prompt("commercial_consent", locale)

        if state == "commercial_consent":
            granted = command in {"1", "yes", "y"}
            declined = command in {"2", "no", "n"}
            if not granted and not declined:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 for Yes or 2 for No.")
            self.repository.record_permission(
                conversation_id,
                "commercial_needs_follow_up",
                granted,
                self.settings.CONSENT_NOTICE_VERSION,
            )
            if declined:
                self._record_event(conversation_id, "commercial_assessment", "consent_declined", context.get("product_id"))
                return self._survey_reply(wa_id, conversation_id, "commercial_guidance", "abandoned", locale)
            recommendation = self.commercial_rules.recommend(context.get("answers", {}))
            qualification = "qualified_by_approved_rules" if recommendation else "rules_pending"
            lead_id = self.repository.create_sales_lead(
                conversation_id,
                "whatsapp_needs_assessment",
                context["product_id"],
                context.get("answers", {}),
                language=locale,
                callback_number=wa_id,
                follow_up_consent=True,
                assigned_team=context.get("team"),
                qualification_status=qualification,
            )
            template = self.follow_up_templates.get("needs_assessment")
            follow_status = "scheduled" if self.settings.FOLLOW_UP_ENABLED and template else "awaiting_configuration"
            self.repository.create_follow_up(
                conversation_id,
                lead_id,
                "needs_assessment",
                datetime.utcnow() + timedelta(hours=max(1, self.settings.FOLLOW_UP_WINDOW_HOURS)),
                f"permission:{self.settings.CONSENT_NOTICE_VERSION}",
                status=follow_status,
                template_name=str(template) if template else None,
            )
            context.update({"lead_id": lead_id, "recommendation": recommendation})
            self._record_event(conversation_id, "lead_captured", qualification, context.get("product_id"), lead_id)
            self._save(wa_id, conversation_id, "commercial_result", context)
            if recommendation:
                result = f"Approved rules indicate: {recommendation.get('label')}. An adviser must still confirm eligibility and terms."
            else:
                result = (
                    "Your needs have been recorded. Automated product recommendations are not enabled because "
                    "approved suitability rules have not yet been supplied. No premium or eligibility outcome has been calculated."
                )
            return BotReply(
                f"*Needs assessment recorded*\n\nReference: {lead_id}\n{result}\n\n"
                "1. Request quote preparation\n2. Speak to an adviser\n3. Prepare an application checklist\n4. Main Menu"
            )

        if state == "commercial_result":
            if command == "4":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            if command == "1":
                quote_id = self.repository.create_quote_request(
                    conversation_id,
                    context.get("lead_id"),
                    context.get("product_id", "general"),
                    context.get("answers", {}),
                    context.get("answers", {}).get("currency"),
                )
                escalation_id = self.repository.create_escalation(
                    conversation_id,
                    "quote_request",
                    json.dumps({"quote_request_id": quote_id, "lead_id": context.get("lead_id")}),
                    assigned_team=context.get("team"),
                )
                self._record_event(conversation_id, "quote_request", "pricing_pending", context.get("product_id"), quote_id)
                self._save(wa_id, conversation_id, "survey_resolved", {"language": locale, "journey": "quote_request", "journey_outcome": "pricing_pending"})
                return BotReply(
                    "Submitting the quote-preparation request...",
                    escalation_id=escalation_id,
                    metadata={
                        "handover": True,
                        "share_context": True,
                        "category": "quote_request",
                        "assigned_team": context.get("team"),
                        "lead_id": context.get("lead_id"),
                        "quote_request_id": quote_id,
                        "success_text": f"Your quote request was sent for pricing. Reference: {quote_id}. This is not yet a formal quote and no premium has been calculated.\n\n{self.localizer.text('survey_resolved', locale)}",
                        "failure_text": f"Your quote request was recorded as {quote_id}, but delivery to the adviser system is not confirmed. No premium has been calculated.\n\n{self.localizer.text('survey_resolved', locale)}",
                    },
                )
            if command == "2":
                escalation_id = self.repository.create_escalation(
                    conversation_id,
                    "sales_advice",
                    json.dumps({"lead_id": context.get("lead_id"), "product_interest": context.get("product_id")}),
                    assigned_team=context.get("team"),
                )
                self._save(wa_id, conversation_id, "survey_resolved", {"language": locale, "journey": "sales_advice", "journey_outcome": "submitted"})
                return BotReply(
                    "Connecting you to an adviser...",
                    escalation_id=escalation_id,
                    metadata={
                        "handover": True,
                        "share_context": True,
                        "category": "sales_advice",
                        "assigned_team": context.get("team"),
                        "lead_id": context.get("lead_id"),
                        "success_text": f"Your adviser request has been queued. Reference: {escalation_id}.\n\n{self.localizer.text('survey_resolved', locale)}",
                        "failure_text": f"Your request was recorded as {escalation_id}, but delivery to the adviser system is not confirmed.\n\n{self.localizer.text('survey_resolved', locale)}",
                    },
                )
            if command == "3":
                intent_id = self.repository.create_application_intent(
                    conversation_id,
                    context.get("product_id", "general"),
                    self.settings.CONSENT_NOTICE_VERSION,
                    lead_id=context.get("lead_id"),
                    checklist={"status": "business_confirmation_required"},
                )
                self._record_event(conversation_id, "application_intent", "information_pending", context.get("product_id"), intent_id)
                return BotReply(
                    f"*Application preparation*\n\nReference: {intent_id}\n"
                    "Keep your official identity and contact information available. The authorised adviser must confirm the exact documents, declarations, eligibility and underwriting requirements. Do not send identity-document photographs in this chat.\n\n"
                    "This records your intention only; it is not an application approval or policy issuance.\n\n1. Request quote preparation\n2. Speak to an adviser\n4. Main Menu"
                )
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, 3 or 4.")

        if state == "ask_question":
            if self.SENSITIVE_PATTERN.search(cleaned):
                return BotReply(
                    "For your safety, do not send passwords, PINs, OTPs or card details. "
                    "Ask a general question or type *Agent*."
                )
            protected_routes = [
                (r"\b(my policy|policy details|policy status|check policy)\b", "policy_menu"),
                (r"\b(my claim|claim status|check claim)\b", "claims_menu"),
                (r"\b(make a payment|pay premium|payment status|payment history)\b", "payments_menu"),
                (r"\b(link (my )?account|register (my )?account)\b", "onboarding_service"),
            ]
            for pattern, destination in protected_routes:
                if re.search(pattern, command):
                    self._record_event(conversation_id, "question_route", "protected_workflow", destination)
                    return self._open_destination(wa_id, conversation_id, destination, context)
            match = self.knowledge.answer(cleaned, locale)
            if match is None:
                self._record_event(conversation_id, "knowledge_query", "no_confident_match")
                return BotReply(self.localizer.text("ask_no_match", locale))
            self._record_event(
                conversation_id,
                "knowledge_query",
                "approved_answer",
                match.topic_id,
                f"{match.confidence:.3f}",
            )
            context["answer_given"] = True
            context["last_topic_id"] = match.topic_id
            self._save(wa_id, conversation_id, "ask_question", context)
            return BotReply(match.answer + self.localizer.text("ask_follow_up", locale))

        if state == "survey_resolved":
            if command in {"3", "skip"}:
                self.repository.create_satisfaction_response(
                    conversation_id, context.get("journey", "unknown"), context.get("journey_outcome", "unknown"),
                    None, None, None, None, locale,
                )
                self._save(wa_id, conversation_id, "main_menu", {"language": locale})
                return BotReply(self.localizer.text("survey_thanks", locale) + "\n\n" + self._main_menu_text(locale))
            resolved = {
                "1": True, "yes": True, "y": True,
                "2": False, "no": False, "n": False,
            }.get(command)
            if resolved is None:
                return BotReply(self.localizer.text("survey_resolved", locale))
            context["resolved"] = resolved
            self._save(wa_id, conversation_id, "survey_rating", context)
            return BotReply(self.localizer.text("survey_rating", locale))

        if state == "survey_rating":
            if command == "skip":
                context["rating"] = None
            elif command in {"1", "2", "3", "4", "5"}:
                context["rating"] = int(command)
            else:
                return BotReply(self.localizer.text("survey_rating", locale))
            self._save(wa_id, conversation_id, "survey_comment", context)
            return BotReply(self.localizer.text("survey_comment", locale))

        if state == "survey_comment":
            if self.SENSITIVE_PATTERN.search(cleaned):
                return BotReply("Please remove passwords, PINs or one-time codes, or type *Skip*.")
            if command == "skip":
                context["comment"] = None
            elif len(cleaned) > 500:
                return BotReply("Please keep the optional comment below 500 characters, or type *Skip*.")
            else:
                context["comment"] = cleaned
            self._save(wa_id, conversation_id, "survey_contact", context)
            return BotReply(self.localizer.text("survey_contact", locale))

        if state == "survey_contact":
            contact_requested = {
                "1": True, "yes": True, "y": True,
                "2": False, "no": False, "n": False,
            }.get(command)
            if contact_requested is None:
                return BotReply(self.localizer.text("survey_contact", locale))
            self.repository.create_satisfaction_response(
                conversation_id,
                context.get("journey", "unknown"),
                context.get("journey_outcome", "unknown"),
                context.get("resolved"),
                context.get("rating"),
                context.get("comment"),
                contact_requested,
                locale,
            )
            self._record_event(conversation_id, "satisfaction_survey", "completed")
            if contact_requested:
                self._save(
                    wa_id,
                    conversation_id,
                    "escalation_category",
                    {"language": locale, "survey_follow_up": True},
                )
                return BotReply(
                    self.localizer.text("survey_thanks", locale)
                    + "\n\n"
                    + self._prompt_for_state("escalation_category", context={"language": locale}).text
                )
            self._save(wa_id, conversation_id, "main_menu", {"language": locale})
            return BotReply(
                self.localizer.text("survey_thanks", locale)
                + "\n\n"
                + self._main_menu_text(locale)
            )

        if state in MENUS:
            destination = MENUS[state]["choices"].get(command)
            if destination is None:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Please reply with one of the numbers shown, type *Main Menu*, or type *Agent*.",
                )
            return self._open_destination(wa_id, conversation_id, destination)

        if state == "onboarding_service":
            selected = ONBOARDING_SERVICES.get(command)
            if selected is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose a service from 1 to 7.")
            service_id, service_name, business = selected
            next_context = {
                "selected_service": service_id,
                "selected_service_name": service_name,
                "selected_business": business,
            }
            self._save(wa_id, conversation_id, "onboarding_journey", next_context)
            return self._onboarding_journey_reply()

        if state == "onboarding_journey":
            journey = {"1": "existing", "2": "new", "3": "forgotten_reference", "4": "representative"}.get(command)
            if journey is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose a journey from 1 to 4.")
            context["journey"] = journey
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "onboarding_notice", context)
            return self._onboarding_notice_reply(context)

        if state == "onboarding_notice":
            if command not in {"1", "continue", "yes", "2", "no"}:
                return self._invalid(wa_id, conversation_id, state, context, "Reply 1 to Continue or 2 to Cancel.")
            granted = command in {"1", "continue", "yes"}
            self.repository.record_permission(
                conversation_id,
                f"onboarding:{context['selected_service']}",
                granted,
                self.settings.CONSENT_NOTICE_VERSION,
            )
            if not granted:
                self._save(wa_id, conversation_id, "main_menu", {})
                return BotReply("Onboarding was cancelled. No account was linked.\n\n" + self._main_menu_text(locale))
            context["local_attempt_id"] = self.repository.create_onboarding_attempt(
                conversation_id,
                context["selected_service"],
                context["journey"],
                self.settings.CONSENT_NOTICE_VERSION,
            )
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "onboarding_id_type", context)
            return self._prompt_for_state("onboarding_id_type", context=context)

        if state == "onboarding_id_type":
            if command == "3":
                return self._onboarding_support_reply(conversation_id, context, "Alternative identity route requested.")
            id_type = {"1": "national_id", "2": "passport"}.get(command)
            if id_type is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, or 3.")
            context["id_type"] = id_type
            context.pop("invalid_attempts", None)
            next_state = "onboarding_id_country" if id_type == "passport" else "onboarding_id_number"
            self._save(wa_id, conversation_id, next_state, context)
            return self._prompt_for_state(next_state, context=context)

        if state == "onboarding_id_country":
            if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,59}", cleaned):
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid issuing country name.")
            context["id_country"] = cleaned
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "onboarding_id_number", context)
            return self._prompt_for_state("onboarding_id_number", context=context)

        if state == "onboarding_id_number":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{3,39}", cleaned):
                return self._invalid(wa_id, conversation_id, state, context, "Check the ID-number format and try again.")
            context["id_number"] = cleaned
            context.pop("invalid_attempts", None)
            if context["journey"] in {"existing", "representative"}:
                self._save(wa_id, conversation_id, "onboarding_reference", context)
                return self._prompt_for_state("onboarding_reference", context=context)
            self._save(wa_id, conversation_id, "onboarding_contact_confirm", context)
            return BotReply(
                f"Use this WhatsApp number ending in {wa_id[-4:]} as the preferred digital-profile contact? "
                "Reply *Yes* or *No*."
            )

        if state == "onboarding_reference":
            if not self._valid_identifier(cleaned):
                return self._invalid(wa_id, conversation_id, state, context, "Check the reference format and try again.")
            context["reference"] = cleaned
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "onboarding_contact_confirm", context)
            return BotReply(
                f"Use this WhatsApp number ending in {wa_id[-4:]} as the preferred digital-profile contact? "
                "Reply *Yes* or *No*."
            )

        if state == "onboarding_contact_confirm":
            if command in {"no", "n"}:
                return self._onboarding_support_reply(conversation_id, context, "A different profile contact is required.")
            if command not in {"yes", "y"}:
                return self._invalid(wa_id, conversation_id, state, context, "Reply *Yes* or *No*.")
            return await self._submit_onboarding(wa_id, conversation_id, context)

        if state == "onboarding_relationship_selection":
            relationships = context.get("relationships") or []
            if not relationships:
                if command == "1":
                    return self._onboarding_support_reply(conversation_id, context, "Assisted relationship matching requested.")
                if command == "2":
                    return await self.process_message(wa_id, "cancel", conversation_id, user_name)
                if context.get("journey") != "new" or command != "skip":
                    allowed = "Type Skip, or choose 1 or 2." if context.get("journey") == "new" else "Choose 1 or 2."
                    return self._invalid(wa_id, conversation_id, state, context, allowed)
                selected_indexes: list[int] = []
            elif command in {"a", "all"}:
                selected_indexes = list(range(len(relationships)))
            elif command == "skip":
                selected_indexes = []
            else:
                try:
                    selected_indexes = sorted({int(value.strip()) - 1 for value in command.split(",")})
                except ValueError:
                    selected_indexes = []
                if not selected_indexes or any(index < 0 or index >= len(relationships) for index in selected_indexes):
                    return self._invalid(
                        wa_id,
                        conversation_id,
                        state,
                        context,
                        "Choose numbers separated by commas, A for all, or type Skip to continue without linking.",
                    )
            context["selected_relationship_ids"] = [relationships[index]["relationship_id"] for index in selected_indexes]
            selected = [relationships[index] for index in selected_indexes]
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "onboarding_link_review", context)
            review = (
                "\n".join(f"- {item['service']} {item['masked_reference']} ({item['source_status']})" for item in selected)
                if selected
                else "No existing account will be linked."
            )
            return BotReply(f"*Review onboarding*\n\n{review}\n\n1. Confirm\n2. Change selection\n3. Cancel")

        if state == "onboarding_link_review":
            if command == "2":
                context.pop("selected_relationship_ids", None)
                self._save(wa_id, conversation_id, "onboarding_relationship_selection", context)
                relationships = context.get("relationships") or []
                if not relationships:
                    return BotReply("Type *Skip* to complete without linking.\n1. Get assistance\n2. Cancel")
                lines = ["*Choose accounts to link*", ""]
                for index, item in enumerate(relationships, start=1):
                    lines.append(f"{index}. {item['service']} - {item['masked_reference']} - {item['source_status']}")
                lines.extend(["A. Link all eligible accounts shown", "Type *Skip* to continue without linking"])
                return BotReply("\n".join(lines))
            if command == "3":
                return await self.process_message(wa_id, "cancel", conversation_id, user_name)
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Reply 1 to Confirm, 2 to Change, or 3 to Cancel.")
            selected_ids = context.get("selected_relationship_ids") or []
            try:
                result = await self.core_client.link_relationships(context["external_attempt_id"], selected_ids)
            except (IntegrationUnavailableError, IntegrationResponseError):
                return BotReply("Linking is temporarily unavailable. No new outcome was confirmed. Reply 1 to retry or 3 to Cancel.")
            external_profile_id = str(result.get("profile_id") or "").strip()
            outcomes = result.get("links")
            if not external_profile_id or not isinstance(outcomes, list):
                return self._onboarding_support_reply(conversation_id, context, "Linking result requires reconciliation.")
            returned_ids = {
                str(item.get("relationship_id"))
                for item in outcomes
                if isinstance(item, dict) and item.get("relationship_id")
            }
            if set(selected_ids) != returned_ids:
                self.repository.save_onboarding_links(
                    conversation_id,
                    external_profile_id,
                    [item for item in outcomes if isinstance(item, dict)],
                    str(result.get("profile_status") or "review_required"),
                )
                return self._onboarding_support_reply(conversation_id, context, "Not every requested link received a confirmed outcome.")
            profile_id = self.repository.save_onboarding_links(
                conversation_id,
                external_profile_id,
                [item for item in outcomes if isinstance(item, dict)],
                str(result.get("profile_status") or "active"),
            )
            has_issue = any(
                str(item.get("link_status") or item.get("status") or "").lower() not in {"linked", "already_linked"}
                for item in outcomes
                if isinstance(item, dict)
            )
            self.repository.update_onboarding_attempt(
                context["local_attempt_id"],
                "completed_with_issues" if has_issue else "completed",
            )
            next_context = {
                "language": locale,
                "journey": "onboarding",
                "journey_outcome": "completed_with_issues" if has_issue else "completed",
            }
            self._save(wa_id, conversation_id, "survey_resolved", next_context)
            lines = [
                f"- {item.get('masked_reference', 'Account')}: {item.get('link_status') or item.get('status') or 'Unknown'}"
                for item in outcomes
                if isinstance(item, dict)
            ]
            outcome_text = "\n".join(lines) if lines else "No existing account was selected for linking."
            return BotReply(
                f"Your digital profile is ready.\n\n{outcome_text}\n\n"
                + self.localizer.text("survey_resolved", locale)
            )

        if state == "onboarding_complete":
            if command == "2":
                return self._open_destination(wa_id, conversation_id, "main_menu")
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 or 2.")
            destination = {
                "life": "life_menu",
                "employee_benefits": "1.3",
                "funeral": "funeral_menu",
                "medical_aid": "flimas_menu",
            }.get(context["selected_service"])
            if destination:
                return self._open_destination(wa_id, conversation_id, destination)
            team = context["selected_service_name"]
            self._save(
                wa_id,
                conversation_id,
                "escalation_permission",
                {"category": context["selected_service"], "team": team},
            )
            return BotReply(
                f"{team} does not yet have a dedicated self-service menu. "
                "May we send an enquiry to that team? Reply *Yes* or *No*."
            )

        if state == "app_platform":
            if command == "1":
                self._save(wa_id, conversation_id, "link_result", {"parent": "flimas_self_service"})
                return self._link_reply("android")
            if command == "2":
                self._save(wa_id, conversation_id, "link_result", {"parent": "flimas_self_service"})
                return self._link_reply("ios")
            if command == "3":
                return self._open_destination(wa_id, conversation_id, "flimas_self_service")
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, or 3.")

        if state == "contact_details":
            if command == "1":
                return self._open_destination(wa_id, conversation_id, "escalation_category")
            if command == "2":
                return self._open_destination(wa_id, conversation_id, "main_menu")
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1 or 2, or type *Back*.")

        if state == "service_detail":
            service_id = context.get("service_id")
            service = SERVICES.get(service_id)
            if service is None:
                return self._open_destination(wa_id, conversation_id, "main_menu")
            action = service["actions"].get(command)
            if action is None:
                return self._invalid(wa_id, conversation_id, state, context, "Please choose one of the displayed options.")
            if action == "back":
                return self._handle_back(wa_id, conversation_id, state, context)
            if action == "main_menu":
                return self._open_destination(wa_id, conversation_id, "main_menu")
            if action in SERVICES:
                return self._open_destination(wa_id, conversation_id, action)
            if action in MENUS:
                return self._open_destination(wa_id, conversation_id, action)
            if action.startswith("enquiry"):
                subtype = action.split(":", 1)[1] if ":" in action else None
                form_context = self._service_context(service_id, subtype)
                self._save(wa_id, conversation_id, "enquiry_permission", form_context)
                return BotReply(
                    "To arrange assistance, may we share your callback details with "
                    f"{service['team']}? Reply *Yes* or *No*."
                )

        if state == "enquiry_permission":
            if command not in {"yes", "y", "no", "n"}:
                return self._invalid(wa_id, conversation_id, state, context, "Please reply *Yes* or *No*.")
            granted = command in {"yes", "y"}
            self.repository.record_permission(
                conversation_id,
                f"service_request:{context['service_id']}",
                granted,
                self.settings.CONSENT_NOTICE_VERSION,
            )
            if not granted:
                self._record_event(conversation_id, "permission", "declined", context["service_id"])
                return self._open_destination(wa_id, conversation_id, context["service_id"])
            context["permission_granted"] = True
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "enquiry_callback_confirm", context)
            return BotReply(
                f"Use this WhatsApp number ending in {wa_id[-4:]} as your preferred callback number? "
                "Reply *Yes* or *No*."
            )

        if state == "enquiry_callback_confirm":
            if command in {"yes", "y"}:
                context["callback_number"] = wa_id
                context.pop("invalid_attempts", None)
                if context.get("fields"):
                    self._save(wa_id, conversation_id, "enquiry_field", context)
                    return BotReply(context["fields"][0][1])
                self._save(wa_id, conversation_id, "enquiry_review", context)
                return self._review_enquiry(context)
            if command in {"no", "n"}:
                self._save(wa_id, conversation_id, "enquiry_callback_number", context)
                return BotReply("Enter the preferred callback number, including the country code.")
            return self._invalid(wa_id, conversation_id, state, context, "Please reply *Yes* or *No*.")

        if state == "enquiry_callback_number":
            number = self._valid_phone(cleaned)
            if not number:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Enter a valid international number including the country code.",
                )
            context["callback_number"] = number
            context.pop("invalid_attempts", None)
            if context.get("fields"):
                self._save(wa_id, conversation_id, "enquiry_field", context)
                return BotReply(context["fields"][0][1])
            self._save(wa_id, conversation_id, "enquiry_review", context)
            return self._review_enquiry(context)

        if state == "enquiry_field":
            if self.SENSITIVE_PATTERN.search(cleaned):
                return BotReply(
                    "Please do not send passwords, PINs or one-time codes. Provide only the requested information."
                )
            if len(cleaned) < 2 or len(cleaned) > 500:
                return self._invalid(wa_id, conversation_id, state, context, "Please provide a short answer.")
            field_index = int(context.get("field_index", 0))
            key, _ = context["fields"][field_index]
            context.setdefault("values", {})[key] = cleaned
            field_index += 1
            context["field_index"] = field_index
            context.pop("invalid_attempts", None)
            if field_index < len(context["fields"]):
                self._save(wa_id, conversation_id, "enquiry_field", context)
                return BotReply(context["fields"][field_index][1])
            self._save(wa_id, conversation_id, "enquiry_review", context)
            return self._review_enquiry(context)

        if state == "enquiry_review":
            if command in {"2", "edit"}:
                context["field_index"] = 0
                if context.get("fields"):
                    self._save(wa_id, conversation_id, "enquiry_field", context)
                    return BotReply(context["fields"][0][1])
                self._save(wa_id, conversation_id, "enquiry_callback_confirm", context)
                return BotReply("Use this WhatsApp number as the preferred callback number? Reply *Yes* or *No*.")
            if command in {"3", "cancel"}:
                return await self.process_message(wa_id, "cancel", conversation_id, user_name)
            if command not in {"1", "submit"}:
                return self._invalid(wa_id, conversation_id, state, context, "Reply 1 to Submit, 2 to Edit, or 3 to Cancel.")
            payload = {
                "service_id": context["service_id"],
                "team": context["team"],
                "callback_number": context["callback_number"],
                "customer_type": context.get("customer_type"),
                "fields": context.get("values", {}),
                "permission_scope": f"service_request:{context['service_id']}",
                "priority": context.get("priority", "routine"),
            }
            request_id = self.repository.create_request(
                conversation_id,
                f"service_enquiry:{context['service_id']}",
                payload,
                "pending_delivery",
            )
            lead_id = self.repository.create_sales_lead(
                conversation_id,
                "whatsapp_service_enquiry",
                context["service_id"],
                context.get("values", {}),
                language=locale,
                callback_number=context["callback_number"],
                follow_up_consent=True,
                assigned_team=context["team"],
                qualification_status="service_interest_captured",
            )
            self._record_event(
                conversation_id,
                "lead_captured",
                "service_interest_captured",
                context["service_id"],
                lead_id,
            )
            template = self.follow_up_templates.get("service_enquiry")
            self.repository.create_follow_up(
                conversation_id,
                lead_id,
                "service_enquiry",
                datetime.utcnow() + timedelta(hours=max(1, self.settings.FOLLOW_UP_WINDOW_HOURS)),
                f"permission:{self.settings.CONSENT_NOTICE_VERSION}",
                status="scheduled" if self.settings.FOLLOW_UP_ENABLED and template else "awaiting_configuration",
                template_name=str(template) if template else None,
            )
            escalation_id = self.repository.create_escalation(
                conversation_id,
                context["service_id"],
                json.dumps({"request_id": request_id, "fields": context.get("values", {})}),
                assigned_team=context["team"],
            )
            survey_context = {
                "language": locale,
                "journey": f"service_enquiry:{context['service_id']}",
                "journey_outcome": "submitted",
            }
            self._save(wa_id, conversation_id, "survey_resolved", survey_context)
            survey_prompt = self.localizer.text("survey_resolved", locale)
            return BotReply(
                "Submitting your request...",
                escalation_id=escalation_id,
                metadata={
                    "handover": True,
                    "share_context": True,
                    "category": context["service_id"],
                    "assigned_team": context["team"],
                    "request_id": request_id,
                    "lead_id": lead_id,
                    "success_text": (
                        f"Your request has been received by {context['team']}. "
                        f"Reference: {request_id}\n\n{survey_prompt}"
                    ),
                    "failure_text": (
                        "We could not confirm delivery of your request. Please try again or use the "
                        f"contact details below.\n\n{self._contact_text()}\n\n{survey_prompt}"
                    ),
                },
            )

        if state == "escalation_category":
            selected = ESCALATION_CATEGORIES.get(command)
            if selected is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose a category from 1 to 5.")
            category, default_team = selected
            team = self.escalation_matrix.get(category, default_team)
            next_context = {"category": category, "team": team}
            self._save(wa_id, conversation_id, "escalation_permission", next_context)
            return self._prompt_for_state("escalation_permission")

        if state == "escalation_permission":
            if command not in {"yes", "y", "no", "n"}:
                return self._invalid(wa_id, conversation_id, state, context, "Please reply *Yes* or *No*.")
            share_context = command in {"yes", "y"}
            self.repository.record_permission(
                conversation_id,
                f"agent_handover:{context.get('category', 'general')}",
                share_context,
                self.settings.CONSENT_NOTICE_VERSION,
            )
            context["share_context"] = share_context
            context.pop("invalid_attempts", None)
            self._save(wa_id, conversation_id, "escalation_details", context)
            if share_context:
                return BotReply("Briefly describe what you need help with. Do not include passwords, PINs or card details.")
            return BotReply(
                "We will not attach your earlier conversation. Briefly describe the new issue for the selected team, "
                "or type *Cancel* to use the public contact details."
            )

        if state == "escalation_details":
            if self.SENSITIVE_PATTERN.search(cleaned):
                return BotReply("Please remove passwords, PINs or one-time codes and send a short issue summary.")
            if len(cleaned) < 10 or len(cleaned) > 1000:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Please provide a little more detail, without sensitive information.",
                )
            category = context.get("category", "general")
            team = context.get("team") or self.escalation_matrix.get(category) or "General Customer Care"
            escalation_id = self.repository.create_escalation(
                conversation_id,
                category,
                cleaned,
                assigned_team=team,
            )
            survey_context = {
                "language": locale,
                "journey": f"agent_handover:{category}",
                "journey_outcome": "submitted",
            }
            self._save(wa_id, conversation_id, "survey_resolved", survey_context)
            after_hours = self._is_after_hours()
            queued_text = f"Your conversation has been queued for {team}. Reference: {escalation_id}."
            if after_hours is True:
                queued_text += " This was received outside configured service hours."
            queued_text += "\n\n" + self.localizer.text("survey_resolved", locale)
            return BotReply(
                "Connecting you to the selected team...",
                escalation_id=escalation_id,
                metadata={
                    "handover": True,
                    "share_context": bool(context.get("share_context")),
                    "category": category,
                    "assigned_team": team,
                    "success_text": queued_text,
                    "failure_text": (
                        "We could not confirm that the team queue received your request. "
                        f"Please use the direct contact details below.\n\n{self._contact_text()}"
                    ),
                },
            )

        if state == "policy_menu":
            next_state = {"1": "policy_details_number", "2": "payment_history_number", "3": "escalation_details"}.get(command)
            if next_state is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, or 3, or type *Back*.")
            next_context = {"category": "life", "team": "Life Assurance", "share_context": True} if next_state == "escalation_details" else {}
            self._save(wa_id, conversation_id, next_state, next_context)
            return BotReply("Please describe the policy assistance you need.") if next_state == "escalation_details" else self._prompt_for_state(next_state)

        if state == "policy_cover_menu":
            if command in {"1", "2", "4"}:
                category = "policy_number" if command == "1" else "cover_activation" if command == "2" else "life"
                next_context = {
                    "language": locale,
                    "category": category,
                    "team": "Life Assurance",
                    "share_context": False,
                }
                self._save(wa_id, conversation_id, "escalation_permission", next_context)
                return BotReply(
                    "This operation requires approved business rules and authoritative system confirmation. "
                    "No policy number was generated and no cover was activated.\n\n"
                    + self._prompt_for_state("escalation_permission", context=next_context).text
                )
            if command == "3":
                self._save(wa_id, conversation_id, "application_tracking_reference", {"language": locale})
                return self._prompt_for_state("application_tracking_reference")
            if command == "5":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, 3, 4 or 5.")

        if state == "payments_menu":
            if self.settings.MENU_CATALOGUE_V11_ENABLED and not self.payment_client.configured:
                if command == "5":
                    return self._open_destination(wa_id, conversation_id, "main_menu", context)
                if command == "1":
                    if self.insuretech_client is None or not self.insuretech_client.configured:
                        return BotReply("The approved payment-method service is unavailable. Type *Agent* for official payment information.")
                    try:
                        methods = await self.insuretech_client.list_payment_methods()
                    except (IntegrationUnavailableError, IntegrationResponseError):
                        return BotReply("Available payment methods could not be retrieved right now. Please retry or type *Agent*.")
                    return self._insuretech_payment_methods_reply(methods)
                if command == "3":
                    self._save(wa_id, conversation_id, "payment_status_reference", {"language": locale})
                    return self._prompt_for_state("payment_status_reference")
                if command in {"2", "4"}:
                    next_context = {
                        "language": locale,
                        "category": "payments",
                        "team": "Billing",
                        "share_context": False,
                    }
                    self._save(wa_id, conversation_id, "escalation_permission", next_context)
                    return self._prompt_for_state("escalation_permission", context=next_context)
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, 3, 4 or 5.")
            next_state = {"1": "payment_history_number", "2": "payment_identity_notice", "3": "payment_status_reference", "4": "escalation_details"}.get(command)
            if next_state is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, 3, or 4, or type *Back*.")
            next_context = {"category": "payments", "team": "Billing", "share_context": True} if next_state == "escalation_details" else {}
            self._save(wa_id, conversation_id, next_state, next_context)
            return BotReply("Please describe the payment assistance you need.") if next_state == "escalation_details" else self._prompt_for_state(next_state)

        if state == "payment_identity_notice":
            if command == "2":
                return self._open_destination(wa_id, conversation_id, "life_menu", context)
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 to Verify Identity or 2 to go Back.")
            context = {"language": locale, "verification_attempts": 0, "payment_attempts": 0}
            self._save(wa_id, conversation_id, "payment_verify_mobile", context)
            return self._prompt_for_state("payment_verify_mobile", context=context)

        if state == "payment_verify_mobile":
            mobile = self._valid_payment_mobile(cleaned)
            if not mobile:
                return self._invalid(
                    wa_id,
                    conversation_id,
                    state,
                    context,
                    "Enter a valid registered mobile number, for example 0771234567 or +263771234567.",
                )
            try:
                result = await self.core_client.start_payment_verification(wa_id, mobile)
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                self._record_event(conversation_id, "payment_verification", "unavailable")
                return self._integration_failure(exc)
            verification_id = str(result.get("verification_id") or result.get("attempt_id") or "").strip()
            if not verification_id:
                return BotReply("Fidelity's verification service did not return a valid attempt. No payment was started. Type *Agent* for help.")
            context.update(
                {
                    "verification_id": verification_id,
                    "registered_mobile": mobile,
                    "masked_registered_mobile": f"***{mobile[-4:]}",
                }
            )
            self.repository.create_request(
                conversation_id,
                "payment_identity_verification",
                {"verification_id": verification_id, "mobile_suffix": mobile[-4:]},
                "challenge_sent",
            )
            self._save(wa_id, conversation_id, "payment_verify_code", context)
            return self._prompt_for_state("payment_verify_code", context=context)

        if state == "payment_verify_code":
            if not re.fullmatch(r"[0-9]{4,8}", cleaned):
                return self._invalid(wa_id, conversation_id, state, context, "Enter the 4 to 8 digit verification code.")
            try:
                result = await self.core_client.confirm_payment_verification(context["verification_id"], cleaned)
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return self._integration_failure(exc)
            if result.get("verified") is not True:
                attempts = int(context.get("verification_attempts", 0)) + 1
                context["verification_attempts"] = attempts
                self._record_event(conversation_id, "payment_verification", "failed")
                if attempts >= max(1, self.settings.PAYMENT_VERIFICATION_MAX_ATTEMPTS):
                    self._save(wa_id, conversation_id, "payment_identity_notice", {"language": locale})
                    return BotReply(
                        "Verification could not be completed after the permitted attempts. No payment was started. "
                        "Return later or type *Agent* for assisted verification."
                    )
                self._save(wa_id, conversation_id, state, context)
                remaining = max(0, self.settings.PAYMENT_VERIFICATION_MAX_ATTEMPTS - attempts)
                return BotReply(f"The verification code was not accepted. Try again. Attempts remaining: {remaining}.")
            try:
                policy_data = result if isinstance(result.get("policies"), list) else await self.core_client.get_payment_eligible_policies(context["verification_id"])
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return self._integration_failure(exc)
            policies = self._normalized_payment_policies(policy_data)
            if not policies:
                self._save(wa_id, conversation_id, "payment_profile_menu", context)
                return BotReply(
                    "Identity was verified, but no payment-eligible policy was returned. This does not mean no policy exists. "
                    "Type *Agent* for assistance."
                )
            context.update(
                {
                    "payment_policies": policies,
                    "customer_name": str(result.get("customer_name") or "Verified Customer")[:160],
                    "verified": True,
                }
            )
            context.pop("registered_mobile", None)
            self._record_event(conversation_id, "payment_verification", "verified")
            self._save(wa_id, conversation_id, "payment_profile_menu", context)
            return self._payment_profile_reply(context)

        if state == "payment_profile_menu":
            if command in {"1", "6"}:
                if not context.get("payment_policies"):
                    return BotReply("No payment-eligible policies are available. Type *Agent* for assistance.")
                self._save(wa_id, conversation_id, "payment_policy_select", context)
                return self._payment_policies_reply(context)
            if command == "2":
                return self._open_destination(wa_id, conversation_id, "claims_menu", context)
            if command == "3":
                self._save(wa_id, conversation_id, "payment_history_number", {"language": locale})
                return self._prompt_for_state("payment_history_number", context={"language": locale})
            if command == "4":
                return self._open_destination(wa_id, conversation_id, "life_documents", context)
            if command == "5":
                return self._open_destination(wa_id, conversation_id, "main_menu", context)
            if command == "7":
                return self._survey_reply(wa_id, conversation_id, "payment", "abandoned", locale)
            return self._invalid(wa_id, conversation_id, state, context, "Choose an option from 1 to 7.")

        if state == "payment_policy_select":
            policies = context.get("payment_policies") or []
            if not command.isdigit() or not 1 <= int(command) <= len(policies):
                return self._invalid(wa_id, conversation_id, state, context, "Choose one of the displayed policies.")
            selected = policies[int(command) - 1]
            context.update({"selected_policy": selected, "policy_number": selected["policy_number"]})
            self._save(wa_id, conversation_id, "payment_currency", context)
            return self._payment_currency_reply(context)

        if state == "payment_currency":
            if command == "3":
                self._save(wa_id, conversation_id, "payment_policy_select", context)
                return self._payment_policies_reply(context)
            currency = {"1": "USD", "2": "ZiG"}.get(command)
            if currency is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 for USD, 2 for ZiG, or 3 to go Back.")
            policy = context["selected_policy"]
            try:
                prepared = await self.payment_client.prepare_payment(
                    {
                        "policy_number": policy["policy_number"],
                        "amount_due": policy["premium_due"],
                        "source_currency": policy["currency"],
                        "payment_currency": currency,
                        "verification_id": context.get("verification_id"),
                    }
                )
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return BotReply(
                    "The authorised payment service could not calculate and validate this payment amount. "
                    "No exchange rate or payment amount was assumed. Type *Agent* or try again later."
                )
            raw_amount = str(prepared.get("amount") or prepared.get("payment_amount") or "")
            try:
                amount = Decimal(raw_amount)
                if amount <= 0 or amount.as_tuple().exponent < -2:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                return BotReply("The payment service returned an invalid amount. No payment was started. Type *Agent*.")
            returned_currency = str(prepared.get("currency") or currency)
            if returned_currency.upper() != currency.upper():
                return BotReply("The payment service returned an unexpected currency. No payment was started. Type *Agent*.")
            context.update(
                {
                    "currency": currency,
                    "amount": f"{amount:.2f}",
                    "preparation_reference": str(prepared.get("preparation_reference") or "") or None,
                }
            )
            self._save(wa_id, conversation_id, "payment_method", context)
            return self._payment_methods_reply()

        if state == "payment_method":
            methods = {str(index): method_id for index, method_id in enumerate(self.payment_methods, start=1)}
            back_choice = str(len(methods) + 1)
            if command == back_choice:
                self._save(wa_id, conversation_id, "payment_currency", context)
                return self._payment_currency_reply(context)
            method = methods.get(command)
            if method is None:
                return self._invalid(wa_id, conversation_id, state, context, "Choose one of the displayed payment methods.")
            context["payment_method"] = method
            if method == "bank_transfer":
                if not self.bank_transfer_instructions:
                    return BotReply(
                        "Approved Fidelity bank-transfer instructions are not configured, so no account number will be displayed. "
                        "Type *Agent* for verified banking details."
                    )
                account = self.bank_transfer_instructions.get(context["currency"])
                if not isinstance(account, dict):
                    return BotReply("No approved bank-transfer account is configured for that currency. Type *Agent*.")
                required = [str(account.get(key) or "").strip() for key in ("bank", "branch", "account_number")]
                if not all(required):
                    return BotReply("The approved bank-transfer instructions are incomplete. Type *Agent*.")
                self._save(wa_id, conversation_id, "payment_bank_transfer", context)
                return BotReply(
                    "*Bank Transfer*\n\n"
                    f"Amount: {context['currency']} {context['amount']}\n"
                    f"Bank: {required[0]}\nBranch: {required[1]}\nAccount number: {required[2]}\n\n"
                    f"Use policy number *{context['policy_number']}* as the payment reference. "
                    "A transfer is not credited until Fidelity Finance verifies it.\n\n1. Upload proof of payment\n2. Back"
                )
            if method == "card":
                self._save(wa_id, conversation_id, "payment_card_link", context)
                return BotReply(
                    "*Visa / Mastercard*\n\n"
                    f"Amount: {context['currency']} {context['amount']}\n\n"
                    "Card details are handled only on the authorised encrypted payment portal. "
                    "Never send card numbers, CVV or PINs in this chat.\n\n1. Proceed\n2. Back"
                )
            self._save(wa_id, conversation_id, "payment_mobile", context)
            return self._prompt_for_state("payment_mobile", context=context)

        if state == "payment_mobile":
            mobile = self._valid_payment_mobile(cleaned)
            if not mobile:
                return self._invalid(wa_id, conversation_id, state, context, "Enter a valid wallet mobile number.")
            context.update({"mobile_number": mobile, "masked_mobile": f"***{mobile[-4:]}"})
            self._save(wa_id, conversation_id, "payment_confirm", context)
            return BotReply(
                "*Confirm payment*\n\nPlease confirm:\n"
                f"Policy: {context['policy_number']}\nAmount: {context['currency']} {context['amount']}\n"
                f"Method: {self.payment_methods.get(context['payment_method'], context['payment_method'])}\n"
                f"Mobile: {context['masked_mobile']}\n\nReply *Confirm* to continue or *Back* to change the method."
            )

        if state == "payment_confirm":
            if command != "confirm":
                return self._invalid(wa_id, conversation_id, state, context, "Reply *Confirm* or type *Back*.")
            try:
                return await self._submit_payment(wa_id, conversation_id, context, locale)
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return self._integration_failure(exc)

        if state == "payment_card_link":
            if command == "2":
                self._save(wa_id, conversation_id, "payment_method", context)
                return self._payment_methods_reply()
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 to Proceed or 2 to go Back.")
            try:
                return await self._submit_payment(wa_id, conversation_id, context, locale)
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return self._integration_failure(exc)

        if state == "payment_wallet_processing":
            if command != "done":
                return self._invalid(wa_id, conversation_id, state, context, "Reply *DONE* to verify or *Cancel* to stop.")
            try:
                data = await self.payment_client.get_payment_status(context["payment_reference"])
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return self._integration_failure(exc)
            payment_status = str(data.get("status") or "unknown").lower()
            self.repository.update_transaction_status(context["payment_reference"], payment_status)
            result = self._payment_result_reply(data, context)
            if payment_status in {"successful", "success", "paid", "completed", "confirmed"}:
                self._save(
                    wa_id,
                    conversation_id,
                    "survey_resolved",
                    {"language": locale, "journey": "payment", "journey_outcome": "successful"},
                )
                result.text += "\n\n" + self.localizer.text("survey_resolved", locale)
            elif payment_status in {"failed", "declined", "cancelled", "expired"}:
                self._save(wa_id, conversation_id, "payment_retry", context)
            else:
                self._save(wa_id, conversation_id, state, context)
            return result

        if state == "payment_retry":
            if command == "2":
                self._save(wa_id, conversation_id, "payment_profile_menu", context)
                return self._payment_profile_reply(context)
            if command != "1":
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 to Try Again or 2 for the Profile Menu.")
            attempts = int(context.get("payment_attempts", 0))
            if attempts >= max(1, self.settings.PAYMENT_MAX_RETRIES):
                return BotReply("The permitted payment attempts have been reached. No further payment was submitted. Type *Agent* for help.")
            context.pop("payment_reference", None)
            context.pop("mobile_number", None)
            context.pop("masked_mobile", None)
            self._save(wa_id, conversation_id, "payment_method", context)
            return self._payment_methods_reply()

        if state == "payment_bank_transfer":
            if command == "2":
                self._save(wa_id, conversation_id, "payment_method", context)
                return self._payment_methods_reply()
            if command not in {"1", "upload"}:
                return self._invalid(wa_id, conversation_id, state, context, "Choose 1 to Upload proof of payment or 2 to go Back.")
            self._save(wa_id, conversation_id, "payment_pop_waiting", context)
            return self._prompt_for_state("payment_pop_waiting", context=context)

        if state == "payment_pop_waiting":
            media_match = re.fullmatch(r"__media__:(image|document):([A-Za-z0-9_-]{5,255})", cleaned)
            if not media_match:
                return BotReply("Attach a JPG, PNG or PDF proof of payment. A text message cannot be treated as payment proof.")
            media_type, media_id = media_match.groups()
            request_id = self.repository.create_request(
                conversation_id,
                "bank_transfer_proof",
                {
                    "policy_number": context["policy_number"],
                    "amount": context["amount"],
                    "currency": context["currency"],
                    "media_type": media_type,
                    "media_id": media_id,
                },
                "pending_finance_verification",
            )
            escalation_id = self.repository.create_escalation(
                conversation_id,
                "bank_transfer_proof",
                json.dumps({"request_id": request_id, "policy_number": context["policy_number"]}),
                assigned_team="Finance",
            )
            self._save(
                wa_id,
                conversation_id,
                "survey_resolved",
                {"language": locale, "journey": "bank_transfer_proof", "journey_outcome": "pending_verification"},
            )
            return BotReply(
                "Your proof of payment was received for Finance review. This does not confirm that funds were received or credited. "
                f"Reference: {request_id}\n\n{self.localizer.text('survey_resolved', locale)}",
                escalation_id=escalation_id,
                metadata={
                    "handover": True,
                    "share_context": False,
                    "category": "bank_transfer_proof",
                    "assigned_team": "Finance",
                    "request_id": request_id,
                    "success_text": (
                        "Your proof of payment was delivered for Finance review. It remains pending verification. "
                        f"Reference: {request_id}\n\n{self.localizer.text('survey_resolved', locale)}"
                    ),
                    "failure_text": (
                        "Your proof was recorded but delivery to Finance was not confirmed. No payment has been credited. "
                        f"Reference: {request_id}\n\n{self.localizer.text('survey_resolved', locale)}"
                    ),
                },
            )

        if state == "claims_menu":
            if command == "1":
                self._save(wa_id, conversation_id, "claim_status_reference", {})
                return self._prompt_for_state("claim_status_reference")
            if command in {"2", "3"}:
                next_context = {"category": "claims", "team": "Claims", "share_context": True}
                self._save(wa_id, conversation_id, "escalation_details", next_context)
                return BotReply("Please describe the claim assistance you need.")
            return self._invalid(wa_id, conversation_id, state, context, "Choose 1, 2, or 3, or type *Back*.")

        if state in {"policy_details_number", "payment_history_number"}:
            if not self._valid_identifier(cleaned):
                return BotReply("That policy number format is invalid. Please check it and try again.")
            request_type = "policy_details" if state == "policy_details_number" else "payment_history"
            try:
                verified = await self.core_client.verify_customer(wa_id, cleaned, "policy")
                if not verified:
                    self.repository.create_request(conversation_id, request_type, {"policy_number": cleaned}, "verification_failed")
                    return BotReply("We could not verify that policy for this WhatsApp account. Check the number or type *Agent*.")
                data = (
                    await self.core_client.get_policy_details(cleaned, wa_id)
                    if request_type == "policy_details"
                    else await self.core_client.get_payment_history(cleaned, wa_id)
                )
                result = self._format_policy(data) if request_type == "policy_details" else self._format_payments(data)
                self.repository.create_request(conversation_id, request_type, {"policy_number": cleaned}, "completed")
                self._save(
                    wa_id,
                    conversation_id,
                    "survey_resolved",
                    {"language": locale, "journey": request_type, "journey_outcome": "completed"},
                )
                return BotReply(f"{result}\n\n{self.localizer.text('survey_resolved', locale)}")
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                self.repository.create_request(conversation_id, request_type, {"policy_number": cleaned}, "failed")
                return self._integration_failure(exc)

        if state == "claim_status_reference":
            if not self._valid_identifier(cleaned):
                return BotReply("That claim reference format is invalid. Please check it and try again.")
            try:
                verified = await self.core_client.verify_customer(wa_id, cleaned, "claim")
                if not verified:
                    self.repository.create_request(conversation_id, "claim_status", {"reference": cleaned}, "verification_failed")
                    return BotReply("We could not verify that claim for this WhatsApp account. Check the reference or type *Agent*.")
                data = await self.core_client.get_claim_status(cleaned, wa_id)
                status = data.get("status", "Status unavailable")
                updated = data.get("last_updated")
                self.repository.create_request(conversation_id, "claim_status", {"reference": cleaned}, "completed")
                self._save(
                    wa_id,
                    conversation_id,
                    "survey_resolved",
                    {"language": locale, "journey": "claim_status", "journey_outcome": "completed"},
                )
                suffix = f"\nLast updated: {updated}" if updated else ""
                return BotReply(
                    f"*Claim status*\n\nReference: {cleaned}\nStatus: {status}{suffix}\n\n"
                    + self.localizer.text("survey_resolved", locale)
                )
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                self.repository.create_request(conversation_id, "claim_status", {"reference": cleaned}, "failed")
                return self._integration_failure(exc)

        if state == "payment_status_reference":
            if not self._valid_identifier(cleaned):
                return BotReply("That payment reference format is invalid. Please check it and try again.")
            try:
                if self.payment_client.configured:
                    data = await self.payment_client.get_payment_status(cleaned)
                elif self.insuretech_client is not None and self.insuretech_client.configured:
                    data = await self.insuretech_client.get_payment_status(cleaned)
                else:
                    raise IntegrationUnavailableError("No approved payment-status service is configured")
                payment_status = str(data.get("status") or "unknown")
                self.repository.update_transaction_status(cleaned, payment_status)
                self._save(wa_id, conversation_id, "payments_menu", {})
                return BotReply(
                    f"*Payment status*\n\nReference: {cleaned}\n"
                    f"Status: {payment_status.replace('_', ' ')}"
                )
            except (IntegrationUnavailableError, IntegrationResponseError) as exc:
                return self._integration_failure(exc)

        self._save(wa_id, conversation_id, "main_menu", {})
        return BotReply(f"The previous session could not be continued.\n\n{self._main_menu_text(locale)}")
