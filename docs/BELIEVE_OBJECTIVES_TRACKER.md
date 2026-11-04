# Believe Objectives Delivery Tracker

Status date: 15 October 2026

## Purpose

This tracker maps every task assigned to `Belive`, `Believe`, or jointly to Believe in the approved project export against repository evidence, live evidence, organisational acceptance, dependencies, and the next joint action.

The project export contains outdated task statuses. This document does not treat code completion as business acceptance: both are tracked separately.

## Status model

- **Built**: the required capability exists in the current application and has automated or live evidence.
- **Partial**: supporting code exists, but part of the deliverable or required validation is missing.
- **Not built**: the deliverable has not been implemented, was deliberately deferred, or requires an organisational decision first.
- **Verified live**: exercised through the registered Fidelity WhatsApp number and Meta Cloud API.
- **Tested locally**: covered by automated tests or the local SQL Server/simulator, but not accepted in the target environment.
- **Blocked externally**: Believe cannot close the objective without an approved contract, endpoint, data, environment, decision, or sign-off.

## Portfolio summary

| Measure | Result |
| --- | ---: |
| Believe-owned or jointly owned task objectives | 71 |
| Built | 58 (82%) |
| Partial | 9 (13%) |
| Not built or scheduled later | 4 (6%) |
| Automated tests passing | 35 |
| Live WhatsApp inbound-to-outbound path | Verified |
| Current deployment readiness | Not production-ready |

The implementation-adjusted position is approximately 88% when partial items are counted at half completion. This is a development-progress indicator, not an approved project percentage.

## Objective-by-objective assessment

### M1 — Requirements and solution design

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 1.8 | Define database requirements | Partial | Blocked externally | SQL Server schema and persistence are implemented in `app/database.py`. Believe must produce the final ERD/data dictionary; Munashe, ICT infrastructure, security/privacy, and records management must approve retention, encryption, backup, recovery, roles, and UAT/production topology. |

### M3 — WhatsApp API and backend foundation

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 3.1 | Create backend project/repository | Built | Tested locally | Existing FastAPI repository, application modules, tests, and documentation. Update the central tracker to Completed. |
| 3.2 | Configure development environment | Built | Verified live | Python environment, SQL Server, FastAPI server, Meta connection, and browser simulator operate locally. Document the approved developer onboarding baseline. |
| 3.3 | Configure environment variables | Built | Tested locally | Typed settings and `.env.example` exist. Production secrets must later move to the approved secret manager under M12. |
| 3.4 | Create health-check endpoint | Built | Verified live | `/health`, `/readiness`, and safe Meta diagnostics are implemented. Update the tracker to Completed. |
| 3.5 | Implement WhatsApp webhook verification | Built | Verified live | Local and public challenge verification return HTTP 200. Signature validation remains enabled. |
| 3.6 | Implement incoming-message webhook | Built | Verified live | A real inbound WhatsApp interactive event was accepted and processed through `/webhook`. Update the tracker from In Progress to Completed. |
| 3.7 | Parse incoming messages | Built | Verified live | Text, list replies, button replies, unsupported message fallback, and payload validation are implemented. |
| 3.8 | Extract sender/message identifiers | Built | Verified live | Sender and Meta message IDs are validated, masked in logs, and persisted. |
| 3.9 | Implement outbound WhatsApp messages | Built | Verified live | Text and interactive-list messages are accepted by Meta; live status progressed through sent, delivered, and read. Update the tracker from On Hold to Completed. |
| 3.10 | Handle message statuses | Built | Verified live | Sent, delivered, read, and failure statuses update the persisted outbound message. Update the tracker from In Progress to Completed. |
| 3.11 | Implement message logging | Built | Verified live | Structured event logging covers webhook receipt, validation, routing, read receipts, outbound calls, Meta IDs, and failures without logging secrets or message bodies. Update the tracker from Not Started to Completed. |

### M4 — Database and session management

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 4.1 | Create customer/contact table | Built | Tested locally | `contacts` table exists in SQL Server. Include it in the approved data dictionary. |
| 4.2 | Create conversation table | Built | Tested locally | `conversations` table exists with active-status and contact relationships. |
| 4.3 | Create message table | Built | Verified live | Inbound/outbound messages, Meta IDs, statuses, and errors persist. |
| 4.4 | Create session table | Built | Tested locally | Stateful sessions persist with expiry timestamps and context. |
| 4.5 | Create transaction/request table | Built | Tested locally | `transactions` and `service_requests` exist. Activation depends on approved external APIs. |
| 4.6 | Create escalation table | Built | Tested locally | Escalations persist with team and lifecycle status. |
| 4.7 | Save incoming messages | Built | Verified live | Real Meta inbound messages are present in SQL Server. |
| 4.8 | Save outgoing messages | Built | Verified live | Live outbound message IDs and delivery/read states are present in SQL Server. |
| 4.9 | Implement conversation-history retrieval | Built | Tested locally | Authenticated internal history endpoint and repository query exist. |
| 4.10 | Implement session creation | Built | Verified live | Live menu selection created and advanced the WhatsApp state. |
| 4.11 | Implement session expiry/reset | Built | Tested locally | Expiry, reset, and customer expiry messaging are automated-test covered. |

