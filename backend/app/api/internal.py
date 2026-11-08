"""Routes for nginx only; see the `/internal/` note in main.py."""

from typing import Annotated

from fastapi import APIRouter, Header, status

from app.services import playback as playback_service

router = APIRouter(prefix="/internal", include_in_schema=False)

# Plain strings with defaults: a missing value has to be a 403, because auth_request turns
# anything but 2xx, 401 and 403 into a 500. In headers, so tokens stay out of access logs.
ScopeHeader = Annotated[str, Header(alias="X-Media-Scope")]
IdHeader = Annotated[str, Header(alias="X-Media-Id")]
ExpHeader = Annotated[str, Header(alias="X-Media-Exp")]
SigHeader = Annotated[str, Header(alias="X-Media-Sig")]


@router.get("/playback-auth", status_code=status.HTTP_204_NO_CONTENT)
async def playback_auth(
    scope: ScopeHeader = "", video_id: IdHeader = "", exp: ExpHeader = "", sig: SigHeader = ""
) -> None:
    playback_service.authorize_media(scope, video_id, exp, sig)
