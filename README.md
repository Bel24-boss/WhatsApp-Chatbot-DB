# Fidelity Life Assurance WhatsApp Chatbot

FastAPI service for Fidelity Life Assurance customer self-service over Meta's WhatsApp Cloud API.

## Implemented capabilities

- Meta webhook verification and HMAC signature validation
- Incoming text, list, and button message parsing
- Outbound text and WhatsApp interactive-list messages
- Delivery/read/failure status tracking and duplicate prevention
- Persistent contacts, conversations, messages, sessions, requests, transactions, and escalations
- Controlled content, service contacts/links, permission records, and operational events
- Menu Catalogue 1.1 entry routes: Explore Insurance Products, Apply for Insurance, Track an Application, Payments, Policy & Cover Assistance, and Agent / Contact Us
- InsureTech-backed product listing and verified product details, with product-code continuity into quote/application entry points
- Capability-gated quote, application tracking, payments, policy-number and cover-activation journeys that fail closed until their schemas, authorisation rules and business prerequisites are approved
- Legacy Funeral Services, FLIMAS and the broader seven-business Self Service catalogue remain reachable through Other Fidelity Services
- English-only configurable interface content
- Retrieval-only natural-language answers from explicitly approved Fidelity knowledge; protected intents route to deterministic workflows
- Post-completion and post-abandonment satisfaction survey with resolution, 1–5 rating, optional comment, and agent follow-up
- WhatsApp onboarding for seven Fidelity services, with existing, new, forgotten-reference, and representative journeys
- Consent, identity/reference capture, masked relationship discovery, multi-account review, and idempotent linking
- Direct service route IDs from the approved catalogue, including urgent bereavement priority
- Session timeout plus global `0. Main Menu`, `Back`, and `Cancel` navigation
- Wireframe-aligned Life Assurance menu and payment workflow: backend identity verification, verified profile, eligible-policy selection, USD/ZiG preparation, EcoCash, O'mari, InnBucks, approved bank-transfer instructions/POP review, secure card links, provider status checks and receipts
- Complaints, human escalation, routing matrix, after-hours detection, and agent notifications
- Consent-controlled conversation sharing and truthful queue acknowledgement
- Bot pause after agent takeover acknowledgement and resume after release
- Authenticated AI-to-chatbot workflow handoff and conversation-history endpoints
- Retry and timeout handling for Meta, core-system, payment, and notification APIs
- Privacy-aware operational logging
- Structured sales leads, needs assessments, qualification state and consent-aware follow-up records
- Quote-request lifecycle with pricing-pending safety, authenticated pricing updates, expiry and acceptance handling
- Pre-application intent records that never imply underwriting approval or policy issuance
- HMAC-authenticated, idempotent payment callbacks and reconciliation-safe transaction states
- Protected commercial funnel analytics that count only confirmed payment outcomes as value
- Quotation and CRM adapter boundaries for future authorised Fidelity services

No customer, policy, payment, or claim records are fabricated by the application. Customer-facing data is returned only by configured Fidelity APIs.

## Application structure

```text
app/
  catalog.py           Fidelity service and menu catalogue
  commercial.py        Approval-gated suitability-rule loader
  config.py            Environment configuration
  database.py          SQLAlchemy persistence and repositories
  integrations.py      InsureTech, Fidelity core, payment, quote, CRM, and agent API clients
  knowledge.py         Approved-content natural-language retrieval
  localization.py      Configurable English content loader
  workflow.py          Stateful Fidelity conversation engine
  whatsapp_client.py   Meta WhatsApp Cloud API client
  main.py              FastAPI routes and webhook orchestration
  security.py          Meta webhook signature validation
  deduplication.py     Duplicate-message protection
  simulator.html       Development-only WhatsApp-style browser preview
tests/                 Workflow, persistence, and webhook tests
docs/                  Technical and integration documentation
data/languages.json    English interface content
data/approved_knowledge.json  Approved English question/answer content
data/commercial_rules.json    Business-owned product/suitability controls (disabled by default)
```

## Local setup

```powershell
cd "C:\Users\believez\OneDrive - Fidelity Life Assurance\Documents\cynex-whatsapp-bot"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

The health endpoint is available at `http://127.0.0.1:8000/health`.
The deployment-readiness endpoint is available at `http://127.0.0.1:8000/readiness` and returns every missing production input.
In development, `http://127.0.0.1:8000/diagnostics/whatsapp` performs a safe live check against Meta. It reports authentication, the masked registered number, and Meta error codes without returning any token or app secret.
For this environment, a healthy Meta diagnostic must show `authenticated: true`, `phone_number_id_matches: true`, and a masked display number ending in `0349`.

### Browser chatbot preview

While the server is running in a non-production environment, open:

