"""Demo data (D01): accounts, videos queued through the real pipeline, consistent counters."""

import asyncio
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import (
    Comment,
    Playlist,
    PlaylistItem,
    ProcessingJob,
    ReactionType,
    Subscription,
    User,
    UserRole,
    Video,
    VideoReaction,
    VideoStatus,
    VideoVisibility,
)
from app.services import media, seed, storage, videos
from app.services.media import TitleCard
from app.workers.seed import format_credentials
from tests.conftest import TEST_BUCKET
from tests.media_helpers import require_ffmpeg

ALL_VIDEOS = [video for channel in seed.CHANNELS for video in channel.videos]


def _files(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


async def fake_clip(card: TitleCard, path: Path) -> None:
    await asyncio.to_thread(path.write_bytes, f"clip for {card.title}".encode())


async def run_seed(session: AsyncSession, workdir: Path) -> list[seed.Credential] | None:
    return await seed.seed(session, fake_clip, workdir)


async def test_creates_the_accounts_with_random_passwords(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    credentials = await run_seed(session, tmp_path)

    assert credentials is not None
    assert {c.username for c in credentials} == {a.username for a in seed._accounts()}
    assert len({c.password for c in credentials}) == len(credentials)
    roles = {c.username: c.role for c in credentials}
    assert roles.pop("admin") == UserRole.admin
    assert set(roles.values()) == {UserRole.user}
    for credential in credentials:
        user = await session.scalar(select(User).where(User.username == credential.username))
        assert user is not None
        assert user.email == credential.email
        assert user.password_hash.startswith("$argon2")
        assert await security.verify_password(user.password_hash, credential.password)


async def test_seeded_accounts_can_log_in(
    api: httpx.AsyncClient, session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    credentials = await run_seed(session, tmp_path)
    assert credentials is not None

    for credential in credentials:
        response = await api.post(
            "/api/auth/login", json={"email": credential.email, "password": credential.password}
        )
        assert response.status_code == 200, credential.username


async def test_queues_every_video_through_the_pipeline(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)

    videos = list(await session.scalars(select(Video)))
    assert sorted(v.title for v in videos) == sorted(v.title for v in ALL_VIDEOS)
    assert {v.status for v in videos} == {VideoStatus.processing}
    assert {v.visibility for v in videos} == {VideoVisibility.public}
    jobs = await session.scalar(select(func.count()).select_from(ProcessingJob))
    assert jobs == len(ALL_VIDEOS)
    listing = storage.get_client().list_objects_v2(Bucket=TEST_BUCKET)
    keys = {item["Key"] for item in listing.get("Contents", [])}
    assert keys == {storage.raw_key(v.id) for v in videos}
    # Only the uploaded copies remain; the local clips are gone.
    assert _files(tmp_path) == []


async def test_backdates_and_counts_views_for_a_lived_in_feed(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)

    rows = (await session.execute(select(Video.title, Video.published_at, Video.views_count))).all()
    by_title = {title: (published, views) for title, published, views in rows}
    for demo in ALL_VIDEOS:
        published, views = by_title[demo.title]
        assert published is not None
        assert views == demo.views
    assert len({published for published, _ in by_title.values()}) == len(ALL_VIDEOS)


async def test_counters_match_the_engagement_rows(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)

    total_likes = total_comments = 0
    for video in await session.scalars(select(Video)):
        likes = await session.scalar(
            select(func.count()).where(
                VideoReaction.video_id == video.id, VideoReaction.reaction == ReactionType.like
            )
        )
        dislikes = await session.scalar(
            select(func.count()).where(
                VideoReaction.video_id == video.id, VideoReaction.reaction == ReactionType.dislike
            )
        )
        comments = await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.video_id == video.id)
        )
        assert (video.likes_count, video.dislikes_count, video.comments_count) == (
            likes,
            dislikes,
            comments,
        ), video.title
        assert comments >= 1
        total_likes += likes
        total_comments += comments
    assert total_likes > 0
    assert total_comments > 0


async def test_a_second_run_changes_nothing(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)
    before = await session.scalar(select(func.count()).select_from(Video))

    assert await run_seed(session, tmp_path) is None

    assert await session.scalar(select(func.count()).select_from(Video)) == before


async def test_refuses_to_guess_when_only_some_accounts_exist(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)
    await session.execute(delete(User).where(User.username == "admin"))
    await session.commit()

    with pytest.raises(seed.PartiallySeeded, match="codebytes"):
        await run_seed(session, tmp_path)


def test_credentials_are_printed_one_account_per_line() -> None:
    credentials = [
        seed.Credential("admin", "admin@demo.example.com", "s3cret", UserRole.admin),
        seed.Credential("dana_dev", "dana.dev@demo.example.com", "pa55", UserRole.user),
    ]

    lines = format_credentials(credentials).splitlines()

    assert len(lines) == 3
    assert lines[1].split() == ["admin", "admin", "admin@demo.example.com", "s3cret"]
    assert lines[2].split() == ["user", "dana_dev", "dana.dev@demo.example.com", "pa55"]


async def test_the_title_card_is_a_video_the_worker_accepts(tmp_path: Path) -> None:
    require_ffmpeg()
    if not (media.FONT_DIR / "DejaVuSans-Bold.ttf").exists():
        pytest.skip("needs the DejaVu fonts that ffmpeg brings on Debian and Ubuntu")
    card = TitleCard("Rust: in 100 Seconds 'quoted' 100%", "CodeBytes", "#rust", "b7410e", 440, 2)
    clip = tmp_path / "card.mp4"

    await media.render_title_card(card, clip)

    info = await media.probe(clip)
    assert (info.width, info.height) == (1280, 720)
    assert info.has_audio
    assert 1.5 < info.duration < 3
    assert _files(tmp_path) == ["card.mp4"]


async def test_a_failed_run_leaves_nothing_so_the_next_run_starts_over(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    calls = 0

    async def failing_clip(card: TitleCard, path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("ffmpeg crashed")
        await fake_clip(card, path)

    with pytest.raises(RuntimeError, match="ffmpeg crashed"):
        await seed.seed(session, failing_clip, tmp_path)

    assert await session.scalar(select(func.count()).select_from(User)) == 0
    assert await session.scalar(select(func.count()).select_from(Video)) == 0
    assert storage.get_client().list_objects_v2(Bucket=TEST_BUCKET).get("KeyCount") == 0

    credentials = await run_seed(session, tmp_path)

    assert credentials is not None
    assert await session.scalar(select(func.count()).select_from(Video)) == len(ALL_VIDEOS)


def test_every_demo_title_fits_the_frame() -> None:
    for demo in ALL_VIDEOS:
        lines = media._title_lines(demo.title)
        assert " ".join(lines) == demo.title
        assert all(len(line) <= media.TITLE_LINE_CHARS for line in lines), demo.title
        assert len(lines) <= 3, demo.title


async def test_viewers_subscribe_and_the_counts_match(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)

    for channel in seed.CHANNELS:
        user = await session.scalar(select(User).where(User.username == channel.username))
        assert user is not None
        recount = await session.scalar(
            select(func.count()).select_from(Subscription).where(Subscription.channel_id == user.id)
        )
        assert user.subscribers_count == recount == len(seed.VIEWERS) - 1, channel.username
    for viewer in seed.VIEWERS:
        follows = await session.scalar(
            select(func.count())
            .select_from(Subscription)
            .join(User, User.id == Subscription.subscriber_id)
            .where(User.username == viewer.username)
        )
        assert follows == len(seed.CHANNELS) - 1, viewer.username


def test_demo_playlists_name_real_demo_videos_and_owners() -> None:
    titles = {video.title for video in ALL_VIDEOS}
    owners = {account.username for account in seed._accounts()}
    for playlist in seed.PLAYLISTS:
        assert playlist.owner in owners, playlist.title
        assert set(playlist.videos) <= titles, playlist.title
        assert len(set(playlist.videos)) == len(playlist.videos), playlist.title


async def test_adds_the_demo_playlists_in_order(
    session: AsyncSession, minio: str, tmp_path: Path
) -> None:
    await run_seed(session, tmp_path)

    for demo in seed.PLAYLISTS:
        playlist = await session.scalar(select(Playlist).where(Playlist.title == demo.title))
        assert playlist is not None, demo.title
        assert playlist.visibility == demo.visibility
        titles = await session.scalars(
            select(Video.title)
            .join(PlaylistItem, PlaylistItem.video_id == Video.id)
            .where(PlaylistItem.playlist_id == playlist.id)
            .order_by(PlaylistItem.position)
        )
        assert tuple(titles) == demo.videos


def test_each_demo_channel_fits_under_the_unfinished_video_cap() -> None:
    """The seed adds a channel's videos one after another while the worker still processes
    the first ones, so a channel with as many as the cap would make install fail."""
    for channel in seed.CHANNELS:
        assert len(channel.videos) < videos.MAX_UNFINISHED_VIDEOS, channel.username
