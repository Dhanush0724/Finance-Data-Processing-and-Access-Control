from datetime import datetime, timezone
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.models.models import Transaction, TransactionType
from app.schemas.schemas import (
    CategoryTotal, MonthlyTrend, DashboardSummary, TransactionOut
)


def get_dashboard_summary(db: Session) -> DashboardSummary:
    active = db.query(Transaction).filter(Transaction.is_deleted == False)  # noqa: E712

    # ── Totals ──────────────────────────────────────────────────────────────
    income_q  = active.filter(Transaction.type == TransactionType.income)
    expense_q = active.filter(Transaction.type == TransactionType.expense)

    total_income  = income_q.with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    total_expense = expense_q.with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar()
    tx_count      = active.count()

    # ── Category breakdowns ─────────────────────────────────────────────────
    def category_totals(query) -> list[CategoryTotal]:
        rows = (
            query
            .with_entities(
                Transaction.category,
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
            .all()
        )
        return [CategoryTotal(category=r.category, total=round(r.total, 2), count=r.count) for r in rows]

    income_by_cat  = category_totals(income_q)
    expense_by_cat = category_totals(expense_q)

    # ── Monthly trends (last 12 months) ─────────────────────────────────────
    monthly_rows = (
        active
        .with_entities(
            extract("year",  Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
        )
        .group_by("year", "month", Transaction.type)
        .order_by("year", "month")
        .all()
    )

    trend_map: dict[tuple, dict] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for row in monthly_rows:
        key = (int(row.year), int(row.month))
        trend_map[key][row.type.value] += float(row.total)

    monthly_trends = [
        MonthlyTrend(
            year=y, month=m,
            income=round(v["income"], 2),
            expense=round(v["expense"], 2),
            net=round(v["income"] - v["expense"], 2),
        )
        for (y, m), v in sorted(trend_map.items())
    ]

    # ── Recent activity ──────────────────────────────────────────────────────
    recent_txs = (
        active
        .order_by(Transaction.date.desc())
        .limit(10)
        .all()
    )

    return DashboardSummary(
        total_income=round(float(total_income), 2),
        total_expense=round(float(total_expense), 2),
        net_balance=round(float(total_income) - float(total_expense), 2),
        transaction_count=tx_count,
        income_by_category=income_by_cat,
        expense_by_category=expense_by_cat,
        monthly_trends=monthly_trends,
        recent_transactions=[TransactionOut.model_validate(t) for t in recent_txs],
    )