```text
http://127.0.0.1:8000/simulator
```

The preview uses the real conversation engine and configured database, but it does not send messages through Meta. It is currently configured for the registered number `263781380349`; use the Fidelity menu buttons or type a message. The simulator route is disabled when `APP_ENV=production`.

For a temporary HTTPS webhook URL, use a separate terminal:

```powershell
.\start_tunnel.ps1
```

Set the Meta callback URL to `https://CURRENT-TUNNEL.trycloudflare.com/webhook`. Quick Tunnel URLs change when the tunnel restarts.
Use a named Cloudflare Tunnel or an approved hosted HTTPS endpoint for persistent Meta webhooks; quick tunnels have no uptime guarantee.

### Live WhatsApp activation

Before testing from a separate personal WhatsApp account, confirm all of the following:

- `.env` contains a current permanent System User token with `whatsapp_business_messaging` and `whatsapp_business_management` permissions.
- `WHATSAPP_PHONE_NUMBER_ID` belongs to the registered Fidelity number, not Meta's temporary test number.
- The Meta app is subscribed to the WhatsApp Business Account and the Webhooks `messages` field.
- Meta's callback URL is the current public HTTPS URL ending in `/webhook`, and webhook verification succeeds.
- The API server and tunnel/hosting service remain running throughout the test.
- The Meta app is in the appropriate mode and the sender is an allowed recipient while the app is in development mode.

See `docs/LIVE_WHATSAPP_RUNBOOK.md` for the verification sequence and safe diagnostic commands.

## Configuration

Copy `.env.example` to `.env` and configure approved credentials locally. Never commit `.env` or paste credentials into chat, tickets, or documentation.

For production, set:

```ini
RELOAD=false
DATABASE_URL=mssql+pyodbc://@SERVER/DatabaseName?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes
```

The local database is `FidelityWhatsAppBot` on the default SQL Server instance using Windows integrated authentication. UAT and production should use approved SQL Server instances with encrypted connections, backups, least-privilege service identities, network controls, and an approved retention policy. SQLite is used only for isolated automated tests.

### Menu Catalogue 1.1 and InsureTech

`MENU_CATALOGUE_V11_ENABLED=true` enables the six-option customer menu defined by
Menu Catalogue 1.1. Product discovery reads only from the configured InsureTech
API; when it is unavailable, the bot does not substitute an invented product list.

The official InsureTech OpenAPI 3.1 contract is mapped to the chatbot's product,
quote, application submission, payment-method, and payment-status journeys. Configure `INSURETECH_API_BASE_URL` and
prefer a dedicated `INSURETECH_API_TOKEN`. When a service token is unavailable,
set `INSURETECH_API_EMAIL` and `INSURETECH_API_PASSWORD` for a dedicated service
account; the client logs in through `/auth/login` and reauthenticates once after a
401 response. Do not use a personal Swagger password in deployed environments.

Quotes send the required `lives_assured` field. Draft applications send the
approved applicant and `lives_assured` structures and use an idempotency key.
Application intake normalizes Zimbabwe national IDs to `08-212-3471R-03` and
mobile numbers to `+263 77 123 4567`. Supported mobile prefixes are Econet
`77`, `78`, and `79`; NetOne `71`; and Telecel `73`.
Application tracking remains disabled unless
`INSURETECH_APPLICATION_TRACKING_ENABLED=true` and the approved customer-verification
service is also configured.

Policy-number allocation and cover activation are independently protected by
`INSURETECH_POLICY_NUMBER_ENABLED` and `INSURETECH_COVER_ACTIVATION_ENABLED`. Keep
both false until Fidelity approves the application, payment, underwriting,
authorisation, retry, and audit conditions. Unsafe POST/PUT requests are not
automatically retried unless they carry an idempotency key.

### English interface and approved Q&A content

The language and knowledge catalogs are configured with `LANGUAGE_CATALOG_PATH` and
`APPROVED_KNOWLEDGE_PATH`. The chatbot operates only in English. New customers open
directly on the English main menu, and legacy sessions that were waiting for a language
selection are normalized to English.

To revise interface wording, edit the English entry in `data/languages.json` and keep the
same message keys. Valid catalog changes are reloaded automatically when the next relevant
message arrives.

To extend Ask a Question, add a topic to `data/approved_knowledge.json` with:

- a stable `id`, accountable `owner`, and `review_due` date;
- `approved: true` only after business approval;
- natural English customer phrasings in `patterns.en`;
- reviewed English answers in `answers.en`.

The matcher does not generate new product facts. It returns only approved answers above
`KNOWLEDGE_MATCH_THRESHOLD`; otherwise it asks the customer to rephrase or contact an
agent. Questions involving personal policies, claims, payments, or account linking are
routed to the existing protected workflow. Lowering the threshold increases coverage but
also increases wrong-answer risk, so tune it against an approved English test set.

