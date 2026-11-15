"""Several accounts signed in at once in one browser, switchable as on YouTube."""

import uuid

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_refresh_token
from app.models import RefreshToken, User
from app.services.auth import MAX_ACCOUNTS
from tests.helpers import PASSWORD, ApiUser, CreateUser

ORIGIN = {"Origin": "http://test"}


def _name(user: ApiUser) -> str:
    return f"refresh_{uuid.UUID(user.id).hex}"


class Browser:
    """One browser's cookie jar, sent explicitly so each test says what the browser holds."""

    def __init__(self, api: httpx.AsyncClient) -> None:
        self.api = api
        self.jar: dict[str, str] = {}

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        cookie = "; ".join(f"{name}={value}" for name, value in self.jar.items())
        return ORIGIN | ({"Cookie": cookie} if cookie else {}) | (extra or {})

    def _keep(self, response: httpx.Response) -> None:
        for name, value in response.cookies.items():
            self.jar[name] = value
        for header in response.headers.get_list("set-cookie"):
            name = header.split("=", 1)[0]
            if "max-age=0" in header.lower():
                self.jar.pop(name, None)
        self.api.cookies.clear()

    async def login(self, user: ApiUser) -> httpx.Response:
        response = await self.api.post(
            "/api/auth/login",
            json={"email": user.email, "password": PASSWORD},
            headers=self._headers(),
        )
        self._keep(response)
        return response

    async def refresh(self, user: ApiUser | None = None) -> httpx.Response:
        body = {"json": {"user_id": user.id}} if user else {}
        response = await self.api.post("/api/auth/refresh", headers=self._headers(), **body)
        self._keep(response)
        return response

    async def accounts(self) -> list[str]:
        response = await self.api.get("/api/auth/accounts", headers=self._headers())
        assert response.status_code == 200, response.text
        self._keep(response)
        return [item["username"] for item in response.json()["items"]]

    async def logout(self, user: ApiUser | None = None) -> httpx.Response:
        body = {"json": {"user_id": user.id}} if user else {}
        response = await self.api.post("/api/auth/logout", headers=self._headers(), **body)
        self._keep(response)
        return response

    async def me(self, refreshed: httpx.Response) -> str:
        token = refreshed.json()["access_token"]
        response = await self.api.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        return response.json()["username"]


@pytest.fixture
def browser(api: httpx.AsyncClient) -> Browser:
    return Browser(api)


async def test_each_account_signed_in_has_its_own_cookie(
    browser: Browser, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")

    await browser.login(alice)
    await browser.login(bob)

    assert set(browser.jar) == {_name(alice), _name(bob)}
    assert await browser.accounts() == ["alice", "bob"]


async def test_the_switcher_shows_name_and_picture(
    browser: Browser, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    await browser.login(alice)

    response = await browser.api.get("/api/auth/accounts", headers=browser._headers())

    assert response.json()["items"] == [
        {"id": alice.id, "username": "alice", "display_name": "Alice", "avatar_url": None}
    ]


async def test_switching_refreshes_the_chosen_account(
    browser: Browser, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await browser.login(alice)
    await browser.login(bob)

    as_alice = await browser.refresh(alice)
    as_bob = await browser.refresh(bob)

    assert (as_alice.status_code, as_bob.status_code) == (200, 200)
    assert await browser.me(as_alice) == "alice"
    assert await browser.me(as_bob) == "bob"


async def test_with_several_accounts_refresh_must_say_which(
    browser: Browser, create_user: CreateUser
) -> None:
    await browser.login(await create_user("alice"))
    await browser.login(await create_user("bob"))

    response = await browser.refresh()

    assert response.status_code == 400


async def test_with_one_account_refresh_needs_no_choice(
    browser: Browser, create_user: CreateUser
) -> None:
    await browser.login(await create_user("alice"))

    response = await browser.refresh()

    assert await browser.me(response) == "alice"


async def test_a_cookie_cant_stand_in_for_another_account(
    browser: Browser, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await browser.login(bob)
    bobs_token = browser.jar.pop(_name(bob))
    browser.jar[_name(alice)] = bobs_token  # Renamed: it now claims to be alice's.

    response = await browser.refresh(alice)

    assert response.status_code == 401
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(bobs_token))
    )
    assert row is not None and row.revoked_at is None  # Refused, not rotated or revoked.


async def test_signing_out_of_one_account_keeps_the_others(
    browser: Browser, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    await browser.login(alice)
    await browser.login(bob)
    alices_token = browser.jar[_name(alice)]

    response = await browser.logout(alice)

    assert response.status_code == 204
    assert set(browser.jar) == {_name(bob)}
    assert await browser.accounts() == ["bob"]
    assert (await browser.refresh(bob)).status_code == 200
    browser.jar[_name(alice)] = alices_token  # Kept by an attacker: revoked all the same.
    assert (await browser.refresh(alice)).status_code == 401


async def test_signing_out_of_all_accounts(browser: Browser, create_user: CreateUser) -> None:
    await browser.login(await create_user("alice"))
    await browser.login(await create_user("bob"))

    response = await browser.logout()

    assert response.status_code == 204
    assert browser.jar == {}
    assert await browser.accounts() == []


async def test_at_most_five_accounts_in_one_browser(
    browser: Browser, create_user: CreateUser
) -> None:
    users = [await create_user(f"user{i}") for i in range(MAX_ACCOUNTS + 1)]
    for user in users[:MAX_ACCOUNTS]:
        assert (await browser.login(user)).status_code == 200

    one_more = await browser.login(users[-1])
    again = await browser.login(users[0])

    assert one_more.status_code == 409
    assert "Sign out of one" in one_more.json()["detail"]
    assert again.status_code == 200  # Signing in again to one already here is fine.
    assert len(browser.jar) == MAX_ACCOUNTS


async def test_the_switcher_drops_accounts_that_ended(
    browser: Browser, session: AsyncSession, create_user: CreateUser
) -> None:
    alice, bob, carol = [await create_user(n) for n in ("alice", "bob", "carol")]
    for user in (alice, bob, carol):
        await browser.login(user)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(browser.jar[_name(alice)]))
        .values(revoked_at=RefreshToken.created_at)
    )
    await session.execute(update(User).where(User.username == "bob").values(is_active=False))
    await session.commit()

    assert await browser.accounts() == ["carol"]
    assert set(browser.jar) == {_name(carol)}  # The dead cookies are cleared.


async def test_no_cookies_no_accounts(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/auth/accounts")

    assert response.json() == {"items": []}


async def test_the_old_single_cookie_moves_to_its_accounts_own(
    browser: Browser, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    await browser.login(alice)
    browser.jar["refresh_token"] = browser.jar.pop(_name(alice))  # As before this change.

    assert await browser.accounts() == ["alice"]
    response = await browser.refresh(alice)

    assert response.status_code == 200
    assert set(browser.jar) == {_name(alice)}


async def test_choosing_an_account_needs_same_origin(
    browser: Browser, create_user: CreateUser
) -> None:
    alice = await create_user("alice")
    await browser.login(alice)

    response = await browser.api.post(
        "/api/auth/refresh",
        json={"user_id": alice.id},
        headers=browser._headers({"Origin": "http://evil.example"}),
    )

    assert response.status_code == 403


async def test_refresh_refuses_other_fields(browser: Browser, create_user: CreateUser) -> None:
    alice = await create_user("alice")
    await browser.login(alice)

    response = await browser.api.post(
        "/api/auth/refresh",
        json={"user_id": alice.id, "role": "admin"},
        headers=browser._headers(),
    )

    assert response.status_code == 422