### M5 — Core menu and workflow engine

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 5.1 | Implement main-menu engine | Built | Verified live | Fidelity main menu operates on WhatsApp. Final wording remains subject to business/content approval. |
| 5.2 | Implement submenu navigation | Built | Verified live | A real selection routed from `main_menu` to `life_menu`. Remaining menus are automated-test covered. |
| 5.3 | Implement conversation state management | Built | Verified live | SQL-backed state transitions and context preservation are operational. |
| 5.4 | Implement numbered/menu selections | Built | Tested locally | Numeric routes and stable service IDs are implemented. |
| 5.5 | Implement WhatsApp interactive buttons/lists | Built | Verified live | Interactive list send and inbound selection are proven. Update the tracker from In Progress to Completed. |
| 5.6 | Implement Back command | Built | Tested locally | Stateful parent-route behavior exists. Leslie must include it in formal QA acceptance. |
| 5.7 | Implement Main Menu command | Built | Tested locally | Returns to main menu while preserving eligible drafts for resume. |
| 5.8 | Implement Cancel command | Built | Tested locally | Cancels drafts without submitting requests or payments. |
| 5.9 | Implement invalid-selection handling | Built | Tested locally | Retry counting and agent offer after repeated invalid input are implemented. |
| 5.10 | Implement session timeout | Built | Tested locally | Configurable timeout and expiry response exist; business must approve final timeout values. |
| 5.11 | Implement confirmation screens | Built | Tested locally | Review/edit/cancel/submit confirmations exist for enquiries and payments. |

### M6 — AI agent to chatbot handoff

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 6.3 | Create chatbot workflow entry points | Built | Tested locally | Authenticated `POST /internal/handoff` exists. It cannot be activated until 6.1 and 6.2 are approved by Munashe. |
| 6.4 | Allow chatbot to start at a specific workflow | Built | Tested locally | Named workflow and service-ID deep links are supported. |
| 6.5 | Pass customer/session context into chatbot | Partial | Blocked externally | Generic context is accepted and preserved, but allowed fields and data classification are undefined. Munashe must supply the context contract; Believe then enforces a typed schema. |
| 6.6 | Validate handoff requests | Partial | Blocked externally | Authentication, WhatsApp ID, workflow ID, and basic payload validation exist. Completion requires an approved caller identity, configured key/identity mechanism, and field-level context validation. |
| 6.7 | Handle invalid/unknown workflow requests | Built | Tested locally | Unknown workflow IDs return a controlled validation response. Add contract-level tests after 6.1 is final. |
| 6.8 | Preserve WhatsApp conversation/session | Built | Tested locally | Handoff reuses the persisted contact, conversation, session, and optional outbound delivery. Joint integration testing remains. |

### M7 — Customer and core-system integrations

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 7.1 | Implement customer identification | Partial | Blocked externally | A fail-closed verification adapter and protected workflow gates exist. Fidelity must supply identity rules, endpoint, contract, credentials, and prohibited-data rules. |
| 7.2 | Implement policy-number capture | Built | Tested locally | Policy number prompts and capture exist. |
| 7.3 | Implement input validation | Built | Tested locally | Policy/reference/phone/amount validation and sensitive-value warnings exist. Business-format rules must be confirmed. |
| 7.4 | Build mock customer/policy API | Not built | Decision required | Earlier direction explicitly prohibited mocks. The team must formally descope this task or approve a controlled contract-test stub/sandbox; Believe should not silently mark it complete. |
| 7.5 | Integrate chatbot with mock API | Not built | Decision required | Blocked by the 7.4 conflict. Preferred organisational resolution: use an approved non-production core sandbox and rename the deliverable accordingly. |
| 7.7 | Implement policy-details enquiry | Partial | Blocked externally | Workflow, formatter, verification gate, and adapter exist, but no approved core API is configured. |
| 7.8 | Implement payment-history enquiry | Partial | Blocked externally | Workflow and adapter exist; operational completion requires the approved API and UAT data. |
| 7.9 | Implement API error handling | Built | Tested locally | Safe unavailable/not-found responses are implemented. |
| 7.10 | Implement timeout/retry handling | Built | Tested locally | Configurable timeout and bounded retry/backoff exist. |
| 7.11 | Implement integration logging | Built | Tested locally | Integration failures are logged without credentials or customer payloads. Production correlation/monitoring belongs to M12. |