## Fidelity API contracts

The current adapter expects these configurable operations:

- `GET {POLICY_DETAILS_PATH}` with `policy_number` in the path and `customer_wa_id` as a query parameter
- `POST {CUSTOMER_VERIFICATION_PATH}` before protected policy, claim, payment-history, or payment operations
- `POST {ONBOARDING_START_PATH}` for backend identity, reference, duplicate, role, and authority decisions
- `GET {ONBOARDING_RELATIONSHIPS_PATH}` for eligible masked relationships after verification
- `POST {ONBOARDING_LINK_PATH}` for digital-profile creation and per-relationship link outcomes
- `GET {PAYMENT_HISTORY_PATH}` with `policy_number` in the path and `customer_wa_id` as a query parameter
- `GET {CLAIM_STATUS_PATH}` with `reference` in the path and `customer_wa_id` as a query parameter
- `POST {PAYMENT_INITIATION_PATH}` with policy, amount, method, and notification-mobile fields
- `POST {PAYMENT_VERIFICATION_START_PATH}` and `POST {PAYMENT_VERIFICATION_CONFIRM_PATH}` for backend-owned payment identity verification
- `GET {PAYMENT_ELIGIBLE_POLICIES_PATH}` for payment-eligible policies after successful verification
- `POST {PAYMENT_PREPARATION_PATH}` for authoritative amount/currency calculation before a method is selected
- `GET {PAYMENT_STATUS_PATH}` with the payment reference in the path
- `POST AGENT_NOTIFICATION_WEBHOOK_URL` with escalation and conversation context

All endpoint paths are configurable. See `docs/INTEGRATION_CONTRACTS.md` before connecting an environment.

The WhatsApp flow intentionally contains no OTP or authentication-challenge workflow. It still fails closed: private relationship discovery and linking require an approved backend response confirming identity and applicable authority.

## AI handoff

Configure `HANDOFF_API_KEY`, then call:

```http
POST /internal/handoff
X-Handoff-Key: <configured key>
Content-Type: application/json

{
  "wa_id": "263XXXXXXXXX",
  "workflow_id": "policy_enquiry",
  "context": {},
  "send_message": true
}
```

Supported workflow identifiers are `main_menu`, `life_assurance`, `funeral_services`, `flimas`, `policy_enquiry`, `payment_history`, `payments`, `claims`, `customer_service`, `complaints`, `human_agent`, `sales_guidance`, and `quote_status`. Service IDs such as `1.1`, `2.3`, and `3.2` are also accepted.

## Commercial operations

Needs answers and consent are stored as a sales lead. Because the default
`data/commercial_rules.json` is not business-approved, the bot records
`rules_pending` and does not recommend a product. A quote request is stored as
`pricing_pending` with no premium. An authorised internal service can later post
a price, currency and expiry to `POST /internal/quotes/{quote_id}/pricing` using
`X-Internal-Key`. Customers can type `Quote Status` and accept only a priced,
unexpired quote; acceptance creates a pending application intent, not a policy.

Payment providers post signed outcomes to `POST /internal/payments/callback`
using `X-Payment-Signature: sha256=<HMAC>`. Commercial aggregates are available
at `GET /internal/analytics/commercial`, and due follow-up work at
`GET /internal/follow-ups/due`; both require `X-Internal-Key`. The follow-up
endpoint never sends messages. Sending remains disabled until approved WhatsApp
templates and `FOLLOW_UP_ENABLED=true` are configured.

Conversation history is available to authorized internal services through:

```http
GET /internal/conversations/{wa_id}/history
X-Handoff-Key: <configured key>
```

Agent platforms update takeover and release state through:

```http
POST /internal/escalations/{escalation_id}/status
X-Handoff-Key: <configured key>
Content-Type: application/json

{"status": "takeover_acknowledged"}
```

Supported lifecycle values are `queue_acknowledged`, `takeover_acknowledged`, `released`, `resolved`, and `rejected`.

## Tests

```powershell
python -m pytest -q
```

Verify that the configured database is reachable and synchronized with the
SQLAlchemy models:

```powershell
python scripts/check_database_sync.py
python scripts/check_database_sync.py --write-probe
```

The first command is read-only. The optional write probe inserts and reads a
temporary contact inside a transaction that is always rolled back.

## Required business inputs

The source-to-code decisions are recorded in `docs/REQUIREMENTS_TRACEABILITY.md`. Remaining activation inputs are listed in `docs/REQUIRED_INPUTS.md`. External workflows remain unavailable until approved Fidelity endpoints, credentials, wording, routing, and operating rules are configured.
