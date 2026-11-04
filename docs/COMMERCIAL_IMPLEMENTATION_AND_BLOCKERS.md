# Commercial implementation and blocker register

Assessment date: 2026-10-20

## Payments wireframe increment

The seven Fidelity business areas from the supplied payments wireframe now appear
at the start of Self Service. Life Assurance contains the wireframe actions for
exploration, products, quotation, application, existing policies, payments,
claims, documents and FAQs.

The Make a Payment workflow now includes backend-owned identity verification
(maximum three code attempts), verified profile and eligible-policy selection,
USD/ZiG payment preparation, EcoCash, O'mari, InnBucks, bank transfer and secure
Visa/Mastercard routes, a four-attempt transaction limit, explicit provider
confirmation and proof-of-payment intake. Codes and payment contacts are redacted
from routine message history. A proof attachment creates a
`pending_finance_verification` request and never marks a policy paid.

Activation still requires the approved payment API base URL and credentials,
verification start/confirm endpoints, eligible-policy endpoint, authoritative
currency/rate preparation, payment initiation/status responses, provider-hosted
card URLs and approved bank-transfer instructions. These dependencies remain
fail-closed in runtime readiness.

This register reconciles the Customer Care WhatsApp AI Chatbot Scope Document,
the supplied commercial gap tracker and the executable code. “Implemented” means
there is a traced persistence-to-workflow path with tests. It does not mean an
unconfigured Fidelity dependency has been simulated.

## Implemented in this increment

| Capability | Current implementation | Truth/safety boundary |
|---|---|---|
| Product information | Approved English retrieval catalogue covers the group overview, funeral, Vaka Yako, savings/retirement, FLIMAS and contact routes. | No premiums, benefit limits, waiting periods, exclusions or guarantees were invented. |
| Needs analysis | `Needs & Quote Guidance` captures product interest, customer goal, people count, budget range, currency, existing cover and explicit follow-up permission. | `commercial_rules.json` is disabled by default, so the result is `rules_pending`, not advice. |
| Lead management | Every completed needs assessment and service sales enquiry creates a durable lead with source, interest, language, consent, qualification state, team and structured context. | CRM delivery is not claimed until the CRM adapter is configured and acknowledges delivery. |
| Quote preparation | A quote request receives a reference and `pricing_pending` state. The internal pricing endpoint supports price, currency, external reference and expiry. Customers can check status and accept only a priced, unexpired quote. | A pricing-pending record is explicitly not a formal quote. No local rate table exists. |
| Application preparation | A pre-application intent and checklist boundary are recorded after customer interest or valid quote acceptance. | This is not KYC, underwriting, signature, approval or issuance. |
| Follow-up automation | Consent basis, scenario, due time, template name and state are persisted. A protected due-work endpoint is available. | Sending is disabled unless both an approved template mapping and explicit enablement are configured. |
| Payments | Existing initiation/polling is retained. A signed, idempotent provider callback now records the event and updates only a known transaction. | Unknown/unsigned callbacks are rejected. No callback creates a policy or fabricates receipt confirmation. |
| Commercial analytics | Protected aggregates report leads by status/product, quote states, application-intent states, payment states, follow-up states and verified payment value. | Pending payments and quote requests are not revenue. PII is excluded from the aggregate response. |
| Integration boundaries | Typed HTTP adapters exist for core policy, payment, agent notification, quote and CRM services. | Empty endpoints/tokens fail closed. |
| Security/reliability | New internal operations require a dedicated internal key; payment callbacks require body HMAC; identifiers/statuses/amounts/expiry are validated; callback events are idempotent. | Secrets and provider payloads are not logged or stored wholesale. |

## Previously implemented and retained

- Meta webhook verification, signature validation, deduplication and status tracking.
- Persistent contacts, conversations, messages, sessions, service requests,
  transactions, escalations, permissions, operational events and surveys.
- English-only personalised greeting and controlled approved-content Q&A.
- Life, funeral, FLIMAS, contact, urgent assistance and complaints routes.
- Seven-service onboarding shell with consent, identity/reference capture,
  relationship discovery/review and account-link persistence.
