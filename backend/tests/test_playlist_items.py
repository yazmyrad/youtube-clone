"""Adding, removing and reordering playlist items."""

import asyncio
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlaylistItem
from app.models.user import UserRole
from app.services import playlists
from tests.helpers import NOT_LISTED, ApiUser, CreateUser, SetRole, create_ready_video


async def _create(api: httpx.AsyncClient, owner: ApiUser, visibility: str = "public") -> str:
    response = await api.post(
        "/api/playlists", headers=owner.headers, json={"title": "Mix", "visibility": visibility}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _add(api: httpx.AsyncClient, user: ApiUser, playlist: str, video: str) -> httpx.Response:
    return await api.post(
        f"/api/playlists/{playlist}/items", headers=user.headers, json={"video_id": video}
    )


def _ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def _positions(session: AsyncSession, playlist: str) -> list[tuple[str, int]]:
    rows = await session.execute(
        select(PlaylistItem.video_id, PlaylistItem.position)
        .where(PlaylistItem.playlist_id == uuid.UUID(playlist))
        .order_by(PlaylistItem.position)
    )
    return [(str(video_id), position) for video_id, position in rows]


async def _videos(
    api: httpx.AsyncClient, session: AsyncSession, owner: ApiUser, count: int
) -> list[str]:
    return [await create_ready_video(api, session, owner) for _ in range(count)]


async def test_adds_to_the_end(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    a, b = await _videos(api, session, alice, 2)
    playlist = await _create(api, alice)

    await _add(api, alice, playlist, a)
    response = await _add(api, alice, playlist, b)

    assert _ids(response) == [a, b]
    assert response.json()["video_count"] == 2
    assert await _positions(session, playlist) == [(a, 0), (b, 1)]


async def test_adding_twice_keeps_one_in_place(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    a, b = await _videos(api, session, alice, 2)
    playlist = await _create(api, alice)
    await _add(api, alice, playlist, a)
    await _add(api, alice, playlist, b)

    response = await _add(api, alice, playlist, a)

    assert _ids(response) == [a, b]


async def test_concurrent_adds_get_distinct_positions(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    videos = await _videos(api, session, alice, 5)
    playlist = await _create(api, alice)

    responses = await asyncio.gather(*(_add(api, alice, playlist, v) for v in videos))

    assert all(response.status_code == 200 for response in responses)
    assert [position for _, position in await _positions(session, playlist)] == [0, 1, 2, 3, 4]


async def test_any_watchable_video_can_be_added(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    carol, alice = await create_user("carol"), await create_user("alice")
    theirs = await create_ready_video(api, session, carol)
    unlisted = await create_ready_video(api, session, carol, visibility="unlisted")
    playlist = await _create(api, alice)

    await _add(api, alice, playlist, theirs)
    response = await _add(api, alice, playlist, unlisted)

    assert _ids(response) == [theirs, unlisted]


@pytest.mark.parametrize("state", ["private", "processing", "deleted"])
async def test_a_video_you_cant_watch_cant_be_added(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    """D34: and the answer is the same as for no video at all."""
    carol, alice = await create_user("carol"), await create_user("alice")
    video = await create_ready_video(api, session, carol, **NOT_LISTED[state])
    playlist = await _create(api, alice)

    response = await _add(api, alice, playlist, video)
    missing = await _add(api, alice, playlist, str(uuid.uuid4()))

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json() == {"detail": "Video not found"}
    assert await _positions(session, playlist) == []


async def test_a_shared_private_video_can_be_added(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    carol, alice = await create_user("carol"), await create_user("alice")
    secret = await create_ready_video(api, session, carol, visibility="private")
    await api.put(f"/api/videos/{secret}/access/alice", headers=carol.headers)
    playlist = await _create(api, alice)

    assert _ids(await _add(api, alice, playlist, secret)) == [secret]


@pytest.mark.parametrize("role", [UserRole.user, UserRole.moderator, UserRole.admin])
async def test_only_the_owner_changes_items(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    role: UserRole,
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await set_role(bob, role)
    [video] = await _videos(api, session, alice, 1)
    playlist = await _create(api, alice)
    await _add(api, alice, playlist, video)
    url = f"/api/playlists/{playlist}/items"

    added = await _add(api, bob, playlist, video)
    removed = await api.delete(f"{url}/{video}", headers=bob.headers)
    ordered = await api.put(f"{url}/order", headers=bob.headers, json={"video_ids": [video]})

    assert (added.status_code, removed.status_code, ordered.status_code) == (404, 404, 404)
    assert await _positions(session, playlist) == [(video, 0)]


async def test_removing_closes_the_gap(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    a, b, c = await _videos(api, session, alice, 3)
    playlist = await _create(api, alice)
    for video in (a, b, c):
        await _add(api, alice, playlist, video)

    response = await api.delete(f"/api/playlists/{playlist}/items/{b}", headers=alice.headers)
    again = await api.delete(f"/api/playlists/{playlist}/items/{b}", headers=alice.headers)

    assert _ids(response) == _ids(again) == [a, c]
    assert await _positions(session, playlist) == [(a, 0), (c, 1)]
    added = await _add(api, alice, playlist, b)
    assert _ids(added) == [a, c, b]


async def test_reorder(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    a, b, c = await _videos(api, session, alice, 3)
    playlist = await _create(api, alice)
    for video in (a, b, c):
        await _add(api, alice, playlist, video)

    response = await api.put(
        f"/api/playlists/{playlist}/items/order",
        headers=alice.headers,
        json={"video_ids": [c, a, b]},
    )

    assert _ids(response) == [c, a, b]
    assert await _positions(session, playlist) == [(c, 0), (a, 1), (b, 2)]


@pytest.mark.parametrize("order", ["missing", "extra", "duplicate"])
async def test_reorder_must_name_exactly_the_items(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, order: str
) -> None:
    alice = await create_user("alice")
    a, b, other = await _videos(api, session, alice, 3)
    playlist = await _create(api, alice)
    await _add(api, alice, playlist, a)
    await _add(api, alice, playlist, b)
    video_ids = {"missing": [b], "extra": [b, a, other], "duplicate": [b, a, a]}[order]

    response = await api.put(
        f"/api/playlists/{playlist}/items/order",
        headers=alice.headers,
        json={"video_ids": video_ids},
    )

    assert response.status_code == 409
    assert await _positions(session, playlist) == [(a, 0), (b, 1)]


async def test_reorder_keeps_videos_the_owner_no_longer_sees_at_the_end(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    carol, alice = await create_user("carol"), await create_user("alice")
    secret = await create_ready_video(api, session, carol, visibility="private")
    await api.put(f"/api/videos/{secret}/access/alice", headers=carol.headers)
    a, b = await _videos(api, session, alice, 2)
    playlist = await _create(api, alice)
    for video in (a, secret, b):
        await _add(api, alice, playlist, video)
    await api.delete(f"/api/videos/{secret}/access/alice", headers=carol.headers)

    response = await api.put(
        f"/api/playlists/{playlist}/items/order",
        headers=alice.headers,
        json={"video_ids": [b, a]},
    )

    assert _ids(response) == [b, a]
    assert await _positions(session, playlist) == [(b, 0), (a, 1), (secret, 2)]


async def test_a_playlist_has_a_limit(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(playlists, "MAX_PLAYLIST_ITEMS", 2)
    alice = await create_user("alice")
    a, b, c = await _videos(api, session, alice, 3)
    playlist = await _create(api, alice)
    await _add(api, alice, playlist, a)
    await _add(api, alice, playlist, b)

    response = await _add(api, alice, playlist, c)
    again = await _add(api, alice, playlist, a)

    assert response.status_code == 409
    assert again.status_code == 200


async def test_item_changes_update_the_playlist(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    [video] = await _videos(api, session, alice, 1)
    playlist = await _create(api, alice)
    before = (await api.get(f"/api/playlists/{playlist}")).json()["updated_at"]

    after = (await _add(api, alice, playlist, video)).json()["updated_at"]

    assert after > before


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "", {"video_id": str(uuid.uuid4())}),
        ("delete", f"/{uuid.uuid4()}", None),
        ("put", "/order", {"video_ids": []}),
    ],
)
async def test_items_need_sign_in(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    playlist = await _create(api, await create_user("alice"))

    response = await api.request(method, f"/api/playlists/{playlist}/items{path}", json=body)

    assert response.status_code == 401


async def test_my_playlists_say_which_hold_the_video(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    [video] = await _videos(api, session, alice, 1)
    holding = await _create(api, alice, visibility="private")
    other = await _create(api, alice)
    await _create(api, bob)
    await _add(api, alice, holding, video)

    response = await api.get(
        "/api/users/me/playlists", headers=alice.headers, params={"video_id": video}
    )
    without = await api.get("/api/users/me/playlists", headers=alice.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(item["id"], item["contains_video"]) for item in items] == [
        (other, False),
        (holding, True),
    ]
    assert [item["contains_video"] for item in without.json()["items"]] == [False, False]


async def test_my_playlists_need_sign_in(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/users/me/playlists")).status_code == 401


@pytest.mark.parametrize("state", ["processing", "hidden"])
async def test_your_own_unplayable_video_cant_be_added(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser, state: str
) -> None:
    """It would take a slot and never show."""
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice, **NOT_LISTED[state])
    playlist = await _create(api, alice)

    response = await _add(api, alice, playlist, video)

    assert response.status_code == {"processing": 409, "hidden": 404}[state]
    assert await _positions(session, playlist) == []


async def test_a_moderator_cant_add_a_hidden_video(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
) -> None:
    carol, mod = await create_user("carol"), await create_user("mod")
    await set_role(mod, UserRole.moderator)
    video = await create_ready_video(api, session, carol, **NOT_LISTED["hidden"])
    playlist = await _create(api, mod)

    assert (await _add(api, mod, playlist, video)).status_code == 404
