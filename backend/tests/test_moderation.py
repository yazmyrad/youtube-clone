"""The report queue, resolving and dismissing, hiding and restoring (D35, D46, D55)."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModerationAction, ModerationActionType, Report, ReportStatus, Video
from app.models.user import UserRole
from tests.helpers import ApiUser, CreateUser, SetRole, create_ready_video

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
async def mod(create_user: CreateUser, set_role: SetRole) -> ApiUser:
    user = await create_user("mod")
    await set_role(user, UserRole.moderator)
    return user


async def _report(
    api: httpx.AsyncClient, user: ApiUser, video_id: str, reason: str = "spam"
) -> str:
    response = await api.post(
        f"/api/videos/{video_id}/reports",
        headers=user.headers,
        json={"reason": reason, "details": f"from {user.username}"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _audit(session: AsyncSession) -> list[tuple[ModerationActionType, str | None]]:
    rows = await session.execute(
        select(ModerationAction.action, ModerationAction.report_id).order_by(ModerationAction.id)
    )
    return [(action, str(report) if report else None) for action, report in rows]


async def _statuses(session: AsyncSession, video_id: str) -> list[ReportStatus]:
    session.expire_all()
    return list(
        await session.scalars(
            select(Report.status)
            .where(Report.video_id == uuid.UUID(video_id))
            .order_by(Report.created_at)
        )
    )


async def _queue(api: httpx.AsyncClient, mod: ApiUser, **params: object) -> dict:
    response = await api.get("/api/moderation/reports", headers=mod.headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_queue_groups_open_reports_by_video_oldest_first(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    alice, bob, carol = (
        await create_user("alice"),
        await create_user("bob"),
        await create_user("carol"),
    )
    newer = await create_ready_video(api, session, alice)
    older = await create_ready_video(api, session, alice)
    calm = await create_ready_video(api, session, alice)
    await _report(api, bob, older, "spam")
    await _report(api, carol, older, "spam")
    await _report(api, bob, newer, "violence")
    await _report(api, carol, calm)
    await session.execute(
        update(Report).where(Report.video_id == uuid.UUID(older)).values(created_at=T0)
    )
    await session.execute(
        update(Report)
        .where(Report.video_id == uuid.UUID(calm))
        .values(status=ReportStatus.dismissed)
    )
    await session.commit()

    items = (await _queue(api, mod))["items"]

    assert [item["video"]["id"] for item in items] == [older, newer]
    first = items[0]
    assert first["open_reports"] == 2
    assert first["reasons"] == {"spam": 2}
    assert first["video"]["channel"]["username"] == "alice"
    assert {report["reporter"]["username"] for report in first["reports"]} == {"bob", "carol"}
    assert first["thumbnail_url"].startswith("/thumbs/")


async def test_the_queue_pages_cover_every_video_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    videos = [await create_ready_video(api, session, alice) for _ in range(5)]
    for i, video in enumerate(videos):
        await _report(api, bob, video)
        await session.execute(
            update(Report)
            .where(Report.video_id == uuid.UUID(video))
            .values(created_at=T0 + timedelta(minutes=i))
        )
    await session.commit()

    seen: list[str] = []
    sizes = []
    cursor = None
    while True:
        body = await _queue(api, mod, limit=2, **({"cursor": cursor} if cursor else {}))
        seen += [item["video"]["id"] for item in body["items"]]
        sizes.append(len(body["items"]))
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert sizes == [2, 2, 1]
    assert seen == videos


@pytest.mark.parametrize(
    ("decision", "status"), [("resolve", "resolved"), ("dismiss", "dismissed")]
)
async def test_a_decision_closes_the_videos_open_reports_with_audit_rows(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    mod: ApiUser,
    decision: str,
    status: str,
) -> None:
    alice, bob, carol = (
        await create_user("alice"),
        await create_user("bob"),
        await create_user("carol"),
    )
    video = await create_ready_video(api, session, alice)
    first = await _report(api, bob, video)
    second = await _report(api, carol, video)

    response = await api.post(
        f"/api/moderation/reports/{first}/{decision}",
        headers=mod.headers,
        json={"reason": "Checked"},
    )
    again = await api.post(
        f"/api/moderation/reports/{second}/{decision}", headers=mod.headers, json={}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"reports_closed": 2}
    assert again.status_code == 409
    assert await _statuses(session, video) == [ReportStatus(status)] * 2
    action = ModerationActionType(f"{decision}_report")
    assert sorted(await _audit(session)) == sorted([(action, first), (action, second)])
    assert (await _queue(api, mod))["items"] == []
    # The video stays as it was.
    assert (await api.get(f"/api/videos/{video}")).status_code == 200


async def test_an_unknown_report_is_404(api: httpx.AsyncClient, mod: ApiUser) -> None:
    response = await api.post(
        f"/api/moderation/reports/{uuid.uuid4()}/resolve", headers=mod.headers, json={}
    )

    assert response.status_code == 404


async def test_report_hide_restore(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    """D55: report, hide, gone from the feed; restore, back in the feed; all audited."""
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)
    report = await _report(api, bob, video)

    def in_feed(body: dict) -> bool:
        return video in [item["id"] for item in body["items"]]

    hidden = await api.post(
        f"/api/moderation/videos/{video}/hide",
        headers=mod.headers,
        json={"reason": "Spam links in the description"},
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json() == {"reports_closed": 1}
    assert not in_feed((await api.get("/api/videos")).json())
    assert not in_feed((await api.get("/api/channels/alice/videos")).json())
    assert (await api.get(f"/api/videos/{video}", headers=bob.headers)).status_code == 404
    owner_view = (await api.get(f"/api/videos/{video}", headers=alice.headers)).json()
    assert owner_view["hidden_reason"] == "Spam links in the description"
    assert owner_view["hidden_at"] is not None
    assert await _statuses(session, video) == [ReportStatus.resolved]

    restored = await api.post(
        f"/api/moderation/videos/{video}/restore", headers=mod.headers, json={}
    )

    assert restored.status_code == 204
    assert in_feed((await api.get("/api/videos")).json())
    owner_view = (await api.get(f"/api/videos/{video}", headers=alice.headers)).json()
    assert (owner_view["hidden_at"], owner_view["hidden_reason"]) == (None, None)
    assert await _audit(session) == [
        (ModerationActionType.hide_video, None),
        (ModerationActionType.resolve_report, report),
        (ModerationActionType.restore_video, None),
    ]
    targets = set(await session.scalars(select(ModerationAction.target_video_id)))
    assert targets == {uuid.UUID(video)}


async def test_hiding_stops_playback_at_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    """D46, in the API: no new playback grant, for anyone, the owner included."""
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)
    assert (await api.post(f"/api/videos/{video}/playback")).status_code == 200

    await api.post(
        f"/api/moderation/videos/{video}/hide", headers=mod.headers, json={"reason": "Bad"}
    )

    for user in (None, bob, alice, mod):
        headers = user.headers if user else {}
        response = await api.post(f"/api/videos/{video}/playback", headers=headers)
        assert response.status_code == 404, user


async def test_hiding_twice_or_restoring_a_visible_video_is_409(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))
    url = f"/api/moderation/videos/{video}"

    restore = await api.post(f"{url}/restore", headers=mod.headers, json={})
    await api.post(f"{url}/hide", headers=mod.headers, json={"reason": "Bad"})
    hide_again = await api.post(f"{url}/hide", headers=mod.headers, json={"reason": "Bad"})

    assert (restore.status_code, hide_again.status_code) == (409, 409)
    hides = await session.scalar(
        select(ModerationAction.id).where(
            ModerationAction.action == ModerationActionType.hide_video
        )
    )
    assert hides is not None


async def test_hiding_needs_a_reason(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    video = await create_ready_video(api, session, await create_user("alice"))

    response = await api.post(
        f"/api/moderation/videos/{video}/hide", headers=mod.headers, json={"reason": "   "}
    )

    assert response.status_code == 422


async def test_a_private_video_can_be_hidden_only_while_reported(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    """D35: without an open report, a moderator can't even find a private video."""
    alice, friend = await create_user("alice"), await create_user("friend")
    video = await create_ready_video(api, session, alice, visibility="private")
    await api.put(f"/api/videos/{video}/access/friend", headers=alice.headers)
    url = f"/api/moderation/videos/{video}/hide"

    unreported = await api.post(url, headers=mod.headers, json={"reason": "Bad"})
    await _report(api, friend, video)
    reported = await api.post(url, headers=mod.headers, json={"reason": "Bad"})

    assert (unreported.status_code, reported.status_code) == (404, 200)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/moderation/reports"),
        ("post", f"/api/moderation/reports/{uuid.uuid4()}/resolve"),
        ("post", f"/api/moderation/reports/{uuid.uuid4()}/dismiss"),
        ("post", f"/api/moderation/videos/{uuid.uuid4()}/hide"),
        ("post", f"/api/moderation/videos/{uuid.uuid4()}/restore"),
    ],
)
async def test_only_moderators_and_admins(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    set_role: SetRole,
    method: str,
    path: str,
) -> None:
    user = await create_user("user")
    admin = await create_user("admin")
    await set_role(admin, UserRole.admin)
    body = {"reason": "x"} if method == "post" else None

    anonymous = await api.request(method, path, json=body)
    as_user = await api.request(method, path, headers=user.headers, json=body)
    as_admin = await api.request(method, path, headers=admin.headers, json=body)

    assert (anonymous.status_code, as_user.status_code) == (401, 403)
    assert as_admin.status_code in (200, 404)


async def test_a_deleted_video_leaves_the_queue(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, mod: ApiUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    video = await create_ready_video(api, session, alice)
    await _report(api, bob, video)

    await session.execute(
        update(Video).where(Video.id == uuid.UUID(video)).values(deleted_at=datetime.now(UTC))
    )
    await session.commit()

    assert (await _queue(api, mod))["items"] == []
