from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.schemas import DashboardSummary
from app.services import dashboard_service
from app.middleware.auth_deps import require_viewer
from app.models.models import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),  # all authenticated roles can view dashboard
):
    """
    Aggregated dashboard data:
    totals, category breakdowns, monthly trends, recent activity.
    """
    return dashboard_service.get_dashboard_summary(db)
