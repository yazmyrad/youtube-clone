import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole


def _user(username: str, email: str) -> User:
    return User(username=username, email=email, password_hash="x", display_name=username)


async def test_defaults(session: AsyncSession) -> None:
    user = _user("alice", "alice@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    assert user.role is UserRole.user
    assert user.is_active is True
    assert user.description == ""
    assert user.subscribers_count == 0


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (("alice", "a@example.com"), ("ALICE", "b@example.com")),
        (("alice", "a@example.com"), ("bob", "A@Example.com")),
    ],
)
async def test_username_and_email_are_unique_ignoring_case(
    session: AsyncSession, first: tuple[str, str], second: tuple[str, str]
) -> None:
    session.add(_user(*first))
    await session.commit()
    session.add(_user(*second))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.parametrize("username", ["ab", "a" * 31, "bad name", "émile", "a/b"])
async def test_database_rejects_invalid_usernames(session: AsyncSession, username: str) -> None:
    session.add(_user(username, "x@example.com"))
    with pytest.raises(IntegrityError, match="ck_users_username_format"):
        await session.commit()
