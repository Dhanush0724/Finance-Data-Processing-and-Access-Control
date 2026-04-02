import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.models import Transaction, TransactionType, User, UserRole
from app.schemas.schemas import TransactionCreate, TransactionUpdate


def create_transaction(data: TransactionCreate, current_user: User, db: Session) -> Transaction:
    tx = Transaction(
        id=str(uuid.uuid4()),
        amount=data.amount,
        type=data.type,
        category=data.category.strip().lower(),
        date=data.date,
        description=data.description,
        created_by=current_user.id,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def list_transactions(
    db: Session,
    type: Optional[TransactionType] = None,
    category: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = db.query(Transaction).filter(Transaction.is_deleted == False)  # noqa: E712

    if type:
        query = query.filter(Transaction.type == type)
    if category:
        query = query.filter(Transaction.category == category.strip().lower())
    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)
    if search:
        term = f"%{search.lower()}%"
        query = query.filter(
            Transaction.description.ilike(term) | Transaction.category.ilike(term)
        )

    total = query.count()
    items = (
        query.order_by(Transaction.date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),  # ceiling division
    }


def get_transaction(tx_id: str, db: Session) -> Transaction:
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id,
        Transaction.is_deleted == False,  # noqa: E712
    ).first()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx


def update_transaction(
    tx_id: str, data: TransactionUpdate, current_user: User, db: Session
) -> Transaction:
    tx = get_transaction(tx_id, db)

    # Only admin can edit others' records; analysts/viewers cannot edit at all
    if current_user.role != UserRole.admin and tx.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    update_data = data.model_dump(exclude_unset=True)
    if "category" in update_data:
        update_data["category"] = update_data["category"].strip().lower()

    for field, value in update_data.items():
        setattr(tx, field, value)

    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction(tx_id: str, current_user: User, db: Session) -> None:
    tx = get_transaction(tx_id, db)

    if current_user.role != UserRole.admin and tx.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    tx.is_deleted = True  # soft delete
    db.commit()
