import hmac
import hashlib
import logging

logger = logging.getLogger("cynex.security")


def verify_meta_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
    allow_unsigned: bool = True,
) -> bool:
    """
    Verify the cryptographic signature of an incoming Meta webhook payload.

    Meta sends an HMAC-SHA256 signature in the `X-Hub-Signature-256` header:
    `sha256=<hex_digest>`

    Args:
        raw_body: The raw byte content of the incoming HTTP request.
        signature_header: The value of the `X-Hub-Signature-256` header.
        app_secret: The Meta App Secret configured for the application.

    Returns:
        bool: True if signature is valid or if secret verification is disabled in dev,
              False if signature is invalid or missing when required.
    """
    if not app_secret and allow_unsigned:
        logger.warning(
            "META_APP_SECRET is not configured. Webhook signature verification is bypassed. "
            "Please configure META_APP_SECRET for production security."
        )
        return True

    if not app_secret:
        logger.error("META_APP_SECRET is required when unsigned webhooks are disabled.")
        return False

    if not signature_header:
        logger.error("Missing X-Hub-Signature-256 header on incoming webhook request.")
        return False

    if not signature_header.startswith("sha256="):
        logger.error("Malformed X-Hub-Signature-256 header (missing 'sha256=' prefix).")
        return False

    expected_signature = signature_header[len("sha256="):]

    # Compute HMAC SHA-256 digest
    computed_mac = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    )
    computed_signature = computed_mac.hexdigest()

    is_valid = hmac.compare_digest(computed_signature, expected_signature)
    if not is_valid:
        logger.error("Invalid webhook signature. Request does not match META_APP_SECRET HMAC.")

    return is_valid
