# Required Fidelity Inputs

The software foundation and workflow orchestration are implemented. These approved inputs are required to activate and sign off the connected chatbot.

## Conversation and content approval

- Business sign-off for the supplied M1 menu catalogue and M2 flow draft
- Product-owner approval for Vaka Yako, Beloved, Flexi Combo, pensions, endowment, and FLIMAS content
- Approved rates, billing periods, benefits, exclusions, waiting periods, and effective dates
- Approval of confirmation, timeout, privacy, permission, and consent wording
- Decision on the proposed 10-minute warning and 15-minute draft expiry; the application remains configurable
- Supported languages and approved terminology
- Validation of the funeral emergency number and official FLIMAS production links

## Escalation matrix

The supplied workbook defines AI chatbot, Agent, Client Services Supervisor, and Admin Manager levels. The following operating fields are still missing:

- Notification destination or agent-platform queue
- Priority and SLA
- Business hours, holidays, and timezone
- After-hours response and emergency handling
- Named contacts, backup routes, acceptance targets, update intervals, and resolution targets
- Final authority limits and approved closure rules for human escalation levels

This is configured through `ESCALATION_MATRIX_JSON`, `BUSINESS_HOURS_JSON`, `BUSINESS_TIMEZONE`, and the agent notification endpoint.

## Core-system APIs

- Non-production base URL
- OpenAPI/Swagger specification
- Authentication method and test credentials
- Customer-identification rules
- Customer-verification endpoint and the exact controls required before disclosing policy or claim data
- Policy lookup request and response
- Payment-history request and response
- Claim-status request and response
- Error codes, rate limits, timeout requirements, and retry rules
- Data classification and fields prohibited from WhatsApp

## WhatsApp onboarding

- Approved ownership and supported identifiers for all seven services, especially Wealth Management
- Onboarding verification, relationship-discovery and idempotent profile/link API contracts
- Identity matching, duplicate detection, recovery and representative-authority rules
- Cross-business discovery scope, permitted roles/actions, revocation and reconciliation behavior
- Approved onboarding notice and contact-preference wording
- UAT identities for existing, new, forgotten-reference and representative journeys

## Payment API

- Non-production URL and authentication specification
- Approved payment methods and identifiers
- Initiation, status, callback, refund, and reconciliation contracts
- Currency, minimum/maximum values, fees, and rounding rules
- Confirmation and receipt wording
- PCI and security requirements

## AI handoff

- Approved workflow identifiers
- Calling system identity and authentication method
- Allowed context fields
- Rules for starting, resuming, and replacing a WhatsApp session
- Error and retry behavior

## Data and infrastructure

- SQL Server instance and database connection for UAT/production
- Hosting target and network architecture
- Secret manager
- Data retention and deletion policy
- Encryption and restricted access for temporary onboarding identity data
- Encryption, backup, recovery, monitoring, and audit requirements
- POPIA/privacy assessment and approved customer consent text
- UAT environment, testers, test numbers, and acceptance criteria

Do not provide production passwords, tokens, private keys, customer records, or OTPs in chat. Place secrets directly into the approved secret manager or local `.env` file.
