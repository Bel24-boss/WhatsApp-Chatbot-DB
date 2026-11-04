import asyncio
import logging
from typing import Any, Optional
from urllib.parse import quote, urlparse

import httpcore
import httpx

from app.config import Settings

logger = logging.getLogger("fidelity.integrations")


class StaticDnsBackend(httpcore.AsyncNetworkBackend):
    """Resolve one configured host to approved fallback IPs while preserving TLS SNI."""

    def __init__(self, hostname: str, addresses: tuple[str, ...]):
        self.hostname = hostname.lower()
        self.addresses = addresses
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        targets = self.addresses if host.lower() == self.hostname else (host,)
        last_error: Optional[Exception] = None
        for target in targets:
            try:
                return await self.backend.connect_tcp(
                    target,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise OSError(f"No address is configured for {host}")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self.backend.connect_unix_socket(
            path,
            timeout=timeout,
            socket_options=socket_options,
        )


class StaticDnsAsyncTransport(httpx.AsyncHTTPTransport):
    def __init__(self, hostname: str, addresses: tuple[str, ...]):
        super().__init__()
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            network_backend=StaticDnsBackend(hostname, addresses),
        )


class IntegrationUnavailableError(RuntimeError):
    pass


class IntegrationResponseError(RuntimeError):
    def __init__(self, service: str, status_code: int, message: str):
        super().__init__(f"{service} returned HTTP {status_code}: {message}")
        self.service = service
        self.status_code = status_code


class BaseIntegrationClient:
    service_name = "integration"

    def __init__(self, base_url: str, token: str, timeout_seconds: float, max_retries: int):
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self, idempotency_key: Optional[str] = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        allow_list: bool = False,
    ) -> dict[str, Any] | list[Any]:
        if not self.configured:
            raise IntegrationUnavailableError(f"{self.service_name} is not configured")

        request_method = method.upper()
        url = self.base_url if not path else f"{self.base_url}/{path.lstrip('/')}"
        last_error: Optional[Exception] = None
        retry_allowed = request_method in {"GET", "HEAD", "OPTIONS"} or bool(idempotency_key)
        attempt_count = self.max_retries + 1 if retry_allowed else 1
        for attempt in range(attempt_count):
            try:
                async with self._http_client() as client:
                    response = await client.request(
                        request_method,
                        url,
                        params=params,
                        json=json_body,
                        headers=self._headers(idempotency_key),
                    )
                if (
                    response.status_code in {408, 429, 500, 502, 503, 504}
                    and attempt < attempt_count - 1
                ):
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if response.is_error:
                    try:
                        error_body = response.json()
                        message = str(error_body.get("message") or error_body.get("error") or "request failed")
                    except Exception:
                        message = "request failed"
                    raise IntegrationResponseError(self.service_name, response.status_code, message)
                data = response.json()
                if not isinstance(data, dict) and not (allow_list and isinstance(data, list)):
                    raise IntegrationResponseError(self.service_name, response.status_code, "invalid response format")
                return data
            except IntegrationResponseError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < attempt_count - 1:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                break

        logger.error("%s request failed after retries: %s", self.service_name, type(last_error).__name__)
        raise IntegrationUnavailableError(f"{self.service_name} is temporarily unavailable") from last_error


