import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.permissions import AdminUser, SessionDep
from app.models.user import USERNAME_PATTERN
from app.schemas.admin import AdminUserOut, AdminUserPage, AdminUserUpdateIn
from app.schemas.errors import ErrorOut
from app.services import admin as admin_service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut},
        status.HTTP_403_FORBIDDEN: {"model": ErrorOut},
    },
)


@router.get("/users", response_model=AdminUserPage, summary="List and search users")
async def list_users(
    _admin: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100, description="Part of username or email")] = None,
    cursor: Annotated[str | None, Query(pattern=USERNAME_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AdminUserPage:
    users, next_cursor = await admin_service.list_users(session, q=q, cursor=cursor, limit=limit)
    return AdminUserPage(
        items=[AdminUserOut.model_validate(user) for user in users], next_cursor=next_cursor
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    summary="Change a user's role, enable or disable them",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorOut}},
)
async def update_user(
    user_id: uuid.UUID, data: AdminUserUpdateIn, admin: AdminUser, session: SessionDep
) -> AdminUserOut:
    user = await admin_service.update_user(session, admin, user_id, data)
    return AdminUserOut.model_validate(user)
