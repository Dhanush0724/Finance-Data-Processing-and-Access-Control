import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from datetime import datetime

from app.main import app
from app.models.models import User, UserRole, TransactionType

client = TestClient(app)


# ✅ Override auth
from app.middleware.auth_deps import require_analyst, require_viewer

def override_user():
    return User(
        id="1",
        email="test@test.com",
        name="Test User",
        hashed_pw="dummy",
        role=UserRole.analyst,
        is_active=True
    )

app.dependency_overrides[require_analyst] = override_user
app.dependency_overrides[require_viewer] = override_user


# ✅ Patch service
@pytest.fixture(autouse=True)
def mock_service():
    with patch("app.routes.transactions.transaction_service") as mock:
        yield mock


# ── Helpers ────────────────────────────────────────────────────────────────────

def valid_tx_payload():
    return {
        "amount": 100.0,
        "type": "income",
        "category": "general",
        "date": datetime.now().isoformat(),
        "description": "Test transaction"
    }


def valid_tx_response():
    return {
        "id": "1",
        "amount": 100.0,
        "type": "income",
        "category": "general",
        "date": datetime.now().isoformat(),
        "description": "Test transaction",
        "created_by": "1",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


def valid_paginated_response(items=None):
    """Matches PaginatedTransactions schema fields exactly."""
    return {
        "items":       items or [],
        "total":       len(items) if items else 0,
        "page":        1,
        "page_size":   20,
        "total_pages": 1,
    }


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_create_transaction_happy_path(mock_service):
    mock_service.create_transaction.return_value = valid_tx_response()
    response = client.post("/transactions", json=valid_tx_payload())
    assert response.status_code == 201
    assert response.json()["id"] == "1"


def test_create_transaction_negative_amount(mock_service):
    data = valid_tx_payload()
    data["amount"] = -50.0
    response = client.post("/transactions", json=data)
    assert response.status_code == 422


def test_create_transaction_zero_amount(mock_service):
    data = valid_tx_payload()
    data["amount"] = 0.0
    response = client.post("/transactions", json=data)
    assert response.status_code == 422


def test_list_transactions_happy_path(mock_service):
    mock_service.list_transactions.return_value = valid_paginated_response()
    response = client.get("/transactions")
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["page"] == 1


def test_list_transactions_with_filters(mock_service):
    mock_service.list_transactions.return_value = valid_paginated_response(
        items=[valid_tx_response()]
    )
    response = client.get("/transactions?type=income&category=general")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_list_transactions_with_invalid_filters(mock_service):
    response = client.get("/transactions?type=invalid&category=general")
    assert response.status_code == 422


def test_get_transaction_happy_path(mock_service):
    mock_service.get_transaction.return_value = valid_tx_response()
    response = client.get("/transactions/1")
    assert response.status_code == 200
    assert response.json()["id"] == "1"


def test_get_transaction_not_found(mock_service):
    mock_service.get_transaction.side_effect = HTTPException(status_code=404, detail="Not found")
    response = client.get("/transactions/999")
    assert response.status_code == 404


def test_update_transaction_happy_path(mock_service):
    mock_service.update_transaction.return_value = valid_tx_response()
    response = client.patch("/transactions/1", json=valid_tx_payload())
    assert response.status_code == 200


def test_update_transaction_not_found(mock_service):
    mock_service.update_transaction.side_effect = HTTPException(status_code=404, detail="Not found")
    response = client.patch("/transactions/999", json=valid_tx_payload())
    assert response.status_code == 404


def test_update_transaction_negative_amount(mock_service):
    data = valid_tx_payload()
    data["amount"] = -50.0
    response = client.patch("/transactions/1", json=data)
    assert response.status_code == 422


def test_update_transaction_zero_amount(mock_service):
    data = valid_tx_payload()
    data["amount"] = 0.0
    response = client.patch("/transactions/1", json=data)
    assert response.status_code == 422


def test_delete_transaction_happy_path(mock_service):
    response = client.delete("/transactions/1")
    assert response.status_code == 204


def test_delete_transaction_not_found(mock_service):
    mock_service.delete_transaction.side_effect = HTTPException(status_code=404, detail="Not found")
    response = client.delete("/transactions/999")
    assert response.status_code == 404


def test_ping():
    response = client.get("/transactions/health/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_export_summary():
    response = client.get("/transactions/export/summary")
    assert response.status_code == 200
    assert response.json() == {"message": "Export feature coming soon", "status": "placeholder"}


def test_create_transaction_permission_check():
    app.dependency_overrides[require_analyst] = lambda: User(
        id="1",
        email="test@test.com",
        name="Test User",
        hashed_pw="dummy",
        role=UserRole.viewer,
        is_active=True
    )
    response = client.post("/transactions", json=valid_tx_payload())
    assert response.status_code == 403


def test_update_transaction_permission_check():
    app.dependency_overrides[require_analyst] = lambda: User(
        id="1",
        email="test@test.com",
        name="Test User",
        hashed_pw="dummy",
        role=UserRole.viewer,
        is_active=True
    )
    response = client.patch("/transactions/1", json=valid_tx_payload())
    assert response.status_code == 403


def test_delete_transaction_permission_check():
    app.dependency_overrides[require_analyst] = lambda: User(
        id="1",
        email="test@test.com",
        name="Test User",
        hashed_pw="dummy",
        role=UserRole.viewer,
        is_active=True
    )
    response = client.delete("/transactions/1")
    assert response.status_code == 403