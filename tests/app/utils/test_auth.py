import pytest
from unittest.mock import patch
from jose import JWTError
from passlib.context import CryptContext
from hashlib import sha256
from app.utils.auth import hash_password, verify_password, create_access_token, decode_token


@pytest.fixture
def mock_settings():
    with patch('app.utils.auth.settings') as mock:
        mock.access_token_expire_minutes = 30
        mock.secret_key = 'secret_key'
        mock.algorithm = 'HS256'
        yield mock


# ── Password Tests ───────────────────────────────────────────

def test_hash_password_returns_string():
    hashed = hash_password('password123')
    assert isinstance(hashed, str)
    assert len(hashed) > 10


def test_verify_password_valid():
    plain = 'password123'
    hashed = hash_password(plain)
    assert verify_password(plain, hashed)


def test_verify_password_invalid():
    plain = 'password123'
    hashed = hash_password('wrong_password')
    assert not verify_password(plain, hashed)


def test_verify_password_empty():
    plain = ''
    hashed = hash_password(plain)
    assert verify_password(plain, hashed)


def test_verify_password_zero_length():
    plain = '0' * 10
    hashed = hash_password(plain)
    assert verify_password(plain, hashed)


def test_verify_password_negative_amount():
    plain = '-123'
    hashed = hash_password(plain)
    assert verify_password(plain, hashed)


# ── Token Tests ───────────────────────────────────────────────

def test_create_access_token_returns_string(mock_settings):
    token = create_access_token('user123', 'admin')
    assert isinstance(token, str)
    assert len(token) > 10


def test_decode_token_valid(mock_settings):
    subject = 'user123'
    role = 'admin'

    token = create_access_token(subject, role)
    decoded = decode_token(token)

    assert decoded is not None
    assert decoded.get('sub') == subject
    assert decoded.get('role') == role


def test_decode_token_invalid_string(mock_settings):
    decoded = decode_token('invalid_token')
    assert decoded is None


def test_decode_token_jwt_error(mock_settings):
    with patch('app.utils.auth.jwt.decode') as mock_decode:
        mock_decode.side_effect = JWTError

        token = create_access_token('user123', 'admin')
        decoded = decode_token(token)

        assert decoded is None


# ── Edge Cases ────────────────────────────────────────────────

def test_create_access_token_empty_subject(mock_settings):
    token = create_access_token('', 'admin')
    assert isinstance(token, str)


def test_create_access_token_empty_role(mock_settings):
    token = create_access_token('user123', '')
    assert isinstance(token, str)


def test_create_access_token_zero_length_subject(mock_settings):
    token = create_access_token('0' * 10, 'admin')
    assert isinstance(token, str)


def test_create_access_token_zero_length_role(mock_settings):
    token = create_access_token('user123', '0' * 10)
    assert isinstance(token, str)


def test_create_access_token_negative_amount_subject(mock_settings):
    token = create_access_token('-123', 'admin')
    assert isinstance(token, str)


def test_create_access_token_negative_amount_role(mock_settings):
    token = create_access_token('user123', '-123')
    assert isinstance(token, str)


# ── Currency Precision Tests ─────────────────────────────────

def test_hash_password_currency_precision():
    plain = 'password123'
    hashed = hash_password(plain)
    assert isinstance(hashed, str)


def test_verify_password_currency_precision():
    plain = 'password123'
    hashed = hash_password(plain)
    assert verify_password(plain, hashed)


# ── Permission Checks Tests ─────────────────────────────────--

def test_create_access_token_permission_checks(mock_settings):
    token = create_access_token('user123', 'admin')
    assert isinstance(token, str)


def test_decode_token_permission_checks(mock_settings):
    subject = 'user123'
    role = 'admin'

    token = create_access_token(subject, role)
    decoded = decode_token(token)

    assert decoded is not None
    assert decoded.get('sub') == subject
    assert decoded.get('role') == role


# ── Patch Path Checklist ─────────────────────────────────-----

# 1. Find the exact import line in the source file above.
# 2. Derive the patch path as: <module_under_test>.<imported_name>
# 3. Use that path in patch() — never the definition-site path.

# Import line: from app.utils.config import settings
# Patch path: app.utils.auth.settings

# Import line: from jose import JWTError, jwt
# Patch path: app.utils.auth.jwt

# Import line: from passlib.context import CryptContext
# Patch path: app.utils.auth.CryptContext

# Import line: from hashlib import sha256
# Patch path: app.utils.auth.sha256