from fastapi import APIRouter, status

from app.core.permissions import CurrentUser, SessionDep
from app.schemas.errors import ErrorOut
from app.schemas.users import MeOut, MeUpdateIn
from app.services import users as users_service

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorOut}},
)


@router.get("/me", response_model=MeOut, summary="Current user")
async def get_me(user: CurrentUser) -> MeOut:
    return MeOut.model_validate(user)


@router.patch("/me", response_model=MeOut, summary="Edit display name and description")
async def update_me(data: MeUpdateIn, user: CurrentUser, session: SessionDep) -> MeOut:
    return MeOut.model_validate(await users_service.update_me(session, user, data))
