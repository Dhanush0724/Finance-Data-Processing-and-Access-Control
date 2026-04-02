from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, DateTime,
    Enum, ForeignKey, Text, Integer,
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    viewer  = "viewer"   # read-only dashboard access
    analyst = "analyst"  # read + summary/insights
    admin   = "admin"    # full CRUD + user management


class TransactionType(str, enum.Enum):
    income  = "income"
    expense = "expense"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id         = Column(String, primary_key=True)
    email      = Column(String, unique=True, nullable=False, index=True)
    name       = Column(String, nullable=False)
    hashed_pw  = Column(String, nullable=False)
    role       = Column(Enum(UserRole), default=UserRole.viewer, nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    transactions = relationship("Transaction", back_populates="created_by_user",
                                foreign_keys="Transaction.created_by")


# ---------------------------------------------------------------------------
# Transaction (financial record)
# ---------------------------------------------------------------------------

class Transaction(Base):
    __tablename__ = "transactions"

    id          = Column(String, primary_key=True)
    amount      = Column(Float, nullable=False)
    type        = Column(Enum(TransactionType), nullable=False)
    category    = Column(String, nullable=False, index=True)
    date        = Column(DateTime, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_deleted  = Column(Boolean, default=False, nullable=False)  # soft delete
    created_by  = Column(String, ForeignKey("users.id"), nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))

    created_by_user = relationship("User", back_populates="transactions",
                                   foreign_keys=[created_by])