class InsureTechClient(BaseIntegrationClient):
    """Fail-closed adapter for the approved InsureTech product lifecycle."""

    service_name = "InsureTech API"

    def __init__(self, settings: Settings):
        super().__init__(
            settings.INSURETECH_API_BASE_URL,
            settings.INSURETECH_API_TOKEN,
            settings.API_TIMEOUT_SECONDS,
            settings.API_MAX_RETRIES,
        )
        self.email = settings.INSURETECH_API_EMAIL.strip()
        self.password = settings.INSURETECH_API_PASSWORD
        self.login_path = settings.INSURETECH_LOGIN_PATH
        self.resolved_ips = tuple(
            address.strip()
            for address in settings.INSURETECH_API_RESOLVED_IPS.split(",")
            if address.strip()
        )
        self.api_hostname = (urlparse(self.base_url).hostname or "").lower()
        self._auth_lock = asyncio.Lock()
        self.products_path = settings.INSURETECH_PRODUCTS_PATH
        self.product_path = settings.INSURETECH_PRODUCT_PATH
        self.quote_path = settings.INSURETECH_QUOTE_PATH
        self.applications_path = settings.INSURETECH_APPLICATIONS_PATH
        self.application_path = settings.INSURETECH_APPLICATION_PATH
        self.application_submit_path = settings.INSURETECH_APPLICATION_SUBMIT_PATH
        self.payment_methods_path = settings.INSURETECH_PAYMENT_METHODS_PATH
        self.payment_status_path = settings.INSURETECH_PAYMENT_STATUS_PATH
        self.product_policy_number_path = settings.INSURETECH_PRODUCT_POLICY_NUMBER_PATH
        self.application_policy_number_path = settings.INSURETECH_APPLICATION_POLICY_NUMBER_PATH
        self.cover_activation_path = settings.INSURETECH_COVER_ACTIVATION_PATH
        self.policy_number_enabled = settings.INSURETECH_POLICY_NUMBER_ENABLED
        self.cover_activation_enabled = settings.INSURETECH_COVER_ACTIVATION_ENABLED

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self.token or (self.email and self.password)))

    def _http_client(self) -> httpx.AsyncClient:
        transport = (
            StaticDnsAsyncTransport(self.api_hostname, self.resolved_ips)
            if self.api_hostname and self.resolved_ips
            else None
        )
        return httpx.AsyncClient(timeout=self.timeout_seconds, transport=transport)

    async def _authenticate(self) -> None:
        if self.token:
            return
        if not self.email or not self.password:
            raise IntegrationUnavailableError("InsureTech API credentials are not configured")
        async with self._auth_lock:
            if self.token:
                return
            url = f"{self.base_url}/{self.login_path.lstrip('/')}"
            try:
                async with self._http_client() as client:
                    response = await client.post(
                        url,
                        json={"email": self.email, "password": self.password},
                        headers={"Accept": "application/json", "Content-Type": "application/json"},
                    )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise IntegrationUnavailableError("InsureTech authentication is temporarily unavailable") from exc
            if response.is_error:
                raise IntegrationResponseError(self.service_name, response.status_code, "authentication failed")
            data = response.json()
            access_token = data.get("access_token") if isinstance(data, dict) else None
            if not isinstance(access_token, str) or not access_token.strip():
                raise IntegrationResponseError(
                    self.service_name,
                    response.status_code,
                    "invalid authentication response",
                )
            self.token = access_token.strip()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        allow_list: bool = False,
    ) -> dict[str, Any] | list[Any]:
        await self._authenticate()
        try:
            return await super().request(
                method,
                path,
                params=params,
                json_body=json_body,
                idempotency_key=idempotency_key,
                allow_list=allow_list,
            )
        except IntegrationResponseError as exc:
            if exc.status_code != 401 or not self.email or not self.password:
                raise
            self.token = ""
            await self._authenticate()
            return await super().request(
                method,
                path,
                params=params,
                json_body=json_body,
                idempotency_key=idempotency_key,
                allow_list=allow_list,
            )

    @staticmethod
    def _path_value(value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{label} is required")
        return quote(normalized, safe="")

    def _product_path(self, template: str, product_code: str, **values: str) -> str:
        encoded = {
            "product_code": self._path_value(product_code, "product code"),
            **{key: self._path_value(value, key.replace("_", " ")) for key, value in values.items()},
        }
        return template.format(**encoded)

    async def list_products(self) -> list[dict[str, Any]]:
        data = await self.request("GET", self.products_path, allow_list=True)
        if isinstance(data, list):
            products = data
        else:
            products = next(
                (data[key] for key in ("products", "items", "data") if isinstance(data.get(key), list)),
                None,
            )
        if products is None or any(not isinstance(item, dict) for item in products):
            raise IntegrationResponseError(self.service_name, 200, "invalid product list format")
        return products

    async def get_product(self, product_code: str) -> dict[str, Any]:
        path = self._product_path(self.product_path, product_code)
        data = await self.request("GET", path)
        return data

    async def request_quote(
        self,
        product_code: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        path = self._product_path(self.quote_path, product_code)
        data = await self.request(
            "POST",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data

    async def list_applications(
        self,
        product_code: str,
        *,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        path = self._product_path(self.applications_path, product_code)
        data = await self.request("GET", path, params=params, allow_list=True)
        if isinstance(data, list):
            applications = data
        else:
            applications = next(
                (
                    data[key]
                    for key in ("applications", "items", "data")
                    if isinstance(data.get(key), list)
                ),
                None,
            )
        if applications is None or any(not isinstance(item, dict) for item in applications):
            raise IntegrationResponseError(self.service_name, 200, "invalid application list format")
        return applications

    async def create_application(
        self,
        product_code: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        path = self._product_path(self.applications_path, product_code)
        data = await self.request(
            "POST",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data

    async def get_application(self, product_code: str, application_id: str) -> dict[str, Any]:
        path = self._product_path(
            self.application_path,
            product_code,
            application_id=application_id,
        )
        data = await self.request("GET", path)
        return data

    async def update_application(
        self,
        product_code: str,
        application_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        path = self._product_path(
            self.application_path,
            product_code,
            application_id=application_id,
        )
        data = await self.request(
            "PUT",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data

    async def submit_application(
        self,
        product_code: str,
        application_id: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        path = self._product_path(
            self.application_submit_path,
            product_code,
            application_id=application_id,
        )
        data = await self.request(
            "POST",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data

    async def list_payment_methods(self) -> list[dict[str, Any]]:
        data = await self.request("GET", self.payment_methods_path, allow_list=True)
        if isinstance(data, list):
            methods = data
        else:
            methods = next(
                (
                    data[key]
                    for key in ("payment_methods", "methods", "items", "data")
                    if isinstance(data.get(key), list)
                ),
                None,
            )
        if methods is None or any(not isinstance(item, dict) for item in methods):
            raise IntegrationResponseError(self.service_name, 200, "invalid payment-method list format")
        return methods

    async def get_payment_status(self, payment_id: str) -> dict[str, Any]:
        path = self.payment_status_path.format(
            payment_id=self._path_value(payment_id, "payment ID")
        )
        data = await self.request("GET", path)
        return data

    def _require_policy_number_gate(self) -> None:
        if not self.policy_number_enabled:
            raise IntegrationUnavailableError("InsureTech policy-number operations are not enabled")

    async def derive_product_policy_number(
        self,
        product_code: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_policy_number_gate()
        path = self._product_path(self.product_policy_number_path, product_code)
        data = await self.request(
            "POST",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data

    async def reserve_application_policy_number(
        self,
        product_code: str,
        application_id: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_policy_number_gate()
        path = self._product_path(
            self.application_policy_number_path,
            product_code,
            application_id=application_id,
        )
        data = await self.request(
            "POST",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data

    async def activate_cover(
        self,
        product_code: str,
        application_id: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not self.cover_activation_enabled:
            raise IntegrationUnavailableError("InsureTech cover activation is not enabled")
        path = self._product_path(
            self.cover_activation_path,
            product_code,
            application_id=application_id,
        )
        data = await self.request(
            "POST",
            path,
            json_body=payload,
            idempotency_key=idempotency_key,
        )
        return data


class FidelityCoreClient(BaseIntegrationClient):
    service_name = "Fidelity core API"

    def __init__(self, settings: Settings):
        super().__init__(
            settings.CUSTOMER_POLICY_API_BASE_URL,
            settings.CUSTOMER_POLICY_API_TOKEN,
            settings.API_TIMEOUT_SECONDS,
            settings.API_MAX_RETRIES,
        )
        self.policy_details_path = settings.POLICY_DETAILS_PATH
        self.payment_history_path = settings.PAYMENT_HISTORY_PATH
        self.claim_status_path = settings.CLAIM_STATUS_PATH
        self.customer_verification_path = settings.CUSTOMER_VERIFICATION_PATH
        self.onboarding_start_path = settings.ONBOARDING_START_PATH
        self.onboarding_relationships_path = settings.ONBOARDING_RELATIONSHIPS_PATH
        self.onboarding_link_path = settings.ONBOARDING_LINK_PATH
        self.payment_verification_start_path = settings.PAYMENT_VERIFICATION_START_PATH
        self.payment_verification_confirm_path = settings.PAYMENT_VERIFICATION_CONFIRM_PATH
        self.payment_eligible_policies_path = settings.PAYMENT_ELIGIBLE_POLICIES_PATH

    async def verify_customer(
        self,
        customer_wa_id: str,
        reference: str,
        reference_type: str,
    ) -> bool:
        if not self.customer_verification_path:
            raise IntegrationUnavailableError("customer verification endpoint is not configured")
        data = await self.request(
            "POST",
            self.customer_verification_path,
            json_body={
                "customer_wa_id": customer_wa_id,
                "reference": reference,
                "reference_type": reference_type,
            },
        )
        return data.get("verified") is True

    async def get_policy_details(self, policy_number: str, customer_wa_id: str) -> dict[str, Any]:
        path = self.policy_details_path.format(policy_number=policy_number)
        return await self.request("GET", path, params={"customer_wa_id": customer_wa_id})

    async def get_payment_history(self, policy_number: str, customer_wa_id: str) -> dict[str, Any]:
        path = self.payment_history_path.format(policy_number=policy_number)
        return await self.request("GET", path, params={"customer_wa_id": customer_wa_id})

    async def get_claim_status(self, reference: str, customer_wa_id: str) -> dict[str, Any]:
        path = self.claim_status_path.format(reference=reference)
        return await self.request("GET", path, params={"customer_wa_id": customer_wa_id})

    async def start_onboarding(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.onboarding_start_path:
            raise IntegrationUnavailableError("onboarding verification service is not configured")
        return await self.request("POST", self.onboarding_start_path, json_body=payload)

    async def discover_relationships(self, attempt_id: str) -> dict[str, Any]:
        if not self.onboarding_relationships_path:
            raise IntegrationUnavailableError("relationship discovery service is not configured")
        return await self.request(
            "GET",
            self.onboarding_relationships_path.format(attempt_id=attempt_id),
        )

    async def link_relationships(
        self,
        attempt_id: str,
        relationship_ids: list[str],
    ) -> dict[str, Any]:
        if not self.onboarding_link_path:
            raise IntegrationUnavailableError("relationship linking service is not configured")
        return await self.request(
            "POST",
            self.onboarding_link_path.format(attempt_id=attempt_id),
            json_body={"relationship_ids": relationship_ids},
        )

    async def start_payment_verification(self, customer_wa_id: str, registered_mobile: str) -> dict[str, Any]:
        if not self.payment_verification_start_path:
            raise IntegrationUnavailableError("payment identity verification is not configured")
        return await self.request(
            "POST",
            self.payment_verification_start_path,
            json_body={"customer_wa_id": customer_wa_id, "registered_mobile": registered_mobile},
        )

    async def confirm_payment_verification(self, verification_id: str, code: str) -> dict[str, Any]:
        if not self.payment_verification_confirm_path:
            raise IntegrationUnavailableError("payment identity verification is not configured")
        return await self.request(
            "POST",
            self.payment_verification_confirm_path,
            json_body={"verification_id": verification_id, "verification_code": code},
        )

    async def get_payment_eligible_policies(self, verification_id: str) -> dict[str, Any]:
        if not self.payment_eligible_policies_path:
            raise IntegrationUnavailableError("payment policy discovery is not configured")
        return await self.request(
            "GET",
            self.payment_eligible_policies_path,
            params={"verification_id": verification_id},
        )

class FidelityPaymentClient(BaseIntegrationClient):
    service_name = "Fidelity payment API"

    def __init__(self, settings: Settings):
        super().__init__(
            settings.PAYMENT_API_BASE_URL,
            settings.PAYMENT_API_TOKEN,
            settings.API_TIMEOUT_SECONDS,
            settings.API_MAX_RETRIES,
        )
        self.initiation_path = settings.PAYMENT_INITIATION_PATH
        self.status_path = settings.PAYMENT_STATUS_PATH
        self.preparation_path = settings.PAYMENT_PREPARATION_PATH

    async def prepare_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", self.preparation_path, json_body=payload)

    async def initiate_payment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", self.initiation_path, json_body=payload)

    async def get_payment_status(self, reference: str) -> dict[str, Any]:
        return await self.request("GET", self.status_path.format(reference=reference))


class AgentNotificationClient(BaseIntegrationClient):
    service_name = "agent notification service"

    def __init__(self, settings: Settings):
        super().__init__(
            settings.AGENT_NOTIFICATION_WEBHOOK_URL,
            settings.AGENT_NOTIFICATION_TOKEN,
            settings.API_TIMEOUT_SECONDS,
            settings.API_MAX_RETRIES,
        )

    async def notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise IntegrationUnavailableError("agent notification service is not configured")
        return await self.request("POST", "", json_body=payload)


class FidelityQuoteClient(BaseIntegrationClient):
    """Adapter boundary for an authorised rating/quotation service."""

    service_name = "Fidelity quotation API"

    def __init__(self, settings: Settings):
        super().__init__(
            settings.QUOTE_API_BASE_URL,
            settings.QUOTE_API_TOKEN,
            settings.API_TIMEOUT_SECONDS,
            settings.API_MAX_RETRIES,
        )
        self.request_path = settings.QUOTE_REQUEST_PATH

    async def create_quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", self.request_path, json_body=payload)


class FidelityCRMClient(BaseIntegrationClient):
    """Adapter boundary for authorised lead delivery and status ownership."""

    service_name = "Fidelity CRM API"

    def __init__(self, settings: Settings):
        super().__init__(
            settings.CRM_API_BASE_URL,
            settings.CRM_API_TOKEN,
            settings.API_TIMEOUT_SECONDS,
            settings.API_MAX_RETRIES,
        )
        self.lead_path = settings.CRM_LEAD_PATH

    async def create_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", self.lead_path, json_body=payload)
