# Integration Contracts

## Authentication

The current clients send `Authorization: Bearer <token>` and JSON. If Fidelity uses OAuth client credentials, mutual TLS, API keys, signed requests, or another mechanism, provide the security specification so the adapter can be changed before connection.

## Policy details

Before protected data is requested, the chatbot calls the configured customer-verification endpoint:

```http
POST /customers/verify
```

```json
{
  "customer_wa_id": "E.164 digits",
  "reference": "policy or claim reference",
  "reference_type": "policy|claim"
}
```

The endpoint must return `{"verified": true}` only after Fidelity's approved identification checks pass. A false, missing, or unavailable result prevents disclosure and transaction processing.

## WhatsApp onboarding

This implementation does not include OTP or authentication-challenge handling. The configured backend must independently make the identity, reference, duplicate-customer, role and representative-authority decisions needed before private relationships can be returned.

Start or evaluate onboarding:

```http
POST /onboarding
```

```json
{
  "channel": "whatsapp",
  "customer_wa_id": "E.164 digits",
  "selected_service": "life|employee_benefits|funeral|medical_aid|financial_services|wealth_management|actuarial_services",
  "journey": "existing|new|forgotten_reference|representative",
  "identity": {"type": "national_id|passport", "country": "string|null", "value": "string"},
  "reference": "string|null",
  "preferred_contact": "E.164 digits",
  "notice_version": "string"
}
```

Successful responses require an opaque `attempt_id`, `identity_verified: true`, and `status: verified`. Existing and representative journeys also require `reference_matched: true`; representatives require `authority_verified: true`. New-customer responses use `existing_customer_found` to prevent duplicate profiles. Uncertain, conflicting, recovery, or ambiguous results must return an assisted-review status and no private records.

After verification, `GET /onboarding/{attempt_id}/relationships` returns only authorised relationships:

```json
{
  "relationships": [
    {
      "relationship_id": "opaque identifier",
      "business": "FLA",
      "service": "Life Assurance",
      "masked_reference": "****4582",
      "status": "Active",
      "role": "owner",
      "eligible": true
    }
  ]
}
```

Confirmed choices are submitted idempotently to `POST /onboarding/{attempt_id}/links` as `{"relationship_ids": ["opaque identifier"]}`. The response must provide a stable `profile_id` and one truthful result per requested ID, including business, masked reference, role, source status, permitted actions and `link_status`. An empty list completes a verified new profile without creating or approving a product.

Request:

```http
GET /policies/{policy_number}?customer_wa_id={wa_id}
```

Expected response fields:

```json
{
  "policy_number": "string",
  "product_name": "string",
  "status": "string",
  "premium_amount": "string",
  "premium_frequency": "string",
  "next_due_date": "YYYY-MM-DD"
}
```

## Payment history

Request:

```http
GET /policies/{policy_number}/payments?customer_wa_id={wa_id}
```

Expected response:

```json
{
  "payments": [
    {
      "date": "YYYY-MM-DD",
      "amount": "string",
      "status": "string",
      "reference": "string"
    }
  ]
}
```

## Claim status

Request:

```http
GET /claims/{reference}?customer_wa_id={wa_id}
```

Expected response:

```json
{
  "reference": "string",
  "status": "string",
  "last_updated": "ISO-8601 timestamp"
}
```

## Payment workflow

### Payment identity verification

The chatbot does not generate or validate verification codes. It calls the
approved Fidelity backend and redacts the submitted code from message history.

```http
POST /payments/verification/start
```

```json
{"customer_wa_id":"263...","registered_mobile":"263..."}
```

The response must contain an opaque `verification_id`. Confirmation uses:

```http
POST /payments/verification/confirm
```

```json
{"verification_id":"opaque","verification_code":"redacted by chatbot"}
```

Only `{"verified":true}` permits policy discovery. After verification,
`GET /payments/eligible-policies?verification_id=...` must return only policies
the verified customer may pay:

```json
{"policies":[{"policy_number":"string","product_name":"string","account_name":"string","premium_due":"45.00","currency":"USD|ZiG"}]}
```

### Payment preparation

Before a method is selected, the chatbot calls `POST /payments/prepare` with the
policy, amount due, source currency, requested payment currency and verification
reference. The response must provide a validated positive `amount`, matching
`currency` and an optional `preparation_reference`. Currency conversion is never
performed locally.

### Payment initiation

Request:

```http
POST /payments
```

```json
{
  "policy_number": "string",
  "amount": "decimal string",
  "currency": "USD|ZiG",
  "payment_method": "configured method identifier",
  "mobile_number": "E.164 digits or null",
  "preparation_reference": "string or null",
  "verification_id": "opaque"
}
```

Expected response:

```json
{
  "reference": "string",
  "status": "pending|successful|failed",
  "payment_url": "https URL for card payments only",
  "expires_at": "ISO-8601 timestamp for expiring links"
}

Bank details are loaded only from `BANK_TRANSFER_INSTRUCTIONS_JSON`. Proof of
payment attachments create a `pending_finance_verification` request; attachment
receipt never marks a transaction paid or credits a policy.
```

## Payment status

Request:

```http
GET /payments/{reference}
```

Expected response:

```json
{
  "reference": "string",
  "status": "pending|successful|failed"
}
```

## Agent notification

The configured webhook receives:

```json
{
  "escalation_id": "uuid",
  "conversation_id": "uuid",
  "customer_wa_id": "E.164 digits",
  "category": "string",
  "assigned_team": "string or null",
  "conversation_history": []
}
```

When permission to share prior context is declined, `conversation_history` is an empty list. The receiving service must authenticate the caller, encrypt transport with TLS, restrict access to authorized agents, and return `2xx` only after accepting the escalation.

Expected acknowledgment body:

```json
{
  "acknowledged": true,
  "handover_id": "agent-platform-reference",
  "status": "queue_acknowledged"
}
```

`acknowledged: false`, a non-`2xx` response, timeout, or network failure is treated as unconfirmed delivery. The chatbot does not tell the customer that the request is queued in those cases.

The agent platform reports lifecycle changes to the authenticated internal endpoint:

```http
POST /internal/escalations/{escalation_id}/status
X-Handoff-Key: <configured key>
Content-Type: application/json

{"status": "takeover_acknowledged"}
```

Allowed states are `queue_acknowledged`, `takeover_acknowledged`, `released`, `resolved`, and `rejected`. `takeover_acknowledged` pauses bot replies; terminal release states restore the main menu.

## Error behavior

- `404`: customer-facing not-found response
- `408`, `429`, `500`, `502`, `503`, `504`: retried according to `API_MAX_RETRIES`
- Other `4xx`: rejected without retry
- Timeout or network failure: safe unavailable response; no invented customer data

Provide the official OpenAPI specification or equivalent request/response examples to finalize field mapping.
