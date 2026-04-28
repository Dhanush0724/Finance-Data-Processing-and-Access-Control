import pytest
from unittest.mock import patch
from jose import JWTError
from passlib.context import CryptContext
from hashlib import sha256
from app.utils.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password
)


@pytest.fixture
def mock_settings():
    with patch('app.utils.config.settings') as mock:
        mock.access_token_expire_minutes = 30
        mock.secret_key = 'secret_key'
        mock.algorithm = 'HS256'
        yield mock


# ── Password Tests ─────────────────────────────────────────

def test_hash_password():
    plain_password = 'password123'
    hashed_password = hash_password(plain_password)
    assert hashed_password is not None


def test_verify_password():
    plain_password = 'password123'
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True


def test_verify_password_invalid():
    plain_password = 'password123'
    hashed_password = hash_password('wrong_password')
    assert verify_password(plain_password, hashed_password) is False


def test_verify_password_empty():
    plain_password = ''
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True


def test_verify_password_zero():
    plain_password = '0'
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True


def test_verify_password_negative():
    plain_password = '-1'
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True


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
    with patch('jose.jwt.decode') as mock_decode:
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


# ── Edge Cases ─────────────────────────────────────────────

def test_hash_password_empty():
    hashed_password = hash_password('')
    assert hashed_password is not None


def test_hash_password_zero():
    hashed_password = hash_password('0')
    assert hashed_password is not None


def test_hash_password_negative():
    hashed_password = hash_password('-1')
    assert hashed_password is not None


def test_verify_password_empty_hashed():
    plain_password = 'password123'
    hashed_password = hash_password('')
    assert verify_password(plain_password, hashed_password) is False


def test_verify_password_zero_hashed():
    plain_password = 'password123'
    hashed_password = hash_password('0')
    assert verify_password(plain_password, hashed_password) is False


def test_verify_password_negative_hashed():
    plain_password = 'password123'
    hashed_password = hash_password('-1')
    assert verify_password(plain_password, hashed_password) is False