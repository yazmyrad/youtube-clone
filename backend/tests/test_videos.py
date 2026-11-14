import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import JobStatus, ProcessingJob, UserRole, Video, VideoStatus
from app.services import storage
from tests.conftest import TEST_BUCKET
from tests.helpers import ApiUser, CreateUser, SetRole


async def _create(api: httpx.AsyncClient, user: ApiUser, **fields: Any) -> httpx.Response:
    return await api.post("/api/videos", headers=user.headers, json={"title": "Clip", **fields})


async def _post_form(bucket_url: str, upload: dict[str, Any], content: bytes) -> httpx.Response:
    """What the browser does; here straight to storage, nginx has its own check."""
    async with httpx.AsyncClient() as http:
        return await http.post(bucket_url, data=upload["fields"], files={"file": content})


def _policy(upload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(base64.b64decode(upload["fields"]["policy"]))


async def test_create_returns_video_and_upload_form(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()

    response = await _create(api, user, description="Hi", visibility="unlisted")

    assert response.status_code == 201, response.text
    body = response.json()
    video = body["video"]
    assert (video["title"], video["description"]) == ("Clip", "Hi")
    assert (video["visibility"], video["status"]) == ("unlisted", "uploading")
    assert "raw_key" not in video
    assert body["upload"]["url"] == "/uploads/"
    assert body["upload"]["fields"]["key"] == f"raw/{video['id']}/source"


async def test_visibility_defaults_to_private(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    response = await _create(api, await create_user())
    assert response.json()["video"]["visibility"] == "private"


async def test_policy_pins_key_size_and_expiry(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    body = (await _create(api, await create_user())).json()

    policy = _policy(body["upload"])

    assert {"key": f"raw/{body['video']['id']}/source"} in policy["conditions"]
    assert ["content-length-range", 1, 2 * 1024**3] in policy["conditions"]
    expires = datetime.fromisoformat(policy["expiration"])
    assert timedelta(minutes=59) < expires - datetime.now(UTC) <= timedelta(hours=1)


@pytest.mark.parametrize(
    "fields",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 101},
        {"title": "a\x00b"},
        {"description": "x" * 5001},
        {"description": "a\x00b"},
        {"visibility": "secret"},
        {"status": "ready"},
        {"owner_id": "00000000-0000-0000-0000-000000000000"},
        {"raw_key": "raw/other/source"},
    ],
)
async def test_invalid_input_is_rejected(
    api: httpx.AsyncClient, create_user: CreateUser, fields: dict[str, str]
) -> None:
    response = await _create(api, await create_user(), **fields)
    assert response.status_code == 422, response.text


async def test_limit_on_uploads_in_progress(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice, bob = await create_user("alice"), await create_user("bob")
    for _ in range(3):
        assert (await _create(api, alice)).status_code == 201

    assert (await _create(api, alice)).status_code == 409
    assert (await _create(api, bob)).status_code == 201


async def test_limit_on_videos_uploading_or_processing(
    api: httpx.AsyncClient, session: AsyncSession, create_user: CreateUser
) -> None:
    """Processing videos count too, so one account can't queue the worker up without end."""
    alice = await create_user("alice")
    for _ in range(4):
        created = await _create(api, alice)
        await session.execute(
            update(Video)
            .where(Video.id == created.json()["video"]["id"])
            .values(status=VideoStatus.processing)
        )
        await session.commit()

    fifth = await _create(api, alice)
    sixth = await _create(api, alice)

    assert fifth.status_code == 201
    assert sixth.status_code == 409
    assert "uploading or processing" in sixth.json()["detail"]
    await session.execute(
        update(Video).where(Video.owner_id == alice.id).values(status=VideoStatus.failed)
    )
    await session.commit()
    assert (await _create(api, alice)).status_code == 201


async def test_limit_holds_under_concurrent_requests(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    alice = await create_user()

    responses = await asyncio.gather(*(_create(api, alice) for _ in range(8)))

    assert sorted(r.status_code for r in responses) == [201] * 3 + [409] * 5


async def test_upload_form_works_against_storage(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    body = (await _create(api, await create_user())).json()

    response = await _post_form(minio, body["upload"], b"video bytes")

    assert response.status_code == 204, response.text


async def test_upload_form_cannot_write_another_key(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    upload = (await _create(api, await create_user())).json()["upload"]
    upload["fields"]["key"] = "raw/someone-else/source"

    response = await _post_form(minio, upload, b"video bytes")

    assert response.status_code == 403, response.text


async def test_file_over_the_limit_is_rejected_by_storage(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    minio: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D10. The limit is lowered, so the test needn't send 2 GB; the mechanism is the same."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    get_settings.cache_clear()
    upload = (await _create(api, await create_user())).json()["upload"]

    too_big = await _post_form(minio, upload, b"x" * 2048)
    fits = await _post_form(minio, upload, b"x" * 1024)

    assert too_big.status_code == 400, too_big.text
    assert "EntityTooLarge" in too_big.text
    assert fits.status_code == 204, fits.text


async def test_empty_file_is_rejected_by_storage(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    upload = (await _create(api, await create_user())).json()["upload"]

    response = await _post_form(minio, upload, b"")

    assert response.status_code == 400, response.text


async def _complete(api: httpx.AsyncClient, user: ApiUser, video_id: str) -> httpx.Response:
    return await api.post(f"/api/videos/{video_id}/upload/complete", headers=user.headers)


async def _uploaded_video(api: httpx.AsyncClient, user: ApiUser, bucket_url: str) -> str:
    body = (await _create(api, user)).json()
    response = await _post_form(bucket_url, body["upload"], b"video bytes")
    assert response.status_code == 204, response.text
    return body["video"]["id"]


async def _job_count(session: AsyncSession, video_id: str) -> int:
    query = (
        select(func.count()).select_from(ProcessingJob).where(ProcessingJob.video_id == video_id)
    )
    return await session.scalar(query) or 0


async def _status(session: AsyncSession, video_id: str) -> VideoStatus:
    session.expire_all()
    status = await session.scalar(select(Video.status).where(Video.id == video_id))
    assert status is not None
    return status


async def test_complete_moves_to_processing_and_enqueues(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str, session: AsyncSession
) -> None:
    user = await create_user()
    video_id = await _uploaded_video(api, user, minio)

    response = await _complete(api, user, video_id)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "processing"
    video = await session.get(Video, video_id)
    assert video is not None
    assert video.source_size_bytes == len(b"video bytes")
    job = await session.scalar(select(ProcessingJob).where(ProcessingJob.video_id == video_id))
    assert job is not None
    assert (job.status, job.attempts) == (JobStatus.queued, 0)


async def test_complete_without_object_enqueues_nothing(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str, session: AsyncSession
) -> None:
    """D11."""
    user = await create_user()
    video_id = (await _create(api, user)).json()["video"]["id"]

    response = await _complete(api, user, video_id)

    assert response.status_code == 409, response.text
    assert await _status(session, video_id) is VideoStatus.uploading
    assert await _job_count(session, video_id) == 0


async def test_repeating_complete_creates_one_job(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str, session: AsyncSession
) -> None:
    """D12."""
    user = await create_user()
    video_id = await _uploaded_video(api, user, minio)

    first, second = await _complete(api, user, video_id), await _complete(api, user, video_id)

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["status"] == "processing"
    assert await _job_count(session, video_id) == 1


async def test_concurrent_complete_creates_one_job(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str, session: AsyncSession
) -> None:
    """D12, for a double click or a client retry racing the first request."""
    user = await create_user()
    video_id = await _uploaded_video(api, user, minio)

    responses = await asyncio.gather(*(_complete(api, user, video_id) for _ in range(5)))

    assert [r.status_code for r in responses] == [200] * 5
    assert await _job_count(session, video_id) == 1


@pytest.mark.parametrize("status", [VideoStatus.processing, VideoStatus.failed])
async def test_complete_never_restarts_a_later_status(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    minio: str,
    session: AsyncSession,
    status: VideoStatus,
) -> None:
    user = await create_user()
    video_id = await _uploaded_video(api, user, minio)
    await session.execute(update(Video).where(Video.id == video_id).values(status=status))
    await session.commit()

    response = await _complete(api, user, video_id)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == status.value
    assert await _job_count(session, video_id) == 0


async def test_complete_rejects_an_object_over_the_limit(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    minio: str,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second check, in case the object got there some other way than the policy."""
    user = await create_user()
    video_id = (await _create(api, user)).json()["video"]["id"]
    key = f"raw/{video_id}/source"
    storage.get_client().put_object(Bucket=TEST_BUCKET, Key=key, Body=b"x" * 2048)
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    get_settings.cache_clear()

    response = await _complete(api, user, video_id)

    assert response.status_code == 409, response.text
    assert await _job_count(session, video_id) == 0


@pytest.mark.parametrize("role", [UserRole.user, UserRole.moderator, UserRole.admin])
async def test_non_owner_cannot_complete(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    set_role: SetRole,
    minio: str,
    session: AsyncSession,
    role: UserRole,
) -> None:
    """D13."""
    video_id = await _uploaded_video(api, await create_user("alice"), minio)
    other = await create_user("bob")
    await set_role(other, role)

    response = await _complete(api, other, video_id)

    assert response.status_code == 404, response.text
    assert await _status(session, video_id) is VideoStatus.uploading
    assert await _job_count(session, video_id) == 0


async def test_complete_requires_login(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    video_id = (await _create(api, await create_user())).json()["video"]["id"]
    response = await api.post(f"/api/videos/{video_id}/upload/complete")
    assert response.status_code == 401


async def test_complete_unknown_video(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    response = await _complete(api, await create_user(), missing)
    assert response.status_code == 404


async def test_complete_deleted_video(
    api: httpx.AsyncClient, create_user: CreateUser, session: AsyncSession
) -> None:
    user = await create_user()
    video_id = (await _create(api, user)).json()["video"]["id"]
    await session.execute(
        update(Video).where(Video.id == video_id).values(deleted_at=datetime.now(UTC))
    )
    await session.commit()

    assert (await _complete(api, user, video_id)).status_code == 404


async def test_complete_when_storage_is_down(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    closed_port: int,
) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", f"http://127.0.0.1:{closed_port}")
    get_settings.cache_clear()
    storage.get_client.cache_clear()
    user = await create_user()
    video_id = (await _create(api, user)).json()["video"]["id"]

    response = await _complete(api, user, video_id)

    assert response.status_code == 503, response.text
    assert await _status(session, video_id) is VideoStatus.uploading
    assert await _job_count(session, video_id) == 0


async def test_completing_an_upload_frees_a_slot(
    api: httpx.AsyncClient, create_user: CreateUser, minio: str
) -> None:
    user = await create_user()
    first = await _uploaded_video(api, user, minio)
    for _ in range(2):
        await _create(api, user)
    assert (await _create(api, user)).status_code == 409

    await _complete(api, user, first)

    assert (await _create(api, user)).status_code == 201


async def _edit(
    api: httpx.AsyncClient, user: ApiUser, video_id: str, **fields: Any
) -> httpx.Response:
    return await api.patch(f"/api/videos/{video_id}", headers=user.headers, json=fields)


async def test_edit_changes_only_the_given_fields(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()
    video_id = (await _create(api, user, description="Old")).json()["video"]["id"]

    response = await _edit(api, user, video_id, title="  New title ", visibility="public")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["visibility"]) == ("New title", "public")
    assert body["description"] == "Old"


async def test_edit_can_clear_the_description(
    api: httpx.AsyncClient, create_user: CreateUser
) -> None:
    user = await create_user()
    video_id = (await _create(api, user, description="Old")).json()["video"]["id"]

    response = await _edit(api, user, video_id, description="")

    assert response.json()["description"] == ""


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"title": None},
        {"title": "   "},
        {"title": "x" * 101},
        {"description": "a\x00b"},
        {"visibility": "secret"},
        {"status": "ready"},
        {"owner_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
async def test_edit_rejects_invalid_input(
    api: httpx.AsyncClient, create_user: CreateUser, fields: dict[str, Any]
) -> None:
    user = await create_user()
    video_id = (await _create(api, user)).json()["video"]["id"]

    response = await _edit(api, user, video_id, **fields)

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("role", [UserRole.user, UserRole.moderator, UserRole.admin])
async def test_non_owner_cannot_edit(
    api: httpx.AsyncClient,
    create_user: CreateUser,
    set_role: SetRole,
    session: AsyncSession,
    role: UserRole,
) -> None:
    """D13."""
    video_id = (await _create(api, await create_user("alice"))).json()["video"]["id"]
    other = await create_user("bob")
    await set_role(other, role)

    response = await _edit(api, other, video_id, title="Stolen")

    assert response.status_code == 404, response.text
    assert await session.scalar(select(Video.title).where(Video.id == video_id)) == "Clip"


async def test_edit_requires_login(api: httpx.AsyncClient, create_user: CreateUser) -> None:
    video_id = (await _create(api, await create_user())).json()["video"]["id"]
    response = await api.patch(f"/api/videos/{video_id}", json={"title": "New"})
    assert response.status_code == 401


async def test_edit_deleted_video(
    api: httpx.AsyncClient, create_user: CreateUser, session: AsyncSession
) -> None:
    user = await create_user()
    video_id = (await _create(api, user)).json()["video"]["id"]
    await session.execute(
        update(Video).where(Video.id == video_id).values(deleted_at=datetime.now(UTC))
    )
    await session.commit()

    assert (await _edit(api, user, video_id, title="New")).status_code == 404
