import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.schemas import TransactionCreate, TransactionUpdate, TransactionOut, PaginatedTransactions
from app.models.models import User

client = TestClient(app)

@pytest.fixture
def mock_db_session():
    with patch('app.database.get_db', return_value=MagicMock()) as mock:
        yield mock

@pytest.fixture
def mock_current_user():
    user = User(id=1, username='testuser', role='analyst')
    with patch('app.middleware.auth_deps.require_analyst', return_value=user):
        yield user

@pytest.fixture
def mock_transaction_service():
    with patch('app.services.transaction_service') as mock_service:
        yield mock_service

def test_create_transaction_happy_path(mock_db_session, mock_current_user, mock_transaction_service):
    transaction_data = TransactionCreate(amount=100.0, currency='USD', description='Test transaction')
    mock_transaction_service.create_transaction.return_value = TransactionOut(id='1', **transaction_data.dict())
    
    response = client.post("/transactions", json=transaction_data.dict())
    
    assert response.status_code == 201
    assert response.json()['id'] == '1'

def test_create_transaction_zero_amount(mock_db_session, mock_current_user, mock_transaction_service):
    transaction_data = TransactionCreate(amount=0.0, currency='USD', description='Zero amount transaction')
    mock_transaction_service.create_transaction.return_value = TransactionOut(id='2', **transaction_data.dict())
    
    response = client.post("/transactions", json=transaction_data.dict())
    
    assert response.status_code == 201
    assert response.json()['id'] == '2'

def test_create_transaction_negative_amount(mock_db_session, mock_current_user, mock_transaction_service):
    transaction_data = TransactionCreate(amount=-50.0, currency='USD', description='Negative amount transaction')
    
    response = client.post("/transactions", json=transaction_data.dict())
    
    assert response.status_code == 422  # Expecting validation error

def test_list_transactions_happy_path(mock_db_session, mock_current_user, mock_transaction_service):
    mock_transaction_service.list_transactions.return_value = {'transactions': [], 'total': 0}
    
    response = client.get("/transactions")
    
    assert response.status_code == 200
    assert response.json() == {'transactions': [], 'total': 0}

def test_get_transaction_happy_path(mock_db_session, mock_current_user, mock_transaction_service):
    mock_transaction_service.get_transaction.return_value = TransactionOut(id='1', amount=100.0, currency='USD', description='Test transaction')
    
    response = client.get("/transactions/1")
    
    assert response.status_code == 200
    assert response.json()['id'] == '1'

def test_update_transaction_happy_path(mock_db_session, mock_current_user, mock_transaction_service):
    transaction_data = TransactionUpdate(amount=150.0, currency='USD', description='Updated transaction')
    mock_transaction_service.update_transaction.return_value = TransactionOut(id='1', **transaction_data.dict())
    
    response = client.patch("/transactions/1", json=transaction_data.dict())
    
    assert response.status_code == 200
    assert response.json()['amount'] == 150.0

def test_delete_transaction_happy_path(mock_db_session, mock_current_user, mock_transaction_service):
    response = client.delete("/transactions/1")
    
    assert response.status_code == 204
    mock_transaction_service.delete_transaction.assert_called_once_with('1', mock_current_user, mock_db_session())

def test_ping(mock_db_session):
    response = client.get("/transactions/health/ping")
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_list_transactions_with_filters(mock_db_session, mock_current_user, mock_transaction_service):
    mock_transaction_service.list_transactions.return_value = {'transactions': [{'id': '1'}], 'total': 1}
    
    response = client.get("/transactions?type=expense&category=food&date_from=2023-01-01&date_to=2023-12-31&page=1&page_size=10")
    
    assert response.status_code == 200
    assert response.json()['total'] == 1

def test_get_transaction_not_found(mock_db_session, mock_current_user, mock_transaction_service):
    mock_transaction_service.get_transaction.side_effect = Exception("Transaction not found")
    
    response = client.get("/transactions/999")
    
    assert response.status_code == 404  # Expecting not found error

def test_update_transaction_not_found(mock_db_session, mock_current_user, mock_transaction_service):
    transaction_data = TransactionUpdate(amount=150.0, currency='USD', description='Updated transaction')
    mock_transaction_service.update_transaction.side_effect = Exception("Transaction not found")
    
    response = client.patch("/transactions/999", json=transaction_data.dict())
    
    assert response.status_code == 404  # Expecting not found error