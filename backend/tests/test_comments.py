"""Comments on videos: who may read, write and delete them, and D57 for the API."""

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment, UserRole, Video, VideoStatus, VideoVisibility
from tests.helpers import ApiUser, CreateUser, SetRole, collect_pages, create_ready_video

XSS = "<script>alert('x')</script>"
HIDDEN: dict[str, Any] = {"hidden_at": datetime(2026, 1, 1, tzinfo=UTC)}
PROCESSING: dict[str, Any] = {"status": VideoStatus.processing, "published_at": None}


def _url(video_id: str) -> str:
    return f"/api/videos/{video_id}/comments"


async def _post(
    api: httpx.AsyncClient, video_id: str, user: ApiUser, body: str = "Nice"
) -> httpx.Response:
    return await api.post(_url(video_id), headers=user.headers, json={"body": body})


async def _comment(api: httpx.AsyncClient, video_id: str, user: ApiUser) -> str:
    response = await _post(api, video_id, user)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _delete(api: httpx.AsyncClient, comment_id: str, user: ApiUser) -> httpx.Response:
    return await api.delete(f"/api/comments/{comment_id}", headers=user.headers)


async def _comments_count(api: httpx.AsyncClient, video_id: str) -> int:
    return (await api.get(f"/api/videos/{video_id}")).json()["comments_count"]


async def _staff(create_user: CreateUser, set_role: SetRole, role: str) -> ApiUser:
    user = await create_user("staff")
    await set_role(user, UserRole(role))
    return user


async def test_add_and_list(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())
    fan = await create_user("bobby")

    created = await _post(api, video_id, fan, "  First!  ")

    assert created.status_code == 201, created.text
    comment = created.json()
    assert comment["body"] == "First!"
    assert comment["author"] == {"username": "bobby", "display_name": "Bobby"}
    assert set(comment) == {"id", "body", "created_at", "author"}
    listed = (await api.get(_url(video_id))).json()
    assert listed == {"items": [comment], "next_cursor": None}
    assert await _comments_count(api, video_id) == 1


