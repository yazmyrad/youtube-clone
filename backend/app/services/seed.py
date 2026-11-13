"""Demo data: invented programming channels, viewers and an admin.

Videos go through the real pipeline: a generated clip is put where a browser upload would
land, and `complete_upload` queues it for the worker. Likes, comments and view counts are
written directly, because a video can't be engaged with until the worker has made it ready.
They move the counters through `adjust_counters` in the same transaction, so counts match
rows. All names are made up; none belongs to a real creator.
"""

import contextlib
import random
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.models import (
    Comment,
    Playlist,
    PlaylistItem,
    ReactionType,
    Subscription,
    User,
    UserRole,
    Video,
    VideoReaction,
    VideoVisibility,
)
from app.schemas.videos import VideoCreateIn
from app.services import channels as channels_service
from app.services import storage, videos
from app.services.media import TitleCard

EMAIL_DOMAIN = "demo.example.com"
PASSWORD_BYTES = 12


@dataclass(frozen=True)
class DemoVideo:
    title: str
    tag: str
    description: str
    seconds: int
    days_ago: float
    views: int


@dataclass(frozen=True)
class DemoChannel:
    username: str
    display_name: str
    description: str
    color: str
    videos: tuple[DemoVideo, ...]


@dataclass(frozen=True)
class DemoAccount:
    username: str
    display_name: str
    role: UserRole = UserRole.user
    description: str = ""


@dataclass(frozen=True)
class Credential:
    username: str
    email: str
    password: str
    role: UserRole


CHANNELS = (
    DemoChannel(
        "codebytes",
        "CodeBytes",
        "Programming concepts explained fast. New explainer every week.",
        "b7410e",
        (
            DemoVideo(
                "Rust in 100 Seconds",
                "#rust",
                "Ownership, borrowing and why the compiler is your friend.",
                40,
                2,
                184_200,
            ),
            DemoVideo(
                "Docker vs VMs",
                "#docker",
                "Containers share a kernel; virtual machines bring their own. When to use which.",
                32,
                9,
                92_310,
            ),
            DemoVideo(
                "Big O Notation Explained",
                "#algorithms",
                "Constant, linear, quadratic and logarithmic time with everyday examples.",
                45,
                21,
                410_005,
            ),
            DemoVideo(
                "WebAssembly in 100 Seconds",
                "#wasm",
                "A portable binary format that runs next to JavaScript.",
                28,
                47,
                63_870,
            ),
        ),
    ),
    DemoChannel(
        "terminal_tales",
        "Terminal Tales",
        "Git, shells and the command line, one story at a time.",
        "1e3a8a",
        (
            DemoVideo(
                "Git rebase explained",
                "$ git rebase",
                "Rewrite history safely: rebase vs merge, and interactive rebase.",
                50,
                1,
                27_450,
            ),
            DemoVideo(
                "10 Bash one-liners I use every day",
                "$ bash",
                "find, xargs, awk and friends.",
                36,
                6,
                15_920,
            ),
            DemoVideo(
                "SSH keys from zero",
                "$ ssh",
                "Generate, add to an agent, and stop typing passwords.",
                30,
                15,
                8_604,
            ),
            DemoVideo(
                "tmux for beginners",
                "$ tmux",
                "Sessions, windows and panes that survive a closed laptop.",
                42,
                33,
                11_288,
            ),
        ),
    ),
    DemoChannel(
        "pixel_pipeline",
        "Pixel & Pipeline",
        "Web development and DevOps without the hype.",
        "166534",
        (
            DemoVideo(
                "I tried 5 JavaScript runtimes",
                "<js/>",
                "Comparing startup time, compatibility and tooling.",
                55,
                3,
                58_740,
            ),
            DemoVideo(
                "CSS Grid in 10 minutes",
                "<css/>",
                "Rows, columns, areas and the auto-fit trick.",
                38,
                12,
                33_016,
            ),
            DemoVideo(
                "Postgres indexes, visually",
                "<sql/>",
                "B-tree, GIN and partial indexes, and how to read EXPLAIN.",
                48,
                26,
                21_377,
            ),
            DemoVideo(
                "CI pipelines that don't hurt",
                "<ci/>",
                "Caching, parallel jobs and fast feedback.",
                34,
                60,
                6_402,
            ),
        ),
    ),
)

VIEWERS = (
    DemoAccount("dana_dev", "Dana Ortiz"),
    DemoAccount("brian_builds", "Brian Okafor"),
    DemoAccount("lucy_lints", "Lucy Chen"),
)
ADMIN = DemoAccount("admin", "Site Admin", UserRole.admin)


