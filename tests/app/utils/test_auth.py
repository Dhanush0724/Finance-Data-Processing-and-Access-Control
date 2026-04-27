import pytest
from unittest.mock import patch
from jose import JWTError

from app.utils.auth import (
    create_access_token,
    decode_token
)


@pytest.fixture
def mock_settings():
    with patch('app.utils.config.settings') as mock:
        mock.access_token_expire_minutes = 30
        mock.secret_key = 'secret_key'
        mock.algorithm = 'HS256'
        yield mock


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


# ── Safe Edge Cases ──────────────────────────────────────────

def test_create_access_token_empty_subject(mock_settings):
    token = create_access_token('', 'admin')
    assert token is not None


def test_create_access_token_empty_role(mock_settings):
    token = create_access_token('user123', '')
    assert token is not None