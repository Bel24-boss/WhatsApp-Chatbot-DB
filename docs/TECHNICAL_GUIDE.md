# Technical Guide

## Request flow

1. Meta sends a signed event to `POST /webhook`.
2. The service validates `X-Hub-Signature-256` before parsing the payload.
3. Duplicate message IDs are rejected using persistent storage plus the in-memory TTL cache.
4. Contact, conversation, and inbound message records are persisted.
5. The workflow engine loads the customer's active session and handles navigation or service input.
6. Approved Fidelity APIs are called when a workflow requires customer data or a transaction.
7. The reply is sent through Meta and recorded with its Meta message ID.
8. Meta delivery events update the persisted message status.
9. Escalations are stored before agent notification is attempted; the customer sees queue success only after acknowledgment.
10. A takeover acknowledgment pauses automated replies until the agent platform sends release, resolution, or rejection.
11. WhatsApp onboarding collects consent and minimum identity/reference fields, while the configured backend owns verification and authority decisions.
12. Only eligible masked relationships are shown; each confirmed link outcome is stored idempotently.
13. Public natural-language questions are matched only against approved English knowledge entries; low-confidence questions fall back safely.
14. Completed or abandoned journeys can enter the structured satisfaction survey and optionally return to consent-based agent handoff.

## Database entities

- `contacts`: WhatsApp identity and display name
- `conversations`: active and historical customer conversations
- `messages`: inbound/outbound content and delivery status
- `conversation_sessions`: workflow state, context, and expiry
- `service_requests`: policy, payment-history, and claim requests
- `transactions`: payment references and status
- `escalations`: category, routing team, notification status, and timestamps
- `content_records`: versioned content with owner, source, approval state, and effective dates
- `permission_records`: permission scope, decision, timestamp, and notice version
- `operational_events`: minimal workflow outcomes without customer free text
- `satisfaction_responses`: journey outcome, resolved result, rating, optional comment, language, and agent-contact preference
- `service_contacts`: owned and validated contact destinations
- `service_links`: owned, validated, enabled service destinations
- `onboarding_attempts`: selected service, journey, notice version, external attempt and outcome
- `digital_profiles`: stable local-to-external profile binding
- `customer_relationship_links`: business, role, masked reference, source status, permissions and link outcome

## Security controls

- Meta HMAC signature verification; production fails closed when the app secret is missing
- Constant-time webhook and handoff-key comparisons
- Secrets loaded from environment variables
- Masked phone and message identifiers in operational logs
- Protected internal handoff/history routes
- Input length and format validation
- Retry only for transient failures
- No fallback or generated customer records
- No generative product-answer path; Ask a Question is retrieval-only and protected intents are redirected
- Onboarding ID numbers and relationship references are redacted from routine message history
- No private relationship is displayed unless the backend explicitly confirms identity and authority

Database encryption, secret management, network restrictions, retention, and access auditing must be supplied by the deployment environment.

## Operations

- `GET /health` reports component configuration without exposing secrets.
- Set `RELOAD=false` outside local development.
- Use approved SQL Server instances in UAT and production through ODBC Driver 18.
- Keep the FastAPI service and public HTTPS endpoint continuously available.
- Alert on webhook signature failures, outbound failures, integration failures, and escalation notification failures.

## Release validation

1. Run `python -m pytest -q`.
2. Verify `/health` reports WhatsApp and required integrations configured.
3. Verify the public webhook challenge returns the exact challenge body.
4. Send inbound text and interactive-list messages from an approved test number.
5. Confirm outbound delivery status reaches `delivered` or `read`.
6. Exercise each connected Fidelity API using authorized synthetic UAT data.
7. Confirm session timeout, duplicate handling, navigation, escalation routing, and after-hours behavior.
8. Complete security, privacy, disaster-recovery, UAT, and business sign-off before production.
9. Have the content owner review English insurance terminology and regression-test common synonyms before release.
10. Review expired knowledge entries and validate satisfaction-response retention and access controls.
