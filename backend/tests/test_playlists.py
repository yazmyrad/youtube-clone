"""Playlists: create, read, edit, delete, a channel's list, and D34."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Playlist, PlaylistItem, Video
from app.models.user import UserRole
from tests.helpers import NOT_LISTED, ApiUser, CreateUser, SetRole, create_ready_video

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _create(
    api: httpx.AsyncClient, owner: ApiUser, *, visibility: str = "public", title: str = "Mix"
) -> str:
    response = await api.post(
        "/api/playlists",
        headers=owner.headers,
        json={"title": title, "visibility": visibility},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _put_items(session: AsyncSession, playlist_id: str, video_ids: list[str]) -> None:
    """Directly, in this order: adding through the API is tested in test_playlist_items."""
    for position, video_id in enumerate(video_ids):
        session.add(
            PlaylistItem(
                playlist_id=uuid.UUID(playlist_id), video_id=uuid.UUID(video_id), position=position
            )
        )
    await session.commit()


def _item_ids(response: httpx.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def test_create_is_private_by_default(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice = await create_user("alice")

    response = await api.post(
        "/api/playlists", headers=alice.headers, json={"title": "  Watch later  "}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Watch later"
    assert body["visibility"] == "private"
    assert body["description"] == ""
    assert body["channel"] == {"username": "alice", "display_name": body["channel"]["display_name"]}
    assert (body["video_count"], body["thumbnail_url"], body["items"]) == (0, None, [])


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   "},
        {"title": "x" * 101},
        {"title": "Mix", "description": "x" * 1001},
        {"title": "Mix", "visibility": "secret"},
        {"title": "Mix", "owner_id": str(uuid.uuid4())},
    ],
)
async def test_create_validates(
    api: httpx.AsyncClient, create_user: CreateUser, payload: dict[str, str]
) -> None:
    alice = await create_user("alice")

    response = await api.post("/api/playlists", headers=alice.headers, json=payload)

    assert response.status_code == 422


async def test_create_needs_sign_in(api: httpx.AsyncClient) -> None:
    assert (await api.post("/api/playlists", json={"title": "Mix"})).status_code == 401


@pytest.mark.parametrize("visibility", ["public", "unlisted"])
async def test_public_and_unlisted_open_for_anyone(
    api: httpx.AsyncClient, create_user: CreateUser, visibility: str
) -> None:
    playlist = await _create(api, await create_user("alice"), visibility=visibility)

    response = await api.get(f"/api/playlists/{playlist}")

    assert response.status_code == 200
    assert response.json()["visibility"] == visibility


@pytest.mark.parametrize("viewer", ["anonymous", "other user", "moderator", "admin"])
async def test_a_private_playlist_is_only_for_its_owner(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    set_role: SetRole,
    viewer: str,
) -> None:
    alice = await create_user("alice")
    playlist = await _create(api, alice, visibility="private")
    headers = {}
    if viewer != "anonymous":
        other = await create_user("bob")
        if viewer in ("moderator", "admin"):
            await set_role(other, UserRole(viewer))
        headers = other.headers

    response = await api.get(f"/api/playlists/{playlist}", headers=headers)
    own = await api.get(f"/api/playlists/{playlist}", headers=alice.headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Playlist not found"
    assert own.status_code == 200


async def test_unknown_playlist_is_404(api: httpx.AsyncClient) -> None:
    assert (await api.get(f"/api/playlists/{uuid.uuid4()}")).status_code == 404


async def test_items_in_playlist_order_with_count_and_thumbnail(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    a = await create_ready_video(api, session, bob, published_at=T0)
    b = await create_ready_video(api, session, alice, published_at=T0 + timedelta(days=1))
    playlist = await _create(api, alice)
    await _put_items(session, playlist, [a, b])

    response = await api.get(f"/api/playlists/{playlist}")

    assert _item_ids(response) == [a, b]
    body = response.json()
    assert body["video_count"] == 2
    assert body["thumbnail_url"] == body["items"][0]["thumbnail_url"]
    assert body["items"][0]["channel"]["username"] == "bob"


@pytest.mark.parametrize("state", NOT_LISTED)
@pytest.mark.parametrize("viewer", ["anonymous", "playlist owner", "moderator"])
async def test_a_playlist_reveals_no_video_the_viewer_cant_watch(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    state: str,
    viewer: str,
) -> None:
    """D34. Only unlisted videos may be watched by anyone with the link, so only they stay."""
    carol, alice = await create_user("carol"), await create_user("alice")
    listed = await create_ready_video(api, session, carol)
    other = await create_ready_video(api, session, carol, **NOT_LISTED[state])
    playlist = await _create(api, alice)
    await _put_items(session, playlist, [other, listed])
    headers = {}
    if viewer == "playlist owner":
        headers = alice.headers
    elif viewer == "moderator":
        mod = await create_user("mod")
        await set_role(mod, UserRole.moderator)
        headers = mod.headers

    response = await api.get(f"/api/playlists/{playlist}", headers=headers)
    page = await api.get("/api/channels/alice/playlists", headers=headers)

    shown = [other, listed] if state == "unlisted" else [listed]
    assert _item_ids(response) == shown
    assert response.json()["video_count"] == len(shown)
    if state != "unlisted":
        assert other not in response.text
    [summary] = page.json()["items"]
    assert summary["video_count"] == len(shown)
    assert other not in page.text or state == "unlisted"


async def test_shared_private_videos_show_only_to_those_they_are_shared_with(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    carol, alice, bob = (
        await create_user("carol"),
        await create_user("alice"),
        await create_user("bob"),
    )
    secret = await create_ready_video(api, session, carol, visibility="private")
    granted = await api.put(f"/api/videos/{secret}/access/alice", headers=carol.headers)
    assert granted.status_code == 200, granted.text
    playlist = await _create(api, alice)
    await _put_items(session, playlist, [secret])

    for user, expected in ((alice, [secret]), (carol, [secret]), (bob, [])):
        response = await api.get(f"/api/playlists/{playlist}", headers=user.headers)
        assert _item_ids(response) == expected, user.username

    await api.delete(f"/api/videos/{secret}/access/alice", headers=carol.headers)
    assert _item_ids(await api.get(f"/api/playlists/{playlist}", headers=alice.headers)) == []


async def test_an_empty_or_fully_hidden_playlist_has_no_thumbnail(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    private = await create_ready_video(api, session, alice, visibility="private")
    playlist = await _create(api, alice)
    await _put_items(session, playlist, [private])

    body = (await api.get(f"/api/playlists/{playlist}")).json()

    assert (body["video_count"], body["thumbnail_url"]) == (0, None)


async def test_owner_edits(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    alice = await create_user("alice")
    playlist = await _create(api, alice)

    response = await api.patch(
        f"/api/playlists/{playlist}",
        headers=alice.headers,
        json={"title": "Rust", "description": "All about Rust", "visibility": "unlisted"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["description"], body["visibility"]) == (
        "Rust",
        "All about Rust",
        "unlisted",
    )
    assert body["updated_at"] > body["created_at"]


async def test_edit_needs_a_field(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    alice = await create_user("alice")
    playlist = await _create(api, alice)

    response = await api.patch(f"/api/playlists/{playlist}", headers=alice.headers, json={})

    assert response.status_code == 422


@pytest.mark.parametrize("role", [UserRole.user, UserRole.moderator, UserRole.admin])
async def test_only_the_owner_edits_or_deletes(
    api: httpx.AsyncClient,
    session: AsyncSession,
    create_user: CreateUser,
    set_role: SetRole,
    role: UserRole,
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await set_role(bob, role)
    playlist = await _create(api, alice)

    edit = await api.patch(
        f"/api/playlists/{playlist}", headers=bob.headers, json={"title": "Mine now"}
    )
    delete = await api.delete(f"/api/playlists/{playlist}", headers=bob.headers)

    assert (edit.status_code, delete.status_code) == (404, 404)
    assert (
        await session.scalar(select(Playlist.title).where(Playlist.id == uuid.UUID(playlist)))
        == "Mix"
    )


async def test_delete_keeps_the_videos(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice)
    playlist = await _create(api, alice)
    await _put_items(session, playlist, [video])

    response = await api.delete(f"/api/playlists/{playlist}", headers=alice.headers)

    assert response.status_code == 204
    assert (await api.get(f"/api/playlists/{playlist}")).status_code == 404
    assert (await api.get(f"/api/videos/{video}")).status_code == 200
    assert await session.scalar(select(func.count()).select_from(PlaylistItem)) == 0


@pytest.mark.parametrize("method", ["patch", "delete"])
async def test_edit_and_delete_need_sign_in(
    api: httpx.AsyncClient, create_user: CreateUser, method: str
) -> None:
    playlist = await _create(api, await create_user("alice"))

    response = await api.request(method, f"/api/playlists/{playlist}", json={"title": "X"})

    assert response.status_code == 401


async def test_channel_lists_public_playlists_to_others_and_all_to_the_owner(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    public = await _create(api, alice, visibility="public")
    unlisted = await _create(api, alice, visibility="unlisted")
    private = await _create(api, alice, visibility="private")
    await _create(api, bob, visibility="public")

    others = await api.get("/api/channels/alice/playlists", headers=bob.headers)
    anonymous = await api.get("/api/channels/alice/playlists")
    own = await api.get("/api/channels/alice/playlists", headers=alice.headers)

    assert _item_ids(others) == _item_ids(anonymous) == [public]
    assert _item_ids(own) == [private, unlisted, public]


async def test_channel_playlists_pages_cover_every_playlist_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    made = [await _create(api, alice, title=f"List {i}") for i in range(5)]
    for i, playlist in enumerate(made):
        await session.execute(
            update(Playlist)
            .where(Playlist.id == uuid.UUID(playlist))
            .values(created_at=T0 + timedelta(minutes=i))
        )
    await session.commit()

    seen: list[str] = []
    sizes = []
    cursor = None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        body = (await api.get("/api/channels/alice/playlists", params=params)).json()
        seen += [item["id"] for item in body["items"]]
        sizes.append(len(body["items"]))
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert sizes == [2, 2, 1]
    assert seen == made[::-1]


async def test_unknown_channel_playlists_is_404(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/channels/nobody/playlists")).status_code == 404


async def test_a_deleted_video_drops_out_of_the_playlist(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    video = await create_ready_video(api, session, alice)
    playlist = await _create(api, alice)
    await _put_items(session, playlist, [video])

    await api.delete(f"/api/videos/{video}", headers=alice.headers)

    assert _item_ids(await api.get(f"/api/playlists/{playlist}", headers=alice.headers)) == []
    still_there = await session.scalar(select(func.count()).select_from(Video))
    assert still_there == 1  # Soft-deleted until the worker removes it.
