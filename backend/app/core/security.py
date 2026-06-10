"""Security baseline — SCAFFOLD ONLY (authentication is implemented in Phase 11).

This module fixes the *shape* of authentication/authorization so the rest of the
codebase can depend on stable interfaces, without committing to an implementation
yet. Nothing here enforces auth; the functions are deliberately unimplemented.

Planned design (see docs/04_API_DESIGN.md §3 and docs/09_DEVELOPMENT_GUIDELINES.md):
  * AuthN: OAuth2 password flow → short-lived JWT access token + refresh token.
  * AuthZ: role-based access control (RBAC).
  * Resource scoping: every query filtered by org_id (multi-tenant ready).
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """RBAC roles. Permissions are enforced in Phase 11."""

    VIEWER = "viewer"        # read-only access to processed data
    ANALYST = "analyst"      # viewer + upload + generate (memo/benchmark)
    ADMIN = "admin"          # manage users, companies, system settings


# Coarse capability map used to plan endpoint guards. NOT yet enforced.
ROLE_HIERARCHY: dict[Role, set[Role]] = {
    Role.ADMIN: {Role.ADMIN, Role.ANALYST, Role.VIEWER},
    Role.ANALYST: {Role.ANALYST, Role.VIEWER},
    Role.VIEWER: {Role.VIEWER},
}


def create_access_token(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
    """Issue a signed JWT access token. Implemented in Phase 11."""
    raise NotImplementedError("Authentication is implemented in Phase 11 (Production Hardening).")


def decode_token(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
    """Verify and decode a JWT. Implemented in Phase 11."""
    raise NotImplementedError("Authentication is implemented in Phase 11 (Production Hardening).")


def hash_password(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
    """Hash a password (passlib/bcrypt). Implemented in Phase 11."""
    raise NotImplementedError("Authentication is implemented in Phase 11 (Production Hardening).")
