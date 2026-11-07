from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.users import MeUpdateIn


async def update_me(session: AsyncSession, user: User, data: MeUpdateIn) -> User:
    # Only fields declared on MeUpdateIn can get here; the schema forbids anything else.
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return user