### M8 — Payments and transactional services

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 8.2 | Capture policy number | Built | Tested locally; blocked externally | Activate only after the approved payment workflow and verification rules are supplied. |
| 8.3 | Capture payment amount | Built | Tested locally; blocked externally | Decimal validation exists. Business must approve currency, limits, fees, and rounding. |
| 8.4 | Select payment method | Built | Blocked externally | Configurable method menu exists, but `PAYMENT_METHODS_JSON` is empty. Finance/Payments must provide approved IDs and labels. |
| 8.5 | Capture/confirm mobile number | Built | Tested locally; blocked externally | WhatsApp-number confirmation and alternate international number capture exist. |
| 8.6 | Display transaction confirmation | Built | Tested locally; blocked externally | Review/confirm/cancel screen exists. Final wording requires compliance/business approval. |
| 8.8 | Implement payment-status polling | Built | Tested locally; blocked externally | Polling, bounded attempts, restart recovery, and terminal-state handling exist. Requires payment API testing. |
| 8.9 | Handle successful payment | Built | Tested locally; blocked externally | Success/reference response exists; payment-provider status mapping must be confirmed. |
| 8.10 | Handle failed payment | Built | Tested locally; blocked externally | Failure response and persistence exist; approved decline mappings are missing. |
| 8.11 | Handle pending payment | Built | Tested locally; blocked externally | Pending response and polling scheduling exist. |
| 8.12 | Return receipt/reference | Built | Tested locally; blocked externally | External reference is returned and persisted when supplied by the API. |
| 8.13 | Log transactions | Built | Tested locally; blocked externally | Transaction table and status updates exist. Retention, reconciliation, and audit requirements remain. |

### M9 — Human-agent escalation

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 9.1 | Implement Talk to Agent option | Built | Tested locally | Trigger and menu route exist. |
| 9.2 | Capture escalation category | Built | Tested locally | Life, Funeral, FLIMAS, Complaints, and General categories exist. |
| 9.3 | Capture customer details | Built | Tested locally | Permission, WhatsApp contact, category, and details are captured. |
| 9.4 | Capture chatbot workflow/history | Built | Tested locally | Consent-controlled history attachment exists. |
| 9.6 | Implement agent notification | Partial | Blocked externally | Notification adapter, acknowledgement handling, and failure wording exist. The approved destination, credentials, queue contract, and SLA are missing. |
| 9.7 | Implement after-hours handling | Partial | Blocked externally | Timezone-aware logic exists. Business hours, holidays, emergency rules, and approved after-hours wording are missing. |
| 9.8 | Record escalation status | Built | Tested locally | Open, notification failure, acknowledgement, takeover, release, resolution, and rejection lifecycle persistence exist. |

### M10 — Testing and QA

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 10.15 | Fix defects | Not built as a formal phase | Scheduled joint activity | Engineering defects found so far were fixed and 35 tests pass. Formal completion starts only when Leslie opens the defect register and assigns accepted defects to Believe/Munashe. |

### M11 — UAT and business sign-off

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 11.2 | Prepare UAT environment | Not built | Blocked externally and scheduled | Requires approved hosting, UAT SQL Server, network access, secret manager, Meta UAT configuration, test accounts/data, deployment process, and environment owner. Local development is not UAT. |

### M12 — Production deployment and handover

| ID | Believe objective | Build | Organisational position | Evidence and next joint action |
| --- | --- | --- | --- | --- |
| 12.7 | Prepare technical documentation | Partial | Drafted; finalisation scheduled | README, technical guide, contracts, live runbook, requirements traceability, required inputs, and this tracker exist. Final deployment topology, operational procedures, monitoring, backup/recovery, support ownership, and approved screenshots must be added after M11/M12 decisions. |

## Tracker corrections to submit now

The central project tracker should be updated with evidence—not merely percentages:

1. Mark 3.6, 3.9, 3.10, 3.11, 5.5, and 5.6 **Completed (development scope)**.
2. Keep 1.8 **In Progress** until the database design and governance review is signed off.
3. Mark 6.3, 6.4, 6.7, and 6.8 **Development Complete / Integration Pending**.
4. Keep 6.5, 6.6, 7.1, 7.7, 7.8, 9.6, and 9.7 **In Progress — External Dependency** and name the dependency owner.
5. Flag 7.4 and 7.5 as **Decision Required** because they conflict with the explicit no-mocks direction.
6. Mark Believe's M8 implementation tasks **Development Complete / Payment API Acceptance Pending**, not production complete.
7. Keep 10.15, 11.2, and final 12.7 closure aligned to their formal project phases.

