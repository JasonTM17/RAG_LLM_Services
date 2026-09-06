"""Settings tests: .env.example parity, fail-fast production guard, drivers.

Tests never read the developer's real ``.env``: every Settings is constructed
with ``_env_file=None`` and environment input arrives only through
``monkeypatch.setenv`` (the shared autouse fixture scrubs app variables).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_llm_services_api.core.config import KNOWN_ENV_VARS, PLACEHOLDER_MARKERS, Settings
from rag_llm_services_shared.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _env_example_keys() -> set[str]:
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_parity_both_directions() -> None:
    file_keys = _env_example_keys()
    missing_from_known = sorted(file_keys - set(KNOWN_ENV_VARS))
    extra_in_known = sorted(set(KNOWN_ENV_VARS) - file_keys)
    assert not missing_from_known, f"keys missing from KNOWN_ENV_VARS: {missing_from_known}"
    assert not extra_in_known, f"KNOWN_ENV_VARS keys absent from .env.example: {extra_in_known}"


def test_local_defaults_construct(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)
    assert settings.app.env == "local"
    assert settings.app.api_port == 8000
    assert settings.deepseek.base_url == "https://api.deepseek.com"
    assert settings.deepseek.model == "deepseek-v4-flash"
    assert settings.deepseek.run_live_tests is False


def test_production_with_placeholder_secret_raises_and_hides_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "DEEPSEEK_API_KEY" in message
    for marker in PLACEHOLDER_MARKERS:
        assert marker not in message


def test_production_with_dev_auth_enabled_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    real = "real-value-not-a-placeholder"
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{real}@db:5432/d")
    monkeypatch.setenv("DEEPSEEK_API_KEY", real)
    monkeypatch.setenv("POSTGRES_PASSWORD", real)
    monkeypatch.setenv("MINIO_SECRET_KEY", real)
    monkeypatch.setenv("N8N_API_KEY", real)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", real)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", real)
    monkeypatch.setenv("RAG_DEV_AUTH_ENABLED", "true")
    with pytest.raises(ConfigurationError) as excinfo:
        Settings(_env_file=None)
    assert "dev auth" in str(excinfo.value)


def test_production_with_complete_config_constructs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    real = "real-value-not-a-placeholder"
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://u:{real}@db:5432/d")
    monkeypatch.setenv("DEEPSEEK_API_KEY", real)
    monkeypatch.setenv("POSTGRES_PASSWORD", real)
    monkeypatch.setenv("MINIO_SECRET_KEY", real)
    monkeypatch.setenv("N8N_API_KEY", real)
    monkeypatch.setenv("N8N_ENCRYPTION_KEY", real)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", real)
    settings = Settings(_env_file=None)
    assert settings.app.env == "production"
    assert settings.dev_auth.auth_enabled is False


def test_database_url_rewrites_to_psycopg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/d")
    settings = Settings(_env_file=None)
    assert settings.database.url.startswith("postgresql+psycopg://")


def test_database_url_rejects_other_drivers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@db:3306/d")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_deepseek_base_url_rejects_v1_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    # Our validator's message text must be present (pydantic appends the
    # developer-supplied input value to its own report, which is not a secret).
    assert "must not include the /v1 path suffix" in str(excinfo.value)


def test_deepseek_base_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")
    settings = Settings(_env_file=None)
    assert settings.deepseek.base_url == "https://api.deepseek.com"


def test_cors_origins_parses_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    settings = Settings(_env_file=None)
    assert settings.app.cors_origins == ["http://a.com", "http://b.com"]
