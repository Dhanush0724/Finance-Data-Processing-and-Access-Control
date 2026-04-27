import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.utils.config import settings
from app.utils.auth import hash_password, verify_password, create_access_token, decode_token

@pytest.fixture
def mock_settings():
    with patch('app.utils.config.settings') as mock:
        mock.access_token_expire_minutes = 30
        mock.secret_key = 'secret_key'
        mock.algorithm = 'HS256'
        yield mock

def test_hash_password(mock_settings):
    plain_password = 'password123'
    hashed_password = hash_password(plain_password)
    assert hashed_password is not None

def test_hash_password_zero_length(mock_settings):
    plain_password = ''
    hashed_password = hash_password(plain_password)
    assert hashed_password is not None

def test_hash_password_negative_length(mock_settings):
    plain_password = '-password123'
    hashed_password = hash_password(plain_password)
    assert hashed_password is not None

def test_verify_password(mock_settings):
    plain_password = 'password123'
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True

def test_verify_password_zero_length(mock_settings):
    plain_password = ''
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True

def test_verify_password_negative_length(mock_settings):
    plain_password = '-password123'
    hashed_password = hash_password(plain_password)
    assert verify_password(plain_password, hashed_password) is True

def test_verify_password_incorrect(mock_settings):
    plain_password = 'password123'
    hashed_password = hash_password('wrong_password')
    assert verify_password(plain_password, hashed_password) is False

def test_create_access_token(mock_settings):
    subject = 'user123'
    role = 'admin'
    token = create_access_token(subject, role)
    assert token is not None

def test_decode_token(mock_settings):
    subject = 'user123'
    role = 'admin'
    token = create_access_token(subject, role)
    decoded_token = decode_token(token)
    assert decoded_token is not None
    assert decoded_token['sub'] == subject
    assert decoded_token['role'] == role

def test_decode_token_expired(mock_settings):
    subject = 'user123'
    role = 'admin'
    with patch('datetime.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime.now(timezone.utc) - timedelta(minutes=31)
        token = create_access_token(subject, role)
        decoded_token = decode_token(token)
        assert decoded_token is None

def test_decode_token_invalid(mock_settings):
    token = 'invalid_token'
    decoded_token = decode_token(token)
    assert decoded_token is None

def test_decode_token_jwt_error(mock_settings):
    with patch('jose.jwt.decode') as mock_jwt_decode:
        mock_jwt_decode.side_effect = JWTError
        subject = 'user123'
        role = 'admin'
        token = create_access_token(subject, role)
        decoded_token = decode_token(token)
        assert decoded_token is None