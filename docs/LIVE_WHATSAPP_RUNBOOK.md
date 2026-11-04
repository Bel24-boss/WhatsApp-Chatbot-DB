# Live WhatsApp Activation Runbook

## Current confirmed state

- The FastAPI service starts successfully on `http://127.0.0.1:8000`.
- Local webhook verification returns Meta's challenge with HTTP 200.
- The configured public callback returns Meta's challenge with HTTP 200.
- A correctly signed Meta-shaped POST reaches the public callback, passes signature validation, and is acknowledged with HTTP 200.
- Signed webhook POST requests are accepted and processed.
- The SQL Server repository is available.
- The conversation workflow and browser simulator work locally.
- The current Meta token authenticates successfully.
- `WHATSAPP_PHONE_NUMBER_ID` now resolves to the registered `+263 78 138 0349` Fidelity number.
- The registered number is verified, uses Cloud API, is in LIVE account mode, and has GREEN quality.
- The Fidelity WhatsApp Business Account is subscribed to the CyneX Meta app and the `messages` webhook field.
- One Cloudflare quick tunnel is running and matches the callback registered in Meta.
- A real interactive reply from a separate WhatsApp account was received, routed from `main_menu` to `life_menu`, and answered successfully through Meta.

The previous primary root cause was an incorrect Phone Number ID: the application was sending through Meta's test number ending `4984` while customers were messaging the registered Fidelity number ending `0349`. Duplicate local API and tunnel processes also made routing ambiguous. The Phone Number ID and duplicate processes have been corrected.

The repaired live path has been verified as follows:

1. A Fidelity main-menu message was accepted by Meta with HTTP 200.
2. Meta reported the message as sent, delivered, and read.
3. The recipient selected a WhatsApp interactive menu option.
4. The signed inbound event reached the configured public webhook.
5. The workflow routed the conversation from `main_menu` to `life_menu`.
6. Meta accepted the automated interactive reply with HTTP 200.

## 1. Rotate the Meta token

The previously used token must be revoked because it was exposed outside the local secret store and Meta now reports that its session is invalid.

1. In Meta Business Settings, open **Users > System Users**.
2. Create or select an Admin system user.
3. Assign the Fidelity WhatsApp Business Account and the Meta app with the required control.
4. Generate a token for the app with `whatsapp_business_messaging` and `whatsapp_business_management`.
5. Replace `WHATSAPP_ACCESS_TOKEN` in the local `.env` file. Never paste the token into chat, source code, screenshots, tickets, or documentation.
6. Restart the FastAPI process so the cached settings are reloaded.

Run this safe check after restarting:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/diagnostics/whatsapp
```

Required result:

```text
credentials_present      True
reachable                True
authenticated            True
phone_number_id_matches  True
```

The returned `display_phone_number` is masked. Confirm its final four digits match the registered business number.

## 2. Confirm the Meta phone-number configuration

In **WhatsApp Manager > Phone numbers**, confirm:

- The number is `+263 78 138 0349`.
- Its status is connected/registered.
- The Phone Number ID exactly matches `WHATSAPP_PHONE_NUMBER_ID` in `.env`.
- The quality status is acceptable and no account restriction is displayed.
- Two-step verification or registration requirements shown by Meta are complete.

Do not use the visible telephone number as `WHATSAPP_PHONE_NUMBER_ID`; Meta provides a separate numeric ID.

## 3. Restore a stable public webhook

Meta cannot call `127.0.0.1`. Keep the API on port 8000 and expose it through a persistent public HTTPS endpoint.

For temporary development only:

```powershell
.\start_tunnel.ps1
```

For reliable use, create a named Cloudflare Tunnel with a stable hostname or deploy the API to an approved server. The callback must be:

```text
https://YOUR-STABLE-HOST/webhook
```

Verify the public route before changing Meta:

```powershell
$url = "https://YOUR-STABLE-HOST/webhook?hub.mode=subscribe&hub.verify_token=YOUR_LOCAL_VERIFY_TOKEN&hub.challenge=123456"
Invoke-WebRequest -Uri $url -Method Get
```

The response must be HTTP 200 with body `123456`.

## 4. Confirm Meta webhook subscriptions

In the Meta app's WhatsApp configuration:

1. Set the callback URL to the stable URL ending in `/webhook`.
2. Enter the same value stored locally as `WHATSAPP_VERIFY_TOKEN` and verify/save it.
3. Subscribe the Webhooks product to the `messages` field.
4. Confirm the app is subscribed to the correct WhatsApp Business Account.
5. Use Live mode for general senders. In Development mode, test only with app roles and explicitly allowed recipients.

## 5. End-to-end test

1. Keep FastAPI and the public tunnel/hosting service running.
2. From a different personal WhatsApp account, send `Hello` to `+263 78 138 0349`.
3. Watch the server terminal for the webhook request and outbound Meta request.
4. Confirm the Fidelity main menu appears in WhatsApp.
5. Query SQL Server and confirm live rows contain Meta message IDs rather than `message_type='simulator'` only.

If the inbound webhook appears but no reply is sent, call the diagnostic endpoint and inspect the outbound HTTP status in the server log. If no inbound webhook appears, the problem is the public callback, WABA/app subscription, app mode, or phone-number registration rather than the conversation code.
