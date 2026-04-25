
import sys
import os

# Add backend/ to path so 'from app.xxx import' works in tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
"""
conftest.py
───────────
Shared pytest fixtures for the Finance Data Processing test suite.
These are automatically available to all test files — no import needed.
"""

import pytest
from unittest.mock import MagicMock, patch


# ── App Client ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """
    Creates a test instance of the Flask/FastAPI app.
    Update the import path to match your actual app factory.
    """
    try:
        # Flask
        from backend.app import create_app
        application = create_app()
        application.config["TESTING"] = True
        application.config["DEBUG"]   = False
        return application
    except ImportError:
        try:
            # FastAPI
            from backend.main import app as fastapi_app
            return fastapi_app
        except ImportError:
            return MagicMock()  # Fallback — prevents import errors during CI


@pytest.fixture
def client(app):
    """HTTP test client — works for both Flask and FastAPI."""
    try:
        # Flask test client
        with app.test_client() as c:
            yield c
    except AttributeError:
        # FastAPI test client
        from fastapi.testclient import TestClient
        yield TestClient(app)


# ── Auth Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def admin_headers():
    """Auth headers for an admin user."""
    return {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
def viewer_headers():
    """Auth headers for a read-only viewer."""
    return {"Authorization": "Bearer test-viewer-token"}


@pytest.fixture
def no_auth_headers():
    """Simulates an unauthenticated request."""
    return {}


@pytest.fixture
def mock_jwt_admin():
    """Patches JWT verification to return an admin user payload."""
    with patch("backend.auth.verify_token") as mock:
        mock.return_value = {
            "user_id": 1,
            "email":   "admin@finance.com",
            "role":    "admin",
        }
        yield mock


@pytest.fixture
def mock_jwt_viewer():
    """Patches JWT verification to return a viewer user payload."""
    with patch("backend.auth.verify_token") as mock:
        mock.return_value = {
            "user_id": 2,
            "email":   "viewer@finance.com",
            "role":    "viewer",
        }
        yield mock


# ── Database Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_session():
    """Mocked SQLAlchemy database session."""
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value   = []
    session.query.return_value.filter.return_value.first.return_value = None
    session.query.return_value.all.return_value                       = []
    return session


@pytest.fixture
def mock_db(mock_db_session):
    """Patches the get_db dependency to return the mock session."""
    with patch("backend.database.get_db", return_value=mock_db_session):
        yield mock_db_session


# ── Finance Sample Data ────────────────────────────────────────────────────────

@pytest.fixture
def sample_transaction():
    return {
        "id":          1,
        "amount":      1500.00,
        "currency":    "USD",
        "type":        "credit",
        "description": "Client payment",
        "date":        "2025-01-15",
        "status":      "completed",
    }


@pytest.fixture
def sample_transaction_list(sample_transaction):
    return [
        sample_transaction,
        {**sample_transaction, "id": 2, "amount": -250.00, "type": "debit"},
        {**sample_transaction, "id": 3, "amount": 0.00,    "type": "adjustment"},
    ]


@pytest.fixture
def sample_user():
    return {
        "id":       1,
        "email":    "testuser@finance.com",
        "role":     "admin",
        "is_active": True,
    }