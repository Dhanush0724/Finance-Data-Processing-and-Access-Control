from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.models import UserRole, TransactionType


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6)
    role: UserRole = UserRole.viewer


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Transaction schemas
# ---------------------------------------------------------------------------

class TransactionCreate(BaseModel):
    amount: float = Field(gt=0, description="Must be positive; type determines income vs expense")
    type: TransactionType
    category: str = Field(min_length=1, max_length=100)
    date: datetime
    description: Optional[str] = Field(default=None, max_length=500)


class TransactionUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    type: Optional[TransactionType] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=100)
    date: Optional[datetime] = None
    description: Optional[str] = Field(default=None, max_length=500)


class TransactionOut(BaseModel):
    id: str
    amount: float
    type: TransactionType
    category: str
    date: datetime
    description: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedTransactions(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Dashboard / summary schemas
# ---------------------------------------------------------------------------

class CategoryTotal(BaseModel):
    category: str
    total: float
    count: int


class MonthlyTrend(BaseModel):
    year: int
    month: int
    income: float
    expense: float
    net: float


class DashboardSummary(BaseModel):
    total_income: float
    total_expense: float
    net_balance: float
    transaction_count: int
    income_by_category: list[CategoryTotal]
    expense_by_category: list[CategoryTotal]
    monthly_trends: list[MonthlyTrend]
    recent_transactions: list[TransactionOut]
