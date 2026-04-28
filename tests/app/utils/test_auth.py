import pytest
from unittest.mock import patch
from jose import JWTError
from passlib.context import CryptContext
from hashlib import sha256
from datetime import datetime, timedelta, timezone

from app.utils.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
    pwd_context
)


@pytest.fixture
def mock_settings():
    with patch('app.utils.auth.settings') as mock:
        mock.access_token_expire_minutes = 30
        mock.secret_key = 'secret_key'
        mock.algorithm = 'HS256'
        yield mock


# ── Password Tests ─────────────────────────────────────────

def test_hash_password():
    plain = 'password123'
    hashed = hash_password(plain)
    assert hashed is not None


def test_verify_password():
    plain = 'password123'
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_invalid():
    plain = 'password123'
    hashed = hash_password(plain)
    assert verify_password('wrong_password', hashed) is False


def test_verify_password_empty():
    plain = ''
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_zero():
    plain = '0'
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_verify_password_negative():
    plain = '-1'
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_hash_password_zero():
    plain = '0'
    hashed = hash_password(plain)
    assert hashed is not None


def test_hash_password_negative():
    plain = '-1'
    hashed = hash_password(plain)
    assert hashed is not None


# ── Token Tests ───────────────────────────────────────────────

def test_create_access_token(mock_settings):
    token = create_access_token('user123', 'admin')
    assert token is not None


def test_decode_token(mock_settings):
    subject = 'user123'
    role = 'admin'

    token = create_access_token(subject, role)
    decoded = decode_token(token)

    assert decoded is not None
    assert decoded['sub'] == subject
    assert decoded['role'] == role


def test_decode_token_invalid(mock_settings):
    decoded = decode_token('invalid_token')
    assert decoded is None


def test_decode_token_jwt_error(mock_settings):
    with patch('app.utils.auth.jwt.decode') as mock_decode:
        mock_decode.side_effect = JWTError

        token = create_access_token('user123', 'admin')
        decoded = decode_token(token)

        assert decoded is None


def test_create_access_token_empty_subject(mock_settings):
    token = create_access_token('', 'admin')
    assert token is not None


def test_create_access_token_empty_role(mock_settings):
    token = create_access_token('user123', '')
    assert token is not None


def test_create_access_token_zero_subject(mock_settings):
    token = create_access_token('0', 'admin')
    assert token is not None


def test_create_access_token_zero_role(mock_settings):
    token = create_access_token('user123', '0')
    assert token is not None


def test_create_access_token_negative_subject(mock_settings):
    token = create_access_token('-1', 'admin')
    assert token is not None


def test_create_access_token_negative_role(mock_settings):
    token = create_access_token('user123', '-1')
    assert token is not None


# ── Edge Cases ─────────────────────────────────────────────--

def test_hash_password_long_string():
    plain = 'a' * 1000
    hashed = hash_password(plain)
    assert hashed is not None


def test_verify_password_long_string():
    plain = 'a' * 1000
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True


def test_create_access_token_long_subject(mock_settings):
    subject = 'a' * 1000
    token = create_access_token(subject, 'admin')
    assert token is not None


def test_create_access_token_long_role(mock_settings):
    role = 'a' * 1000
    token = create_access_token('user123', role)
    assert token is not None


def test_decode_token_expired(mock_settings):
    with patch('app.utils.auth.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime.now(timezone.utc) + timedelta(minutes=31)

        token = create_access_token('user123', 'admin')
        decoded = decode_token(token)

        assert decoded is None


def test_decode_token_invalid_algorithm(mock_settings):
    with patch('app.utils.auth.jwt.encode') as mock_encode:
        mock_encode.return_value = 'invalid_token'

        token = create_access_token('user123', 'admin')
        decoded = decode_token(token)

        assert decoded is None