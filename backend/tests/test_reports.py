"""Reporting a video (D56), and what an open report lets moderators see (D35)."""

import uuid

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Report, ReportStatus
from app.models.user import UserRole
from tests.helpers import NOT_LISTED, ApiUser, CreateUser, SetRole, create_ready_video


async def _report(
    api: httpx.AsyncClient, user: ApiUser, video_id: str, reason: str = "spam", **extra: str
) -> httpx.Response:
    return await api.post(
        f"/api/videos/{video_id}/reports",
        headers=user.headers,
        json={"reason": reason, **extra},
    )


async def _close_reports(session: AsyncSession, video_id: str, status: ReportStatus) -> None:
    await session.execute(
        update(Report).where(Report.video_id == uuid.UUID(video_id)).values(status=status)
    )
    await session.commit()


async def test_report_a_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)

    response = await _report(api, bob, video, "copyright", details="  My song  ")

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["video_id"], body["reason"], body["details"], body["status"]) == (
        video,
        "copyright",
        "My song",
        "open",
    )


async def test_one_open_report_per_user_and_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D56. Once it's closed, a new one may be filed."""
    alice, bob, carol = (
        await create_user("alice"),
        await create_user("bob"),
        await create_user("carol"),
    )
    video = await create_ready_video(api, session, alice)
    await _report(api, bob, video)

    again = await _report(api, bob, video, "violence")
    other = await _report(api, carol, video)
    await _close_reports(session, video, ReportStatus.dismissed)
    after = await _report(api, bob, video)

    assert again.status_code == 409
    assert again.json()["detail"] == "You've already reported this video"
    assert (other.status_code, after.status_code) == (201, 201)


async def test_the_owner_cant_report_their_own_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice)

    response = await _report(api, alice, video)

    assert response.status_code == 403


@pytest.mark.parametrize("state", ["private", "hidden", "processing", "deleted"])
async def test_a_video_you_cant_watch_cant_be_reported(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice, **NOT_LISTED[state])

    response = await _report(api, bob, video)

    assert response.status_code == 404


async def test_an_unlisted_video_can_be_reported(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice, visibility="unlisted")

    assert (await _report(api, bob, video)).status_code == 201


@pytest.mark.parametrize(
    "body",
    [{"reason": "boring"}, {"reason": "spam", "details": "x" * 1001}, {"details": "x"}],
)
async def test_validates_the_report(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    body: dict[str, str],
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)

    response = await api.post(f"/api/videos/{video}/reports", headers=bob.headers, json=body)

    assert response.status_code == 422


async def test_reporting_needs_sign_in(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))

    response = await api.post(f"/api/videos/{video}/reports", json={"reason": "spam"})

    assert response.status_code == 401


@pytest.mark.parametrize("role", [UserRole.moderator, UserRole.admin])
async def test_a_moderator_sees_a_private_video_only_while_it_has_an_open_report(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    role: UserRole,
) -> None:
    """D35."""
    alice, friend, mod, user = (
        await create_user("alice"),
        await create_user("friend"),
        await create_user("mod"),
        await create_user("user"),
    )
    await set_role(mod, role)
    video = await create_ready_video(api, session, alice, visibility="private")
    await api.put(f"/api/videos/{video}/access/friend", headers=alice.headers)
    url = f"/api/videos/{video}"

    before = await api.get(url, headers=mod.headers)
    assert (await _report(api, friend, video)).status_code == 201
    during = await api.get(url, headers=mod.headers)
    playback = await api.post(f"{url}/playback", headers=mod.headers)
    plain_user = await api.get(url, headers=user.headers)
    await _close_reports(session, video, ReportStatus.resolved)
    after = await api.get(url, headers=mod.headers)

    assert before.status_code == 404
    assert (during.status_code, playback.status_code) == (200, 200)
    assert plain_user.status_code == 404
    assert after.status_code == 404
