"""Subscribe, unsubscribe and the caller's subscriptions; D53."""

import asyncio

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Subscription, User
from tests.helpers import ApiUser, CreateUser


def _url(username: str) -> str:
    return f"/api/channels/{username}/subscription"


async def _subscribe(api: httpx.AsyncClient, user: ApiUser, channel: str) -> httpx.Response:
    return await api.put(_url(channel), headers=user.headers)


async def _unsubscribe(api: httpx.AsyncClient, user: ApiUser, channel: str) -> httpx.Response:
    return await api.delete(_url(channel), headers=user.headers)


async def _stored_count(session: AsyncSession, username: str) -> int:
    session.expire_all()
    return await session.scalar(select(User.subscribers_count).where(User.username == username))


async def _recount(session: AsyncSession, username: str) -> int:
    channel_id = select(User.id).where(User.username == username).scalar_subquery()
    return await session.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.channel_id == channel_id)
    )


async def test_subscribe_and_unsubscribe(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    await create_user("alice")
    bob = await create_user("bob")

    subscribed = await _subscribe(api, bob, "alice")
    assert subscribed.status_code == 200, subscribed.text
    assert subscribed.json() == {"is_subscribed": True, "subscribers_count": 1}
    channel = (await api.get("/api/channels/alice", headers=bob.headers)).json()
    assert (channel["is_subscribed"], channel["subscribers_count"]) == (True, 1)

    unsubscribed = await _unsubscribe(api, bob, "alice")
    assert unsubscribed.status_code == 200, unsubscribed.text
    assert unsubscribed.json() == {"is_subscribed": False, "subscribers_count": 0}
    channel = (await api.get("/api/channels/alice", headers=bob.headers)).json()
    assert (channel["is_subscribed"], channel["subscribers_count"]) == (False, 0)


async def test_subscribing_twice_counts_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D53."""
    await create_user("alice")
    bob = await create_user("bob")

    await _subscribe(api, bob, "alice")
    again = await _subscribe(api, bob, "alice")

    assert again.status_code == 200
    assert again.json() == {"is_subscribed": True, "subscribers_count": 1}
    assert await _stored_count(session, "alice") == await _recount(session, "alice") == 1


async def test_unsubscribing_twice_counts_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_user("alice")
    bob, carol = await create_user("bob"), await create_user("carol")
    await _subscribe(api, bob, "alice")
    await _subscribe(api, carol, "alice")

    await _unsubscribe(api, bob, "alice")
    again = await _unsubscribe(api, bob, "alice")
    never = await _unsubscribe(api, (await create_user("dave")), "alice")

    assert again.json() == {"is_subscribed": False, "subscribers_count": 1}
    assert never.json() == {"is_subscribed": False, "subscribers_count": 1}
    assert await _stored_count(session, "alice") == await _recount(session, "alice") == 1


async def test_concurrent_subscribes_count_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_user("alice")
    bob = await create_user("bob")

    responses = await asyncio.gather(*(_subscribe(api, bob, "alice") for _ in range(5)))

    assert all(response.status_code == 200 for response in responses)
    assert await _stored_count(session, "alice") == await _recount(session, "alice") == 1


async def test_concurrent_unsubscribes_count_once(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_user("alice")
    bob, carol = await create_user("bob"), await create_user("carol")
    await _subscribe(api, bob, "alice")
    await _subscribe(api, carol, "alice")

    responses = await asyncio.gather(*(_unsubscribe(api, bob, "alice") for _ in range(5)))

    assert all(response.status_code == 200 for response in responses)
    assert await _stored_count(session, "alice") == await _recount(session, "alice") == 1


async def test_mixed_concurrent_calls_keep_the_count_right(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_user("alice")
    bob = await create_user("bob")

    calls = [_subscribe, _unsubscribe] * 5
    await asyncio.gather(*(call(api, bob, "alice") for call in calls))

    assert await _stored_count(session, "alice") == await _recount(session, "alice")
    assert await _recount(session, "alice") in (0, 1)


async def test_counts_many_subscribers(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_user("alice")
    fans = [await create_user(f"fan{i}") for i in range(4)]

    await asyncio.gather(*(_subscribe(api, fan, "alice") for fan in fans))
    await _unsubscribe(api, fans[0], "alice")

    assert await _stored_count(session, "alice") == await _recount(session, "alice") == 3


async def test_nobody_subscribes_to_themselves(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """D53."""
    alice = await create_user("alice")

    response = await _subscribe(api, alice, "alice")

    assert response.status_code == 403
    assert response.json()["detail"] == "You can't subscribe to your own channel"
    assert await _stored_count(session, "alice") == 0


@pytest.mark.parametrize("method", ["put", "delete"])
async def test_needs_sign_in(api: httpx.AsyncClient, create_user: CreateUser, method: str) -> None:
    await create_user("alice")

    response = await api.request(method, _url("alice"))

    assert response.status_code == 401


@pytest.mark.parametrize("method", ["put", "delete"])
async def test_unknown_channel_is_404(
    api: httpx.AsyncClient, create_user: CreateUser, method: str
) -> None:
    bob = await create_user("bob")

    response = await api.request(method, _url("nobody"), headers=bob.headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Channel not found"


async def test_subscribing_keeps_the_channels_updated_at(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    await create_user("alice")
    bob = await create_user("bob")
    before = await session.scalar(select(User.updated_at).where(User.username == "alice"))

    await _subscribe(api, bob, "alice")

    session.expire_all()
    assert await session.scalar(select(User.updated_at).where(User.username == "alice")) == before


async def test_my_subscriptions_newest_first(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    for name in ("alice", "carol", "dave"):
        await create_user(name)
    bob = await create_user("bob")
    for name in ("alice", "carol", "dave"):
        await _subscribe(api, bob, name)
    await _unsubscribe(api, bob, "carol")
    await _subscribe(api, await create_user("erin"), "carol")  # Someone else's.

    response = await api.get("/api/users/me/subscriptions", headers=bob.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["username"] for item in items] == ["dave", "alice"]
    assert set(items[0]) == {"username", "display_name", "subscribed_at"}


async def test_my_subscriptions_pages_cover_every_channel_once(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    names = [f"chan{i}" for i in range(5)]
    for name in names:
        await create_user(name)
    bob = await create_user("bob")
    for name in names:
        await _subscribe(api, bob, name)

    pages: list[list[str]] = []
    cursor = None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        body = (
            await api.get("/api/users/me/subscriptions", params=params, headers=bob.headers)
        ).json()
        pages.append([item["username"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert [len(page) for page in pages] == [2, 2, 1]
    assert [name for page in pages for name in page] == names[::-1]


async def test_my_subscriptions_needs_sign_in(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/users/me/subscriptions")).status_code == 401