## Joint execution roadmap

### Gate 1 — Close current MVP evidence

**Believe prepares:** live webhook evidence, passing test report, code references, current readiness output, database entity list, and the proposed tracker corrections above.

**Team provides:** a named approver for architecture/database, menus/content, security/privacy, operations, and each external integration.

**Together complete:** a 45-minute evidence review. Each task is marked `Accepted`, `Changes Requested`, or `Blocked`, with an owner and due date. Code completion alone must not be used as approval.

### Gate 2 — Finalise 1.8 database design

1. Believe generates the ERD, table/field data dictionary, index list, and environment-specific deployment/migration procedure.
2. Munashe validates architecture and integration relationships.
3. ICT infrastructure defines UAT/production SQL Server, encryption, backup, recovery, service identity, access roles, monitoring, and capacity.
4. Privacy/records owners approve classification, retention, deletion, masking, and audit rules.
5. The approver signs the database design; only then mark 1.8 complete.

### Gate 3 — Activate AI handoff

1. Munashe supplies 6.1 workflow identifiers and 6.2 request/response/authentication contract.
2. Believe converts generic context into approved typed models and configures the handoff credential in a non-production secret store.
3. Believe and Munashe run positive, unknown-workflow, unauthorized, invalid-context, resume-session, and duplicate-request tests.
4. Leslie records acceptance evidence for 6.9 and 6.10.

### Gate 4 — Activate core customer services

1. Ephraim/Munashe provide OpenAPI, sandbox URL, identity/verification rules, test credentials, safe test data, error catalogue, and rate limits.
2. The team resolves 7.4/7.5: formally descope mocks or approve a controlled contract-test stub. The preferred route is the approved core sandbox.
3. Believe maps the approved contract into the existing adapters without exposing protected data before verification.
4. Believe adds contract tests; Leslie executes policy and payment-history UAT scenarios.

### Gate 5 — Activate human escalation

1. Leslie/business owners provide the final matrix: queue destinations, priorities, SLAs, business hours, holidays, backups, emergency rules, and approved messages.
2. Munashe confirms team routing and agent-platform lifecycle contract.
3. Believe configures the matrix/hours, connects the notification endpoint, and verifies acknowledgement, failure, takeover, release, after-hours, and audit scenarios.
4. Operations accepts ownership of queue monitoring and unresolved escalation reporting.

### Gate 6 — Activate payments in the planned phase

1. Team approves the payment journey and compliance controls.
2. Ephraim/Munashe provide the sandbox contract and credentials.
3. Finance supplies methods, currency, limits, fees, references, reconciliation, refund, and status mappings.
4. Believe configures and contract-tests the existing capture, confirmation, initiation, polling, receipt, and transaction-log capabilities.
5. Leslie runs success, failure, timeout, duplicate, pending, and reconciliation test cases before business acceptance.

### Gate 7 — UAT, production, and handover

1. ICT provisions UAT hosting, SQL Server, networking, domain/TLS, secret management, monitoring, backup, and access.
2. Believe deploys the release candidate and produces environment-specific runbooks.
3. Leslie executes the approved UAT pack and manages the defect register; Believe/Munashe fix accepted defects.
4. After regression and sign-off, the production team replaces the temporary Quick Tunnel with approved permanent hosting and webhook routing.
5. Believe finalises 12.7 using the approved architecture and operational ownership model.

## Working-together control table

Use this structure in every Scrum or evidence-review session:

| Field | Required content |
| --- | --- |
| Objective ID | Exact tracker task ID |
| Build evidence | Code path, test, screenshot, log, API result, or database record |
| Acceptance criterion | Observable organisational outcome |
| Current result | Accepted, changes requested, or blocked |
| Dependency owner | Named person/team responsible for the missing input |
| Believe action | Specific implementation/documentation/testing action |
| Approver | Person authorised to close the objective |
| Due date | Agreed date, not an assumed date |
| Evidence link | Repository document, test report, or approved ticket |

## Immediate meeting agenda

1. Demonstrate the live WhatsApp inbound-to-outbound flow.
2. Approve the tracker corrections for M3 and M5.
3. Assign reviewers and a sign-off date for 1.8.
4. Obtain owners/dates for AI, core API, escalation, UAT, and payment inputs.
5. Resolve the 7.4/7.5 mock-API conflict explicitly.
6. Agree that `Built`, `Operational`, and `Accepted` remain separate statuses.
