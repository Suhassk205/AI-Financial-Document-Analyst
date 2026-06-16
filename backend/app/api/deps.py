"""FastAPI dependencies for security and db (Phase 11)."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.security import ROLE_HIERARCHY, decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

# OAuth2 scheme using token endpoint (auto_error=False to allow local fallback)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False
)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
) -> User:
    """Extract and authenticate the current user from JWT token."""
    if settings.demo_mode:
        stmt = select(User).where(User.email == "demo@example.com")
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            from app.core.security import hash_password
            user = User(
                email="demo@example.com",
                password_hash=hash_password("demopassword"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    if settings.app_env.value == "local" and not token:
        # For local development, automatically fall back to or create a dev admin user
        stmt = select(User).where(User.email == "dev@example.com")
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            from app.core.security import hash_password
            user = User(
                email="dev@example.com",
                password_hash=hash_password("devpassword"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user

    if not token:
        raise AuthenticationError("Not authenticated")

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Could not validate credentials")
    except Exception as e:
        raise AuthenticationError("Could not validate credentials") from e

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")

    return user


async def get_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the user is active."""
    if not current_user.is_active:
        raise AuthenticationError("User is inactive")
    return current_user


class RoleChecker:
    """Enforce RBAC role hierarchy."""

    def __init__(self, required_role: UserRole) -> None:
        self.required_role = required_role

    def __call__(
        self,
        current_user: User = Depends(get_active_user),
    ) -> User:
        user_role = current_user.role

        # Check if the user's role is in the allowed roles based on ROLE_HIERARCHY
        allowed_roles = ROLE_HIERARCHY.get(user_role, set())
        if self.required_role not in allowed_roles:
            raise ForbiddenError(
                f"Role {self.required_role.value} is required for this action."
            )

        return current_user
