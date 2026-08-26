"""Tests for Cloudflare Access identity and credential mapping."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.fastmcp.exceptions import ToolError

from wikijs_mcp.auth import (
    AuthorizationError,
    CloudflareAccessVerifier,
    WikiJSCredentialResolver,
)
from wikijs_mcp.config import WikiJSConfig
from wikijs_mcp.server import CloudflareAccessMiddleware, WikiJSMCPServer

ISSUER = "https://team.cloudflareaccess.com"
AUDIENCE = "access-audience"


@pytest.fixture
def rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


class FakeJWKClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.public_key)


def make_token(
    private_key,
    *,
    email: str = "user@example.com",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_delta: timedelta = timedelta(minutes=5),
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "exp": now + expires_delta,
            "iat": now,
            "email": email,
        },
        private_key,
        algorithm="RS256",
    )


def make_config() -> WikiJSConfig:
    return WikiJSConfig(
        url="https://wiki.example.com",
        api_key="legacy-key",
        cloudflare_access_issuer=ISSUER,
        cloudflare_access_audience=AUDIENCE,
        cloudflare_access_jwks_url=f"{ISSUER}/cdn-cgi/access/certs",
        auth_users={
            "admin@example.com": "admin",
            "friend1@example.com": "friends",
            "friend2@example.com": "friends",
        },
        auth_profiles={
            "admin": "WIKIJS_API_KEY_ADMIN",
            "friends": "WIKIJS_API_KEY_FRIENDS",
        },
    )


def make_resolver(config: WikiJSConfig, public_key) -> WikiJSCredentialResolver:
    resolver = WikiJSCredentialResolver(config)
    resolver._verifier = CloudflareAccessVerifier(
        issuer=config.cloudflare_access_issuer,
        audience=config.cloudflare_access_audience,
        jwks_url=config.cloudflare_access_jwks_url,
        jwk_client_factory=lambda url: FakeJWKClient(public_key),
    )
    return resolver


@pytest.mark.unit
class TestCloudflareAccessAuth:
    def test_valid_identity_uses_profile_a_key(self, rsa_keys):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        token = make_token(private_key, email="Admin@Example.com")

        with patch.dict("os.environ", {"WIKIJS_API_KEY_ADMIN": "admin-key"}):
            assert resolver.resolve_for_assertion(token) == "admin-key"

    def test_valid_identity_uses_profile_b_key(self, rsa_keys):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        token = make_token(private_key, email="friend1@example.com")

        with patch.dict("os.environ", {"WIKIJS_API_KEY_FRIENDS": "friends-key"}):
            assert resolver.resolve_for_assertion(token) == "friends-key"

    def test_multiple_users_can_share_profile_b(self, rsa_keys):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        friend1 = make_token(private_key, email="friend1@example.com")
        friend2 = make_token(private_key, email="friend2@example.com")

        with patch.dict("os.environ", {"WIKIJS_API_KEY_FRIENDS": "friends-key"}):
            assert resolver.resolve_for_assertion(friend1) == "friends-key"
            assert resolver.resolve_for_assertion(friend2) == "friends-key"

    def test_unknown_authenticated_user_is_rejected(self, rsa_keys):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        token = make_token(private_key, email="unknown@example.com")

        with pytest.raises(AuthorizationError, match="not configured"):
            resolver.resolve_for_assertion(token)

    def test_invalid_jwt_is_rejected(self, rsa_keys):
        _, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)

        with pytest.raises(AuthorizationError, match="Invalid Cloudflare"):
            resolver.resolve_for_assertion("not-a-jwt")

    def test_expired_jwt_is_rejected(self, rsa_keys):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        token = make_token(private_key, expires_delta=timedelta(minutes=-1))

        with pytest.raises(AuthorizationError, match="Invalid Cloudflare"):
            resolver.resolve_for_assertion(token)

    @pytest.mark.parametrize(
        "issuer,audience",
        [
            ("https://wrong.cloudflareaccess.com", AUDIENCE),
            (ISSUER, "wrong-audience"),
        ],
    )
    def test_wrong_audience_or_issuer_is_rejected(
        self, rsa_keys, issuer, audience
    ):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        token = make_token(private_key, issuer=issuer, audience=audience)

        with pytest.raises(AuthorizationError, match="Invalid Cloudflare"):
            resolver.resolve_for_assertion(token)

    def test_missing_configured_api_key_fails_closed(self, rsa_keys):
        private_key, public_key = rsa_keys
        resolver = make_resolver(make_config(), public_key)
        token = make_token(private_key, email="admin@example.com")

        with pytest.raises(AuthorizationError, match="environment variable"):
            resolver.resolve_for_assertion(token)

    @patch("wikijs_mcp.server.WikiJSConfig.load_config")
    async def test_request_scoped_resolution_does_not_mutate_global_config(
        self, mock_load_config, mock_wiki_config
    ):
        config = mock_wiki_config.model_copy(
            update={
                "api_key": "legacy-key",
                "cloudflare_access_issuer": ISSUER,
                "cloudflare_access_audience": AUDIENCE,
                "cloudflare_access_jwks_url": f"{ISSUER}/cdn-cgi/access/certs",
                "auth_users": {"a@example.com": "a", "b@example.com": "b"},
                "auth_profiles": {"a": "KEY_A", "b": "KEY_B"},
            }
        )
        mock_load_config.return_value = config
        server = WikiJSMCPServer()

        def fake_resolve(assertion):
            return {"assertion-a": "api-key-a", "assertion-b": "api-key-b"}[assertion]

        server.credential_resolver.resolve_for_assertion = fake_resolve

        async def resolve(assertion):
            request = SimpleNamespace(headers={"cf-access-jwt-assertion": assertion})
            return server._request_config_for_request(request).api_key

        result_a, result_b = await asyncio.gather(
            resolve("assertion-a"), resolve("assertion-b")
        )

        assert result_a == "api-key-a"
        assert result_b == "api-key-b"
        assert server.config.api_key == "legacy-key"

    @patch("wikijs_mcp.server.WikiJSConfig.load_config")
    def test_missing_assertion_raises_tool_error(
        self, mock_load_config, mock_wiki_config
    ):
        config = mock_wiki_config.model_copy(
            update={
                "cloudflare_access_issuer": ISSUER,
                "cloudflare_access_audience": AUDIENCE,
                "cloudflare_access_jwks_url": f"{ISSUER}/cdn-cgi/access/certs",
                "auth_users": {"a@example.com": "a"},
                "auth_profiles": {"a": "KEY_A"},
            }
        )
        mock_load_config.return_value = config
        server = WikiJSMCPServer()
        request = SimpleNamespace(headers={})

        with pytest.raises(ToolError, match="Missing Cloudflare Access assertion"):
            server._request_config_for_request(request)

    @patch("wikijs_mcp.server.WikiJSConfig.load_config")
    def test_request_config_uses_prevalidated_asgi_scope(
        self, mock_load_config, mock_wiki_config
    ):
        config = mock_wiki_config.model_copy(
            update={
                "cloudflare_access_issuer": ISSUER,
                "cloudflare_access_audience": AUDIENCE,
                "cloudflare_access_jwks_url": f"{ISSUER}/cdn-cgi/access/certs",
                "auth_users": {"a@example.com": "a"},
                "auth_profiles": {"a": "KEY_A"},
            }
        )
        mock_load_config.return_value = config
        server = WikiJSMCPServer()
        server.credential_resolver.resolve_for_assertion = lambda assertion: pytest.fail(
            "resolver should not run when middleware already validated the request"
        )
        request = SimpleNamespace(headers={}, scope={"wikijs_api_key": "scoped-key"})

        assert server._request_config_for_request(request).api_key == "scoped-key"

    async def test_cloudflare_middleware_rejects_missing_assertion(self):
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        config = make_config()
        middleware = CloudflareAccessMiddleware(app, WikiJSCredentialResolver(config))
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await middleware(
            {"type": "http", "headers": []},
            receive,
            send,
        )

        assert sent[0]["status"] == 401
        assert b"Cloudflare Access assertion" in sent[1]["body"]
