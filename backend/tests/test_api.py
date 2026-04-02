"""
Integration tests for the Finance Dashboard API.

Run:
    cd backend
    pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db, Base
from app.models.models import User, UserRole
from app.utils.auth import hash_password
import uuid

# ── In-memory SQLite for tests ───────────────────────────────────────────────
TEST_DB_URL = "sqlite://"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _make_user(db, email="test@test.com", role=UserRole.admin, password="secret123"):
    user = User(
        id=str(uuid.uuid4()), email=email, name="Test User",
        hashed_pw=hash_password(password), role=role,
    )
    db.add(user)
    db.commit()
    return user


def _login(client, email, password="secret123"):
    res = client.post("/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Auth tests ────────────────────────────────────────────────────────────────

class TestAuth:
    def test_login_success(self, client, db):
        _make_user(db)
        res = client.post("/auth/login", json={"email": "test@test.com", "password": "secret123"})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_login_wrong_password(self, client, db):
        _make_user(db)
        res = client.post("/auth/login", json={"email": "test@test.com", "password": "wrong"})
        assert res.status_code == 401

    def test_login_unknown_email(self, client):
        res = client.post("/auth/login", json={"email": "no@one.com", "password": "x"})
        assert res.status_code == 401

    def test_me_returns_user(self, client, db):
        _make_user(db)
        token = _login(client, "test@test.com")
        res = client.get("/auth/me", headers=_auth(token))
        assert res.status_code == 200
        assert res.json()["email"] == "test@test.com"

    def test_me_no_token(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 403  # HTTPBearer returns 403 when header absent

    def test_register_creates_viewer(self, client):
        res = client.post("/auth/register", json={
            "email": "new@test.com", "name": "New User",
            "password": "pass123", "role": "admin",  # should be downgraded
        })
        assert res.status_code == 201
        assert res.json()["role"] == "viewer"


# ── User management tests ─────────────────────────────────────────────────────

class TestUsers:
    def test_admin_can_list_users(self, client, db):
        _make_user(db)
        token = _login(client, "test@test.com")
        res = client.get("/users", headers=_auth(token))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_viewer_cannot_list_users(self, client, db):
        _make_user(db, email="viewer@test.com", role=UserRole.viewer)
        token = _login(client, "viewer@test.com")
        res = client.get("/users", headers=_auth(token))
        assert res.status_code == 403

    def test_admin_can_create_user(self, client, db):
        _make_user(db)
        token = _login(client, "test@test.com")
        res = client.post("/users", headers=_auth(token), json={
            "email": "new@test.com", "name": "New", "password": "pass123", "role": "analyst"
        })
        assert res.status_code == 201
        assert res.json()["role"] == "analyst"

    def test_duplicate_email_rejected(self, client, db):
        _make_user(db)
        token = _login(client, "test@test.com")
        res = client.post("/users", headers=_auth(token), json={
            "email": "test@test.com", "name": "Dup", "password": "pass123", "role": "viewer"
        })
        assert res.status_code == 409

    def test_admin_can_update_role(self, client, db):
        admin = _make_user(db)
        _make_user(db, email="other@test.com", role=UserRole.viewer)
        token = _login(client, "test@test.com")
        other = db.query(User).filter(User.email == "other@test.com").first()
        res = client.patch(f"/users/{other.id}", headers=_auth(token), json={"role": "analyst"})
        assert res.status_code == 200
        assert res.json()["role"] == "analyst"


# ── Transaction tests ─────────────────────────────────────────────────────────

class TestTransactions:
    def _create_tx(self, client, token, overrides=None):
        payload = {
            "amount": 500.0, "type": "expense", "category": "groceries",
            "date": "2024-06-15T00:00:00", "description": "Weekly shop",
        }
        if overrides:
            payload.update(overrides)
        return client.post("/transactions", headers=_auth(token), json=payload)

    def test_analyst_can_create(self, client, db):
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        token = _login(client, "analyst@test.com")
        res = self._create_tx(client, token)
        assert res.status_code == 201
        assert res.json()["category"] == "groceries"

    def test_viewer_cannot_create(self, client, db):
        _make_user(db, email="viewer@test.com", role=UserRole.viewer)
        token = _login(client, "viewer@test.com")
        res = self._create_tx(client, token)
        assert res.status_code == 403

    def test_negative_amount_rejected(self, client, db):
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        token = _login(client, "analyst@test.com")
        res = self._create_tx(client, token, {"amount": -100})
        assert res.status_code == 422

    def test_viewer_can_list(self, client, db):
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        _make_user(db, email="viewer@test.com", role=UserRole.viewer)
        a_token = _login(client, "analyst@test.com")
        self._create_tx(client, a_token)
        v_token = _login(client, "viewer@test.com")
        res = client.get("/transactions", headers=_auth(v_token))
        assert res.status_code == 200
        assert res.json()["total"] == 1

    def test_filter_by_type(self, client, db):
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        token = _login(client, "analyst@test.com")
        self._create_tx(client, token, {"type": "income", "category": "salary"})
        self._create_tx(client, token, {"type": "expense", "category": "rent"})
        res = client.get("/transactions?type=income", headers=_auth(token))
        assert res.json()["total"] == 1

    def test_soft_delete(self, client, db):
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        token = _login(client, "analyst@test.com")
        tx_id = self._create_tx(client, token).json()["id"]
        del_res = client.delete(f"/transactions/{tx_id}", headers=_auth(token))
        assert del_res.status_code == 204
        # Should not appear in list
        list_res = client.get("/transactions", headers=_auth(token))
        assert list_res.json()["total"] == 0

    def test_analyst_cannot_edit_others_transaction(self, client, db):
        _make_user(db, email="admin@test.com", role=UserRole.admin)
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        a_token = _login(client, "admin@test.com")
        tx_id = self._create_tx(client, a_token).json()["id"]
        b_token = _login(client, "analyst@test.com")
        res = client.patch(f"/transactions/{tx_id}", headers=_auth(b_token),
                           json={"amount": 999})
        assert res.status_code == 403


# ── Dashboard tests ───────────────────────────────────────────────────────────

class TestDashboard:
    def test_summary_returns_correct_totals(self, client, db):
        _make_user(db, email="analyst@test.com", role=UserRole.analyst)
        token = _login(client, "analyst@test.com")
        client.post("/transactions", headers=_auth(token), json={
            "amount": 1000, "type": "income", "category": "salary",
            "date": "2024-01-15T00:00:00",
        })
        client.post("/transactions", headers=_auth(token), json={
            "amount": 300, "type": "expense", "category": "rent",
            "date": "2024-01-20T00:00:00",
        })
        res = client.get("/dashboard/summary", headers=_auth(token))
        assert res.status_code == 200
        data = res.json()
        assert data["total_income"]  == 1000.0
        assert data["total_expense"] == 300.0
        assert data["net_balance"]   == 700.0

    def test_viewer_can_access_dashboard(self, client, db):
        _make_user(db, email="viewer@test.com", role=UserRole.viewer)
        token = _login(client, "viewer@test.com")
        res = client.get("/dashboard/summary", headers=_auth(token))
        assert res.status_code == 200
