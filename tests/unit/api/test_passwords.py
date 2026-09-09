"""Unit tests for password hashing and verification."""

from __future__ import annotations

from rag_llm_services_api.core.passwords import hash_password, verify_password


def test_hash_password_produces_argon2id_string() -> None:
    hashed = hash_password("ValidPassword123!")
    assert isinstance(hashed, str)
    assert hashed.startswith("$argon2id$")


def test_verify_password_matches_correct_password() -> None:
    raw_value = "SuperSecretPassword123"
    hashed = hash_password(raw_value)
    assert verify_password(hashed, raw_value) is True


def test_verify_password_rejects_wrong_password() -> None:
    raw_value = "CorrectPassword123"
    hashed = hash_password(raw_value)
    assert verify_password(hashed, "WrongPassword123") is False


def test_verify_password_handles_corrupted_or_malformed_hash() -> None:
    assert verify_password("not-a-valid-hash", "password") is False
    assert verify_password("", "password") is False
    assert verify_password("$argon2id$v=19$m=65536,t=3,p=4$corrupted", "password") is False