async def test_list_is_newest_first_and_pages_cleanly(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    ids = [await _comment(api, video_id, owner) for _ in range(5)]

    pages = await collect_pages(api, _url(video_id), limit=2)

    assert [len(page) for page in pages] == [2, 2, 1]
    assert [comment_id for page in pages for comment_id in page] == ids[::-1]


async def test_comments_sharing_a_timestamp_page_cleanly(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    ids = {await _comment(api, video_id, owner) for _ in range(5)}
    await session.execute(update(Comment).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    await session.commit()

    pages = await collect_pages(api, _url(video_id), limit=2)

    walked = [comment_id for page in pages for comment_id in page]
    assert len(walked) == 5
    assert set(walked) == ids


async def test_comments_stay_on_their_own_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    other_id = await create_ready_video(api, session, owner)
    await _comment(api, other_id, owner)

    assert (await api.get(_url(video_id))).json()["items"] == []


@pytest.mark.parametrize(
    "body", ["", "   ", "x" * 2001, "bad\x00byte"], ids=["empty", "blank", "too-long", "nul"]
)
async def test_bad_bodies_are_rejected(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, body: str
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)

    assert (await _post(api, video_id, owner, body)).status_code == 422
    assert await _comments_count(api, video_id) == 0


async def test_longest_body_is_accepted(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)

    assert (await _post(api, video_id, owner, "x" * 2000)).status_code == 201


async def test_markup_comes_back_as_plain_text(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D57, API half: nothing is stripped or encoded, the SPA renders it as text."""
    owner = await create_user()
    created = await api.post("/api/videos", headers=owner.headers, json={"title": XSS})
    assert created.status_code == 201, created.text
    assert created.json()["video"]["title"] == XSS
    video_id = await create_ready_video(api, session, owner)

    await _post(api, video_id, owner, XSS)

    assert (await api.get(_url(video_id))).json()["items"][0]["body"] == XSS


async def test_stranger_cant_read_or_write_on_a_private_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    stranger = await create_user("bobby")
    video_id = await create_ready_video(api, session, owner, visibility=VideoVisibility.private)

    assert (await api.get(_url(video_id))).status_code == 404
    assert (await api.get(_url(video_id), headers=stranger.headers)).status_code == 404
    assert (await _post(api, video_id, stranger)).status_code == 404


async def test_allowlisted_user_comments_until_revoked(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    friend = await create_user("bobby")
    video_id = await create_ready_video(api, session, owner, visibility=VideoVisibility.private)
    access = f"/api/videos/{video_id}/access/{friend.username}"

    await api.put(access, headers=owner.headers)
    assert (await _post(api, video_id, friend)).status_code == 201

    await api.delete(access, headers=owner.headers)
    assert (await _post(api, video_id, friend)).status_code == 404
    assert (await api.get(_url(video_id), headers=friend.headers)).status_code == 404


@pytest.mark.parametrize("role", ["moderator", "admin"])
async def test_hidden_video_comments_can_be_read_but_not_added_by_staff(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    role: str,
) -> None:
    video_id = await create_ready_video(api, session, await create_user("owner"), **HIDDEN)
    staff = await _staff(create_user, set_role, role)

    assert (await api.get(_url(video_id), headers=staff.headers)).status_code == 200
    assert (await _post(api, video_id, staff)).status_code == 404


async def test_hidden_video_comments_can_be_read_but_not_added_by_the_owner(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner, **HIDDEN)

    assert (await api.get(_url(video_id), headers=owner.headers)).status_code == 200
    assert (await _post(api, video_id, owner)).status_code == 404


async def test_hidden_video_comments_are_gone_for_everyone_else(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user(), **HIDDEN)

    assert (await api.get(_url(video_id))).status_code == 404


async def test_owner_cant_comment_before_the_video_is_ready(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner, **PROCESSING)

    assert (await _post(api, video_id, owner)).status_code == 409


async def test_commenting_on_a_missing_video_is_404(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    missing = str(uuid.uuid4())

    assert (await api.get(_url(missing))).status_code == 404
    assert (await _post(api, missing, await create_user())).status_code == 404


async def test_bad_cursor_is_rejected(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video_id = await create_ready_video(api, session, await create_user())

    assert (await api.get(_url(video_id), params={"cursor": "nonsense"})).status_code == 422


@pytest.mark.parametrize("deleter", ["author", "video owner", "moderator", "admin"])
async def test_who_may_delete_a_comment(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    deleter: str,
) -> None:
    owner = await create_user("owner")
    author = await create_user("author")
    video_id = await create_ready_video(api, session, owner)
    comment_id = await _comment(api, video_id, author)
    caller = {"author": author, "video owner": owner}.get(deleter)
    if caller is None:
        caller = await _staff(create_user, set_role, deleter)

    response = await _delete(api, comment_id, caller)

    assert response.status_code == 204, response.text
    assert await _comments_count(api, video_id) == 0
    assert (await api.get(_url(video_id))).json()["items"] == []


async def test_another_user_cant_delete_a_comment(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    comment_id = await _comment(api, video_id, owner)

    response = await _delete(api, comment_id, await create_user("bobby"))

    assert response.status_code == 403
    assert await _comments_count(api, video_id) == 1


async def test_a_stranger_cant_tell_a_private_videos_comment_exists(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    stranger = await create_user("bobby")
    video_id = await create_ready_video(api, session, owner, visibility=VideoVisibility.private)
    comment_id = await _comment(api, video_id, owner)

    response = await _delete(api, comment_id, stranger)
    missing = await _delete(api, str(uuid.uuid4()), stranger)

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()


async def test_deleting_twice_counts_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    first = await _comment(api, video_id, owner)
    await _comment(api, video_id, owner)

    assert (await _delete(api, first, owner)).status_code == 204
    assert (await _delete(api, first, owner)).status_code == 404
    assert await _comments_count(api, video_id) == 1


async def test_a_comment_can_be_cleaned_up_on_a_hidden_video(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
) -> None:
    owner = await create_user("owner")
    video_id = await create_ready_video(api, session, owner)
    comment_id = await _comment(api, video_id, owner)
    await session.execute(update(Video).values(hidden_at=datetime.now(UTC)))
    await session.commit()

    response = await _delete(api, comment_id, await _staff(create_user, set_role, "moderator"))

    assert response.status_code == 204, response.text


async def test_a_deleted_videos_comments_are_gone_even_for_the_author(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    owner = await create_user()
    video_id = await create_ready_video(api, session, owner)
    comment_id = await _comment(api, video_id, owner)
    await session.execute(update(Video).values(deleted_at=datetime.now(UTC)))
    await session.commit()

    assert (await _delete(api, comment_id, owner)).status_code == 404
    assert (await api.get(_url(video_id), headers=owner.headers)).status_code == 404
