from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Meta WhatsApp Cloud API credentials
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    META_APP_SECRET: str = ""
    META_GRAPH_API_VERSION: str = "v21.0"

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    RELOAD: bool = True
    APP_ENV: str = "development"
    MENU_CATALOGUE_V11_ENABLED: bool = True

    # Persistence and session management
    DATABASE_URL: str = (
        "mssql+pyodbc://@localhost/FidelityWhatsAppBot"
        "?driver=ODBC+Driver+18+for+SQL+Server"
        "&trusted_connection=yes"
        "&TrustServerCertificate=yes"
    )
    SESSION_TTL_SECONDS: int = 1800

    # Fidelity integration endpoints. These must point to approved environments.
    CUSTOMER_POLICY_API_BASE_URL: str = ""
    CUSTOMER_POLICY_API_TOKEN: str = ""
    CUSTOMER_VERIFICATION_PATH: str = ""
    ONBOARDING_START_PATH: str = ""
    ONBOARDING_RELATIONSHIPS_PATH: str = "/onboarding/{attempt_id}/relationships"
    ONBOARDING_LINK_PATH: str = "/onboarding/{attempt_id}/links"
    POLICY_DETAILS_PATH: str = "/policies/{policy_number}"
    PAYMENT_HISTORY_PATH: str = "/policies/{policy_number}/payments"
    CLAIM_STATUS_PATH: str = "/claims/{reference}"
    PAYMENT_API_BASE_URL: str = ""
    PAYMENT_API_TOKEN: str = ""
    PAYMENT_INITIATION_PATH: str = "/payments"
    PAYMENT_STATUS_PATH: str = "/payments/{reference}"
    PAYMENT_PREPARATION_PATH: str = "/payments/prepare"
    PAYMENT_VERIFICATION_START_PATH: str = ""
    PAYMENT_VERIFICATION_CONFIRM_PATH: str = ""
    PAYMENT_ELIGIBLE_POLICIES_PATH: str = ""
    PAYMENT_METHODS_JSON: str = "{}"
    BANK_TRANSFER_INSTRUCTIONS_JSON: str = "{}"
    PAYMENT_VERIFICATION_MAX_ATTEMPTS: int = 3
    PAYMENT_MAX_RETRIES: int = 4
    AGENT_NOTIFICATION_WEBHOOK_URL: str = ""
    AGENT_NOTIFICATION_TOKEN: str = ""
    ESCALATION_MATRIX_JSON: str = "{}"
    BUSINESS_TIMEZONE: str = "Africa/Harare"
    BUSINESS_HOURS_JSON: str = "{}"
    HANDOFF_API_KEY: str = ""

    # InsureTech product, quotation, and application API. Policy-number and
    # cover-activation operations remain disabled until their business gates
    # and prerequisites are explicitly approved.
    INSURETECH_API_BASE_URL: str = ""
    INSURETECH_API_TOKEN: str = ""
    INSURETECH_API_EMAIL: str = ""
    INSURETECH_API_PASSWORD: str = ""
    INSURETECH_LOGIN_PATH: str = "/auth/login"
    INSURETECH_API_RESOLVED_IPS: str = ""
    INSURETECH_PRODUCTS_PATH: str = "/products"
    INSURETECH_PRODUCT_PATH: str = "/products/{product_code}"
    INSURETECH_QUOTE_PATH: str = "/products/{product_code}/quote"
    INSURETECH_APPLICATIONS_PATH: str = "/products/{product_code}/applications"
    INSURETECH_APPLICATION_PATH: str = "/products/{product_code}/applications/{application_id}"
    INSURETECH_APPLICATION_SUBMIT_PATH: str = (
        "/products/{product_code}/applications/{application_id}/submit"
    )
    INSURETECH_PAYMENT_METHODS_PATH: str = "/payments/methods"
    INSURETECH_PAYMENT_STATUS_PATH: str = "/payments/{payment_id}/status"
    INSURETECH_PRODUCT_POLICY_NUMBER_PATH: str = "/products/{product_code}/policy-number"
    INSURETECH_APPLICATION_POLICY_NUMBER_PATH: str = (
        "/products/{product_code}/applications/{application_id}/policy-number"
    )
    INSURETECH_COVER_ACTIVATION_PATH: str = (
        "/products/{product_code}/applications/{application_id}/cover/activate"
    )
    INSURETECH_POLICY_NUMBER_ENABLED: bool = False
    INSURETECH_COVER_ACTIVATION_ENABLED: bool = False
    INSURETECH_APPLICATION_TRACKING_ENABLED: bool = False

    # Commercial workflow integration boundaries. Empty values keep the
    # corresponding capability safely disabled; the bot still captures a
    # traceable request without representing it as a quote or policy.
    QUOTE_API_BASE_URL: str = ""
    QUOTE_API_TOKEN: str = ""
    QUOTE_REQUEST_PATH: str = "/quotes"
    CRM_API_BASE_URL: str = ""
    CRM_API_TOKEN: str = ""
    CRM_LEAD_PATH: str = "/leads"
    COMMERCIAL_RULES_PATH: str = "data/commercial_rules.json"
    FOLLOW_UP_ENABLED: bool = False
    FOLLOW_UP_TEMPLATES_JSON: str = "{}"
    FOLLOW_UP_WINDOW_HOURS: int = 72
    PAYMENT_CALLBACK_SECRET: str = ""
    INTERNAL_API_KEY: str = ""

    # Business-owned public content. Unverified destinations stay blank and are not published.
    HEAD_OFFICE_ADDRESS: str = "66 Julius Nyerere Way, Harare, Zimbabwe"
    TOLL_FREE_NUMBER: str = "+263 8080835"
    CUSTOMER_CARE_EMAIL: str = "customercare@fidelitylife.co.zw"
    FUNERAL_EMERGENCY_PHONE: str = ""
    FLIMAS_MEMBER_URL: str = ""
    FLIMAS_PROVIDER_DIRECTORY_URL: str = ""
    FLIMAS_ANDROID_URL: str = ""
    FLIMAS_IOS_URL: str = ""
    CONSENT_NOTICE_VERSION: str = "2026-10-draft"

    # Replaceable English interface and approved-information catalogs. These files are
    # business content, so they can be reviewed and released without changing
    # workflow code.
    LANGUAGE_CATALOG_PATH: str = "data/languages.json"
    APPROVED_KNOWLEDGE_PATH: str = "data/approved_knowledge.json"
    KNOWLEDGE_MATCH_THRESHOLD: float = 0.42
    SATISFACTION_SURVEY_ENABLED: bool = True

    # Outbound API resilience
    API_TIMEOUT_SECONDS: float = 10.0
    API_MAX_RETRIES: int = 2
    PAYMENT_POLL_INTERVAL_SECONDS: int = 30
    PAYMENT_POLL_MAX_ATTEMPTS: int = 20

    # Optional deduplication TTL in seconds (default: 15 minutes)
    DEDUPLICATION_TTL_SECONDS: int = 900

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @property
    def is_configured(self) -> bool:
        """Check if all required WhatsApp credentials are provided."""
        return bool(
            self.WHATSAPP_ACCESS_TOKEN
            and self.WHATSAPP_PHONE_NUMBER_ID
            and self.WHATSAPP_VERIFY_TOKEN
        )

    def masked_summary(self) -> dict:
        """Return a dictionary of configuration with sensitive secrets masked for safe logging."""
        def mask(val: str, prefix_len: int = 4, suffix_len: int = 3) -> str:
            if not val:
                return "<NOT_SET>"
            if len(val) <= prefix_len + suffix_len:
                return "***"
            return f"{val[:prefix_len]}...{val[-suffix_len:]}"

        return {
            "WHATSAPP_PHONE_NUMBER_ID": self.WHATSAPP_PHONE_NUMBER_ID or "<NOT_SET>",
            "META_GRAPH_API_VERSION": self.META_GRAPH_API_VERSION,
            "WHATSAPP_VERIFY_TOKEN": mask(self.WHATSAPP_VERIFY_TOKEN, 2, 2),
            "WHATSAPP_ACCESS_TOKEN": mask(self.WHATSAPP_ACCESS_TOKEN, 6, 4),
            "META_APP_SECRET": mask(self.META_APP_SECRET, 3, 2),
            "IS_CONFIGURED": self.is_configured,
            "PORT": self.PORT,
            "LOG_LEVEL": self.LOG_LEVEL,
            "DATABASE": "configured" if self.DATABASE_URL else "<NOT_SET>",
            "CUSTOMER_POLICY_API": bool(self.CUSTOMER_POLICY_API_BASE_URL),
            "PAYMENT_API": bool(self.PAYMENT_API_BASE_URL),
            "PAYMENT_VERIFICATION": bool(
                self.PAYMENT_VERIFICATION_START_PATH
                and self.PAYMENT_VERIFICATION_CONFIRM_PATH
                and self.PAYMENT_ELIGIBLE_POLICIES_PATH
            ),
            "AGENT_NOTIFICATION": bool(self.AGENT_NOTIFICATION_WEBHOOK_URL),
            "INSURETECH_API": bool(
                self.INSURETECH_API_BASE_URL
                and (
                    self.INSURETECH_API_TOKEN
                    or (self.INSURETECH_API_EMAIL and self.INSURETECH_API_PASSWORD)
                )
            ),
            "INSURETECH_POLICY_NUMBER": self.INSURETECH_POLICY_NUMBER_ENABLED,
            "INSURETECH_COVER_ACTIVATION": self.INSURETECH_COVER_ACTIVATION_ENABLED,
            "MENU_CATALOGUE_V11": self.MENU_CATALOGUE_V11_ENABLED,
            "QUOTE_API": bool(self.QUOTE_API_BASE_URL and self.QUOTE_API_TOKEN),
            "CRM_API": bool(self.CRM_API_BASE_URL and self.CRM_API_TOKEN),
            "PAYMENT_CALLBACK_AUTH": bool(self.PAYMENT_CALLBACK_SECRET),
            "CUSTOMER_VERIFICATION": bool(self.CUSTOMER_VERIFICATION_PATH),
            "APP_ENV": self.APP_ENV,
        }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
