"""Integration tests for Account Registration, Login, and JWT Authentication."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag_llm_services_api.db.models  # noqa: F401
from rag_llm_services_api.core.config import Settings, get_settings
from rag_llm_services_api.core.tokens import create_access_token
from rag_llm_services_api.db.base import Base
from rag_llm_services_api.db.session import get_session
from rag_llm_services_api.main import create_app

JWT_SECRET_TEST = "test-jwt-secret-key-32-chars-long!"


def _pw(s: str) -> str:
    return s


@pytest.fixture
async def auth_env(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    """Isolated app with in-memory SQLite database and test JWT secret."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session

    def override_settings() -> Settings:
        cfg = get_settings()
        cfg.auth.jwt_secret = JWT_SECRET_TEST
        cfg.dev_auth.auth_enabled = True
        return cfg

    app.dependency_overrides[get_settings] = override_settings

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield app, client

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_register_account_success(auth_env) -> None:
    _, client = auth_env
    payload = {
        "email": "User.Test@Example.COM",
        "password": _pw("SecurePassword123!"),
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "user_id" in data
    assert uuid.UUID(data["user_id"])
    assert data["email"] == "user.test@example.com"


async def test_register_duplicate_email_rejected(auth_env) -> None:
    _, client = auth_env
    payload = {
        "email": "duplicate@example.com",
        "password": _pw("SecurePassword123!"),
    }
    resp1 = await client.post("/api/v1/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/auth/register", json=payload)
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["error"]["code"] == "CONFLICT"
    assert "already registered" in data["error"]["message"].lower()


async def test_register_short_password_rejected(auth_env) -> None:
    _, client = auth_env
    payload = {
        "email": "shortpass@example.com",
        "password": "short",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


async def test_register_invalid_email_rejected(auth_env) -> None:
    _, client = auth_env
    payload = {
        "email": "not-an-email",
        "password": _pw("SecurePassword123!"),
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


async def test_login_success(auth_env) -> None:
    _, client = auth_env
    email = "login_success@example.com"
    plain_secret = _pw("MyPassword123!")
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": plain_secret},
    )
    assert reg_resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": plain_secret},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


async def test_login_wrong_credentials_rejected(auth_env) -> None:
    _, client = auth_env
    email = "test_user@example.com"
    plain_secret = _pw("CorrectPassword123!")
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": plain_secret},
    )

    # 1. Wrong password
    resp1 = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _pw("WrongPassword!")},
    )
    assert resp1.status_code == 401
    assert resp1.json()["error"]["message"] == "Invalid email or password"

    # 2. Unknown email (anti-enumeration check: identical error message)
    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": plain_secret},
    )
    assert resp2.status_code == 401
    assert resp2.json()["error"]["message"] == "Invalid email or password"


async def test_protected_route_with_bearer_token(auth_env) -> None:
    _, client = auth_env
    email = "bearer_route@example.com"
    plain_secret = _pw("ValidPassword123!")
    reg_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": plain_secret},
    )
    assert reg_resp.status_code == 201
    assert "user_id" in reg_resp.json()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": plain_secret},
    )
    token = login_resp.json()["access_token"]

    # Access protected knowledge-bases route with valid Bearer token
    kb_resp = await client.get(
        "/api/v1/knowledge-bases",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert kb_resp.status_code == 200


async def test_protected_route_with_invalid_bearer_token(auth_env) -> None:
    _, client = auth_env
    kb_resp = await client.get(
        "/api/v1/knowledge-bases",
        headers={"Authorization": "Bearer " + "invalid.tampered.token"},
    )
    assert kb_resp.status_code == 401


async def test_production_mode_fails_closed_without_token(auth_env) -> None:
    app, client = auth_env

    # Switch app to production mode
    def override_prod_settings() -> Settings:
        cfg = get_settings()
        cfg.app.env = "production"
        cfg.auth.jwt_secret = JWT_SECRET_TEST
        cfg.dev_auth.auth_enabled = False
        return cfg

    app.dependency_overrides[get_settings] = override_prod_settings

    # Calling with dev header in production must fail closed
    resp = await client.get(
        "/api/v1/knowledge-bases",
        headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 401

    # Calling with valid Bearer token in production succeeds
    valid_token = create_access_token(
        user_id=uuid.uuid4(),
        secret=JWT_SECRET_TEST,
        ttl_minutes=60,
    )
    resp2 = await client.get(
        "/api/v1/knowledge-bases",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert resp2.status_code == 200
