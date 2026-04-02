import uuid
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.models import User, UserRole
from app.schemas.schemas import UserCreate, UserUpdate
from app.utils.auth import hash_password


def create_user(data: UserCreate, db: Session) -> User:
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        id=str(uuid.uuid4()),
        email=data.email,
        name=data.name,
        hashed_pw=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


def get_user(user_id: str, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def update_user(user_id: str, data: UserUpdate, db: Session) -> User:
    user = get_user(user_id, db)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(user_id: str, requesting_user: User, db: Session) -> None:
    if user_id == requesting_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    user = get_user(user_id, db)
    db.delete(user)
    db.commit()
