from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User, UserRole
from app.utils.auth import decode_token

bearer_scheme = HTTPBearer()


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = db.query(User).filter(User.id == payload["sub"]).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    return user


# Alias for readability in route signatures
get_current_user = _get_current_user


def require_roles(*roles: UserRole):
    """Factory: returns a dependency that asserts the current user has one of the given roles."""
    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {[r.value for r in roles]}",
            )
        return current_user
    return _check


# Convenience role guards
require_admin   = require_roles(UserRole.admin)
require_analyst = require_roles(UserRole.analyst, UserRole.admin)
require_viewer  = require_roles(UserRole.viewer, UserRole.analyst, UserRole.admin)
