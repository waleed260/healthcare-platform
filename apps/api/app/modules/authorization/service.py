from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


class ForbiddenError(RuntimeError):
    code = "FORBIDDEN"


def has_permission(db: Session, user_id: UUID, clinic_id: UUID, permission_code: str, branch_id: UUID | None = None) -> bool:
    branch_clause = ""
    params: dict[str, object] = {"user_id": user_id, "clinic_id": clinic_id, "permission_code": permission_code}
    if branch_id is not None:
        branch_clause = """
            AND (
                NOT EXISTS (SELECT 1 FROM user_branch_scopes scope WHERE scope.clinic_id = :clinic_id AND scope.user_id = :user_id)
                OR EXISTS (
                    SELECT 1 FROM user_branch_scopes scope
                    WHERE scope.clinic_id = :clinic_id AND scope.user_id = :user_id AND scope.branch_id = :branch_id
                )
            )
        """
        params["branch_id"] = branch_id
    return bool(db.execute(text(f"""
        SELECT EXISTS (
            SELECT 1
            FROM user_roles ur
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            WHERE ur.clinic_id = :clinic_id
              AND ur.user_id = :user_id
              AND rp.permission_code = :permission_code
              {branch_clause}
        )
    """), params).scalar_one())


def require_permission(db: Session, user_id: UUID, clinic_id: UUID, permission_code: str, branch_id: UUID | None = None) -> None:
    if not has_permission(db, user_id, clinic_id, permission_code, branch_id):
        raise ForbiddenError()