- Protected policy details, payment history, payment initiation/status and claim
  status adapters.
- Agent takeover/release lifecycle and development simulator.

## Exact blockers

| Affected feature | Missing dependency | Why completion is blocked | Independent work completed | Required to finish |
|---|---|---|---|---|
| Deterministic recommendations | Approved eligibility, suitability and product-mapping rules, rule owner and version | Recommendation would otherwise be unapproved financial/insurance guidance. | Approval-gated rule loader, structured answers and qualification states. | Business-approved `commercial_rules.json`, test cases and sign-off reference. |
| Formal quotations | Authoritative rating tables or quote API; rounding, tax/currency, validity and disclosure rules | Any locally invented premium is misleading. | Request/reference/status, pricing adapter, authenticated price update, expiry and acceptance. | Quote API contract/credentials or signed rate specification plus product/actuarial approval. |
| CRM pipeline delivery | CRM/lead platform URL, credentials, field mapping, ownership/status model and idempotency contract | A local lead is not proof that a sales team received it. | Durable lead model and CRM adapter. | UAT endpoint, auth, required-field map, status callbacks and operational owner. |
| Application and policy issuance | KYC/identity API, underwriting questions/rules, document service, e-signature, core application/issuance API | The bot cannot verify identity, underwrite, sign or issue independently. | Intent/checklist state and explicit integration boundary. | Approved contracts, authentication method, document controls, underwriting decision codes and UAT access. |
| Existing-customer self-service | Fidelity core verification, policy, payment-history, claims and onboarding endpoints/credentials | Protected records must not be inferred or disclosed without verified backend authority. | Adapters, fail-closed workflow, validation and error handling. | Endpoint paths, tokens/certificates, schemas, error codes, identity rules and test records. |
| Live payments/reconciliation | Approved gateway URL/token, payment methods, callback secret, provider status/refund/reversal mapping and finance process | Receipt and revenue require provider confirmation and finance reconciliation. | Initiation/status adapter, transaction states, callback verification/idempotency and verified-only analytics. | Gateway UAT access, signing specification, method configuration, reconciliation owner and acceptance evidence. |
| Agent operations | Agent webhook URL/token, routing matrix, business hours, queue acknowledgements and SLA ownership | A stored escalation is not proof of queue delivery or response. | Escalation persistence, notification adapter, truthful failure text and takeover lifecycle. | Agent platform contract, routing/SLA configuration and monitored support roster. |
| Proactive follow-ups | Approved WhatsApp templates per language, opt-out wording, send windows, consent/retention policy and template IDs | WhatsApp template and consent rules prevent arbitrary production outreach. | Scheduler records and protected due-work endpoint; no automatic sending. | Meta-approved template IDs, CX/legal approval, frequency rules, opt-out processing and explicit enablement. |
| Production deployment | Persistent HTTPS hosting/domain, secrets vault, production SQL Server, backups, monitoring/alerts, retention policy and UAT/sign-offs | The current quick tunnel/development process has no production uptime or governance guarantee. | Health/readiness/diagnostic endpoints, configuration masking and runbook. | Infrastructure owner, certificates/DNS, service identity, monitoring, DR/backups, security/privacy/legal/business approvals. |

## Scope interpretation

The supplied scope is principally a customer-care and self-service scope. It
explicitly excludes acquisition campaigns, building core systems, a separate AI
model and the complete claims/complaints lifecycle. Needs analysis, formal quotes,
applications, CRM automation and commercial analytics are therefore implemented
as controlled extensions requested after that draft. They require change control,
business ownership and acceptance criteria before being called in-scope production
deliverables.

## Validation evidence

Run `venv\Scripts\python.exe -m pytest -q`. The suite exercises existing menu,
onboarding, Q&A, payments, handoff and survey behaviour plus the new needs-to-lead,
quote lifecycle, payment callback and analytics paths. Runtime readiness remains
the authority for environment-specific missing dependencies.
