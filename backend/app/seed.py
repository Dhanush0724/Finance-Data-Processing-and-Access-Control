"""
Run once to seed an admin user + sample transactions.
    python -m app.seed
"""
import uuid
from datetime import datetime, timezone, timedelta
import random

from app.database import SessionLocal, engine
from app.models.models import Base, User, UserRole, Transaction, TransactionType
from app.utils.auth import hash_password

CATEGORIES_INCOME  = ["salary", "freelance", "investment", "rental", "bonus"]
CATEGORIES_EXPENSE = ["rent", "groceries", "utilities", "transport", "entertainment", "healthcare", "subscriptions"]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # ── Seed users ────────────────────────────────────────────────────────────
    users_data = [
        {"email": "admin@finance.dev",   "name": "Alice Admin",   "role": UserRole.admin,   "password": "admin123"},
        {"email": "analyst@finance.dev", "name": "Bob Analyst",   "role": UserRole.analyst, "password": "analyst123"},
        {"email": "viewer@finance.dev",  "name": "Carol Viewer",  "role": UserRole.viewer,  "password": "viewer123"},
    ]

    created_users = []
    for u in users_data:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if not existing:
            user = User(
                id=str(uuid.uuid4()),
                email=u["email"],
                name=u["name"],
                role=u["role"],
                hashed_pw=hash_password(u["password"]),
            )
            db.add(user)
            db.flush()
            created_users.append(user)
            print(f"  Created user: {u['email']} ({u['role'].value})")
        else:
            created_users.append(existing)

    db.commit()

    # ── Seed transactions (12 months of data) ────────────────────────────────
    admin_user = db.query(User).filter(User.role == UserRole.admin).first()
    if db.query(Transaction).count() == 0:
        now = datetime.now(timezone.utc)
        txs = []
        for month_offset in range(12):
            month_date = now - timedelta(days=30 * month_offset)

            # Monthly income
            txs.append(Transaction(
                id=str(uuid.uuid4()), amount=round(random.uniform(4000, 8000), 2),
                type=TransactionType.income, category="salary",
                date=month_date.replace(day=1),
                description="Monthly salary", created_by=admin_user.id,
            ))

            # 5–10 expenses per month
            for _ in range(random.randint(5, 10)):
                day_offset = random.randint(0, 27)
                txs.append(Transaction(
                    id=str(uuid.uuid4()), amount=round(random.uniform(20, 800), 2),
                    type=TransactionType.expense,
                    category=random.choice(CATEGORIES_EXPENSE),
                    date=month_date.replace(day=1) + timedelta(days=day_offset),
                    description=f"Sample expense", created_by=admin_user.id,
                ))

            # Occasional extra income
            if random.random() > 0.6:
                txs.append(Transaction(
                    id=str(uuid.uuid4()), amount=round(random.uniform(200, 2000), 2),
                    type=TransactionType.income,
                    category=random.choice(["freelance", "investment", "bonus"]),
                    date=month_date, description="Additional income", created_by=admin_user.id,
                ))

        db.add_all(txs)
        db.commit()
        print(f"  Seeded {len(txs)} transactions across 12 months")

    db.close()
    print("\nSeed complete. Login credentials:")
    print("  admin@finance.dev   / admin123")
    print("  analyst@finance.dev / analyst123")
    print("  viewer@finance.dev  / viewer123")


if __name__ == "__main__":
    seed()
