from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import TransactionType, User
from app.schemas.schemas import (
    TransactionCreate, TransactionUpdate,
    TransactionOut, PaginatedTransactions,
)
from app.services import transaction_service
from app.middleware.auth_deps import require_viewer, require_analyst, require_admin

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(
    body: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),  # analyst + admin can create
):
    """Create a financial record. Requires analyst or admin role."""
    return transaction_service.create_transaction(body, current_user, db)


@router.get("", response_model=PaginatedTransactions)
def list_transactions(
    type: Optional[TransactionType] = Query(default=None),
    category: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),  # all authenticated users can read
):
    """
    List transactions with optional filters.
    Supports: type, category, date range, full-text search, pagination.
    """
    return transaction_service.list_transactions(
        db, type=type, category=category,
        date_from=date_from, date_to=date_to,
        search=search, page=page, page_size=page_size,
    )


@router.get("/{tx_id}", response_model=TransactionOut)
def get_transaction(
    tx_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    return transaction_service.get_transaction(tx_id, db)


@router.patch("/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: str,
    body: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Update a transaction. Analysts can only edit their own; admins can edit all."""
    return transaction_service.update_transaction(tx_id, body, current_user, db)


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(
    tx_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_analyst),
):
    """Soft-delete a transaction."""
    transaction_service.delete_transaction(tx_id, current_user, db)
