from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.models import User
from app.utils.auth import verify_password, create_access_token


def login(email: str, password: str, db: Session) -> dict:
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    token = create_access_token(subject=user.id, role=user.role.value)
    return {"access_token": token, "token_type": "bearer", "user": user}