@dataclass(frozen=True)
class DemoPlaylist:
    owner: str
    title: str
    description: str
    visibility: VideoVisibility
    videos: tuple[str, ...]  # Titles, in playlist order.


PLAYLISTS = (
    DemoPlaylist(
        "codebytes",
        "The 100 Seconds series",
        "Big ideas, short videos.",
        VideoVisibility.public,
        ("Rust in 100 Seconds", "WebAssembly in 100 Seconds", "Big O Notation Explained"),
    ),
    DemoPlaylist(
        "terminal_tales",
        "Terminal essentials",
        "Start here if the command line still feels scary.",
        VideoVisibility.public,
        ("SSH keys from zero", "tmux for beginners", "10 Bash one-liners I use every day"),
    ),
    DemoPlaylist(
        "dana_dev",
        "Backend picks",
        "What I send new teammates.",
        VideoVisibility.public,
        (
            "Postgres indexes, visually",
            "Docker vs VMs",
            "CI pipelines that don't hurt",
            "Git rebase explained",
        ),
    ),
    DemoPlaylist(
        "lucy_lints",
        "Watch later",
        "",
        VideoVisibility.private,
        ("CSS Grid in 10 minutes", "I tried 5 JavaScript runtimes"),
    ),
)

COMMENTS = (
    "This finally made it click for me, thanks!",
    "Can you do a follow-up on the advanced parts?",
    "The pacing in this one is perfect.",
    "I've been doing this wrong for years.",
    "Bookmarked for my next code review.",
    "Great explanation, short and to the point.",
)

# The same tone for every video would be dull; these are the notes of a pentatonic scale.
TONES_HZ = (262, 294, 330, 392, 440)

ClipMaker = Callable[[TitleCard, Path], Awaitable[None]]


def _accounts() -> list[DemoAccount]:
    channels = [
        DemoAccount(c.username, c.display_name, description=c.description) for c in CHANNELS
    ]
    return [*channels, *VIEWERS, ADMIN]


class PartiallySeeded(Exception):
    """Some demo accounts exist and some don't. Seeding again would be guesswork."""


async def seed(
    session: AsyncSession, make_clip: ClipMaker, workdir: Path
) -> list[Credential] | None:
    """Creates the demo data and returns the new accounts' credentials, or None when it is
    already there. Passwords are random and exist only in the return value."""
    accounts = _accounts()
    names = [account.username for account in accounts]
    existing = set(await session.scalars(select(User.username).where(User.username.in_(names))))
    if len(existing) == len(names):
        return None
    if existing:
        raise PartiallySeeded(f"Some demo accounts already exist: {', '.join(sorted(existing))}")

    credentials, users = await _create_accounts(session, accounts)
    # Read now: after the rollback below, the objects are expired and can't load lazily.
    user_ids = [user.id for user in users.values()]
    try:
        video_ids = await _add_videos(session, users, make_clip, workdir)
        await _subscribe_viewers(session, users)
        await _add_playlists(session, users, video_ids)
    except BaseException:
        # The passwords die with this run, so its accounts must too: otherwise a rerun would
        # find them, do nothing, and leave demo accounts nobody can log in to.
        await _undo(session, user_ids)
        raise
    return credentials


async def _add_videos(
    session: AsyncSession, users: dict[str, User], make_clip: ClipMaker, workdir: Path
) -> dict[str, uuid.UUID]:
    """Returns the videos' ids by title."""
    viewers = [users[v.username] for v in VIEWERS]
    now = datetime.now(UTC)
    rng = random.Random(0)  # noqa: S311 - demo data, not security; fixed for repeatability
    video_ids: dict[str, uuid.UUID] = {}
    index = 0
    for channel in CHANNELS:
        owner = users[channel.username]
        for demo in channel.videos:
            card = TitleCard(
                title=demo.title,
                channel=channel.display_name,
                tag=demo.tag,
                color=channel.color,
                tone_hz=TONES_HZ[index % len(TONES_HZ)],
                seconds=demo.seconds,
            )
            video_id = await _add_video(session, owner, demo, card, now, make_clip, workdir)
            await _engage(session, rng, viewers, video_id, demo.days_ago, now)
            video_ids[demo.title] = video_id
            index += 1
    return video_ids


