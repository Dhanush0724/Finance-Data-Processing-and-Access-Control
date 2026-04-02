from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from app.services import auth_service, user_service
from app.middleware.auth_deps import get_current_user
from app.models.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and receive a JWT bearer token."""
    return auth_service.login(body.email, body.password, db)


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: UserCreate, db: Session = Depends(get_db)):
    """
    Self-registration endpoint (creates a viewer by default).
    Admins should use POST /users to assign higher roles.
    """
    # Force viewer role on self-registration to prevent privilege escalation
    body.role = "viewer"
    return user_service.create_user(body, db)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user
