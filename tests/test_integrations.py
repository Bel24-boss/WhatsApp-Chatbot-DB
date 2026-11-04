import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import Settings
from app.integrations import (
    InsureTechClient,
    IntegrationResponseError,
    IntegrationUnavailableError,
)


def build_client(**overrides) -> InsureTechClient:
    values = {
        "INSURETECH_API_BASE_URL": "https://insuretech.example.test",
        "INSURETECH_API_TOKEN": "secret-token",
        "API_MAX_RETRIES": 2,
        "_env_file": None,
    }
    values.update(overrides)
    return InsureTechClient(Settings(**values))


def response(status_code: int, payload) -> MagicMock:
    result = MagicMock(status_code=status_code, is_error=status_code >= 400)
    result.json.return_value = payload
    return result


def async_client_with(*results) -> tuple[MagicMock, AsyncMock]:
    request = AsyncMock(side_effect=results)
    context = AsyncMock()
    context.__aenter__.return_value.request = request
    return MagicMock(return_value=context), request


@pytest.mark.parametrize(
    "payload",
    [
        [{"code": "life"}],
        {"products": [{"code": "life"}]},
        {"items": [{"code": "life"}]},
        {"data": [{"code": "life"}]},
    ],
)
def test_product_list_accepts_list_and_supported_envelopes(payload):
    factory, request = async_client_with(response(200, payload))
    with patch("app.integrations.httpx.AsyncClient", factory):
        products = asyncio.run(build_client().list_products())

    assert products == [{"code": "life"}]
    assert request.await_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_product_list_rejects_unknown_response_shape():
    factory, _ = async_client_with(response(200, {"result": "not-a-list"}))
    with patch("app.integrations.httpx.AsyncClient", factory):
        with pytest.raises(IntegrationResponseError, match="invalid product list format"):
            asyncio.run(build_client().list_products())


@pytest.mark.parametrize(
    "payload",
    [
        [{"code": "ecocash"}],
        {"payment_methods": [{"code": "ecocash"}]},
        {"methods": [{"code": "ecocash"}]},
        {"data": [{"code": "ecocash"}]},
    ],
)
def test_payment_methods_accept_list_and_supported_envelopes(payload):
    factory, request = async_client_with(response(200, payload))
    with patch("app.integrations.httpx.AsyncClient", factory):
        methods = asyncio.run(build_client().list_payment_methods())

    assert methods == [{"code": "ecocash"}]
    assert request.await_args.args[:2] == (
        "GET",
        "https://insuretech.example.test/payments/methods",
    )


def test_payment_status_encodes_reference():
    factory, request = async_client_with(response(200, {"status": "completed"}))
    with patch("app.integrations.httpx.AsyncClient", factory):
        result = asyncio.run(build_client().get_payment_status("pay/100"))

    assert result == {"status": "completed"}
    assert request.await_args.args[:2] == (
        "GET",
        "https://insuretech.example.test/payments/pay%2F100/status",
    )


def test_service_account_login_supplies_bearer_token():
    request = AsyncMock(return_value=response(200, [{"code": "life"}]))
    post = AsyncMock(
        return_value=response(
            200,
            {
                "access_token": "login-access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
            },
        )
    )
    context = AsyncMock()
    context.__aenter__.return_value.request = request
    context.__aenter__.return_value.post = post
    factory = MagicMock(return_value=context)
    client = build_client(
        INSURETECH_API_TOKEN="",
        INSURETECH_API_EMAIL="service@example.test",
        INSURETECH_API_PASSWORD="service-password",
    )

    with patch("app.integrations.httpx.AsyncClient", factory):
        products = asyncio.run(client.list_products())

    assert products == [{"code": "life"}]
    assert post.await_args.kwargs["json"] == {
        "email": "service@example.test",
        "password": "service-password",
    }
    assert request.await_args.kwargs["headers"]["Authorization"] == "Bearer login-access-token"


def test_unsafe_post_is_not_retried_without_idempotency_key():
    factory, request = async_client_with(httpx.ReadTimeout("timeout"), response(200, {"id": "q-1"}))
    with patch("app.integrations.httpx.AsyncClient", factory):
        with pytest.raises(IntegrationUnavailableError):
            asyncio.run(build_client().request_quote("life", {"age": 30}))

    assert request.await_count == 1


def test_unsafe_post_retries_with_idempotency_key():
    factory, request = async_client_with(httpx.ReadTimeout("timeout"), response(200, {"id": "q-1"}))
    with patch("app.integrations.httpx.AsyncClient", factory), patch(
        "app.integrations.asyncio.sleep", AsyncMock()
    ):
        result = asyncio.run(
            build_client().request_quote(
                "life",
                {"age": 30},
                idempotency_key="quote-123",
            )
        )

    assert result == {"id": "q-1"}
    assert request.await_count == 2
    assert request.await_args.kwargs["headers"]["Idempotency-Key"] == "quote-123"


def test_path_values_are_encoded_and_application_methods_use_expected_verbs():
    factory, request = async_client_with(
        response(200, {"id": "app-1"}),
        response(200, {"id": "app-1", "status": "draft"}),
        response(200, {"id": "app-1", "status": "submitted"}),
    )
    client = build_client()
    with patch("app.integrations.httpx.AsyncClient", factory):
        asyncio.run(
            client.create_application(
                "life cover",
                {"name": "Customer"},
                idempotency_key="create-1",
            )
        )
        asyncio.run(client.get_application("life cover", "app/1"))
        asyncio.run(
            client.submit_application(
                "life cover",
                "app/1",
                idempotency_key="submit-1",
            )
        )

    calls = request.await_args_list
    assert calls[0].args[:2] == (
        "POST",
        "https://insuretech.example.test/products/life%20cover/applications",
    )
    assert calls[1].args[:2] == (
        "GET",
        "https://insuretech.example.test/products/life%20cover/applications/app%2F1",
    )
    assert calls[2].args[:2] == (
        "POST",
        "https://insuretech.example.test/products/life%20cover/applications/app%2F1/submit",
    )


def test_policy_number_and_cover_operations_are_disabled_by_default():
    client = build_client()

    with pytest.raises(IntegrationUnavailableError, match="policy-number operations are not enabled"):
        asyncio.run(
            client.reserve_application_policy_number(
                "life",
                "app-1",
                idempotency_key="policy-1",
            )
        )
    with pytest.raises(IntegrationUnavailableError, match="cover activation is not enabled"):
        asyncio.run(
            client.activate_cover(
                "life",
                "app-1",
                idempotency_key="cover-1",
            )
        )


def test_enabled_cover_activation_sends_idempotency_key():
    factory, request = async_client_with(response(200, {"status": "active"}))
    client = build_client(INSURETECH_COVER_ACTIVATION_ENABLED=True)
    with patch("app.integrations.httpx.AsyncClient", factory):
        result = asyncio.run(
            client.activate_cover(
                "life",
                "app-1",
                {"verified": True},
                idempotency_key="cover-1",
            )
        )

    assert result == {"status": "active"}
    assert request.await_args.kwargs["headers"]["Idempotency-Key"] == "cover-1"
