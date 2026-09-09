"""Password hashing for account authentication.

argon2-cffi's :class:`PasswordHasher` (argon2id) is the OWASP-endorsed
default: salt generation, self-describing parameter encoding, and
constant-time verification live in one audited call, so parameter upgrades
stay a ``check_needs_rehash`` concern instead of a hand-rolled format.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with argon2id and return the encoded PHC string."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return True only when the password matches the stored hash.

    Malformed stored hashes verify False rather than raising, so a corrupted
    row behaves exactly like a wrong password at the login boundary.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


__all__ = [
    "hash_password",
    "verify_password",
]