async def _add_playlists(
    session: AsyncSession, users: dict[str, User], video_ids: dict[str, uuid.UUID]
) -> None:
    for demo in PLAYLISTS:
        playlist = Playlist(
            owner_id=users[demo.owner].id,
            title=demo.title,
            description=demo.description,
            visibility=demo.visibility,
        )
        session.add(playlist)
        await session.flush()
        session.add_all(
            PlaylistItem(playlist_id=playlist.id, video_id=video_ids[title], position=position)
            for position, title in enumerate(demo.videos)
        )
    await session.commit()


async def _subscribe_viewers(session: AsyncSession, users: dict[str, User]) -> None:
    """Each viewer follows all channels but one, a different one each, so every channel has
    subscribers and every viewer's subscriptions feed differs."""
    for i, viewer in enumerate(VIEWERS):
        for j, channel in enumerate(CHANNELS):
            if (i + j) % len(CHANNELS) == len(CHANNELS) - 1:
                continue
            channel_id = users[channel.username].id
            session.add(
                Subscription(subscriber_id=users[viewer.username].id, channel_id=channel_id)
            )
            await session.flush()
            await channels_service.adjust_subscribers(session, channel_id, 1)
    await session.commit()


async def _undo(session: AsyncSession, user_ids: list[uuid.UUID]) -> None:
    """Removes a failed run's accounts, their videos and stored files. Deleting a video
    cascades to its job, reactions and comments; a worker already on its job loses the fence."""
    await session.rollback()
    video_ids = list(await session.scalars(select(Video.id).where(Video.owner_id.in_(user_ids))))
    await session.execute(delete(Video).where(Video.owner_id.in_(user_ids)))
    await session.execute(delete(User).where(User.id.in_(user_ids)))
    await session.commit()
    settings = get_settings()
    for video_id in video_ids:
        # Best effort: a leftover object costs disk space, never correctness.
        with contextlib.suppress(Exception):
            await storage.delete_object(settings.uploads_bucket, storage.raw_key(video_id))
            await storage.delete_prefix(settings.media_bucket, storage.hls_prefix(video_id))
            await storage.delete_object(settings.media_bucket, storage.thumbnail_key(video_id))


async def _create_accounts(
    session: AsyncSession, accounts: list[DemoAccount]
) -> tuple[list[Credential], dict[str, User]]:
    credentials: list[Credential] = []
    users: dict[str, User] = {}
    for account in accounts:
        password = secrets.token_urlsafe(PASSWORD_BYTES)
        email = f"{account.username.replace('_', '.')}@{EMAIL_DOMAIN}"
        user = User(
            username=account.username,
            email=email,
            password_hash=await security.hash_password(password),
            display_name=account.display_name,
            description=account.description,
            role=account.role,
        )
        session.add(user)
        users[account.username] = user
        credentials.append(Credential(account.username, email, password, account.role))
    await session.commit()
    return credentials, users


async def _add_video(
    session: AsyncSession,
    owner: User,
    demo: DemoVideo,
    card: TitleCard,
    now: datetime,
    make_clip: ClipMaker,
    workdir: Path,
) -> uuid.UUID:
    data = VideoCreateIn(
        title=demo.title, description=demo.description, visibility=VideoVisibility.public
    )
    video, _ = await videos.create_video(session, owner, data)
    clip = workdir / f"{video.id}.mp4"
    try:
        await make_clip(card, clip)
        await storage.upload_raw(storage.raw_key(video.id), clip)
    finally:
        clip.unlink(missing_ok=True)
    # Processing keeps a preset publish date, so the feed shows a spread of ages.
    video.published_at = now - timedelta(days=demo.days_ago)
    video.views_count = demo.views
    await session.commit()
    await videos.complete_upload(session, owner, video.id)
    return video.id


async def _engage(
    session: AsyncSession,
    rng: random.Random,
    viewers: list[User],
    video_id: uuid.UUID,
    days_ago: float,
    now: datetime,
) -> None:
    likes = dislikes = 0
    for viewer in viewers:
        roll = rng.random()
        if roll < 0.75:
            reaction = ReactionType.like
            likes += 1
        elif roll < 0.85:
            reaction = ReactionType.dislike
            dislikes += 1
        else:
            continue
        session.add(VideoReaction(user_id=viewer.id, video_id=video_id, reaction=reaction))
    commenters = rng.sample(viewers, k=rng.randint(1, len(viewers)))
    for viewer in commenters:
        session.add(
            Comment(
                video_id=video_id,
                author_id=viewer.id,
                body=rng.choice(COMMENTS),
                created_at=now - timedelta(days=days_ago * rng.random()),
            )
        )
    await videos.adjust_counters(
        session,
        video_id,
        likes_count=likes,
        dislikes_count=dislikes,
        comments_count=len(commenters),
    )
    await session.commit()
