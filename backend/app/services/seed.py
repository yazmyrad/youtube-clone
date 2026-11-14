"""Demo data: channels of real, freely licensed videos, viewers and an admin.

The videos come from NASA's public archive (public domain) and the Blender Foundation's open
movies (CC BY), each credited in its description. `app.workers.fetch_demo_media` downloads
them and checks their SHA-256 first; one that can't be had (no internet, say) gets a
generated title card instead, so seeding never depends on the network.

Videos go through the real pipeline: the file is put where a browser upload would land, and
`complete_upload` queues it for the worker. Likes, comments and view counts are
written directly, because a video can't be engaged with until the worker has made it ready.
They move the counters through `adjust_counters` in the same transaction, so counts match
rows. Channel and viewer names are made up; none claims to be the videos' creators.
"""

import asyncio
import contextlib
import hashlib
import logging
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

logger = logging.getLogger(__name__)

EMAIL_DOMAIN = "demo.example.com"
PASSWORD_BYTES = 12


@dataclass(frozen=True)
class DemoSource:
    """A real video, downloaded by `app.workers.fetch_demo_media` and checked against
    `sha256`. Freely licensed, and credited in the video's description."""

    file: str
    url: str
    sha256: str
    credit: str


@dataclass(frozen=True)
class DemoVideo:
    title: str
    tag: str
    description: str
    # For the title card that stands in when the real video can't be had.
    seconds: int
    days_ago: float
    views: int
    source: DemoSource | None = None

    @property
    def full_description(self) -> str:
        if self.source is None:
            return self.description
        return f"{self.description}\n\n{self.source.credit}"


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


NASA_PAGE = "https://images.nasa.gov/details/"
NASA_FILES = "https://images-assets.nasa.gov/video/"
NASA_TERMS = (
    "Public domain: NASA material, used under NASA's media usage guidelines "
    "(nasa.gov/nasa-brand-center/images-and-media). NASA does not endorse this site."
)
BLENDER_TERMS = "License: Creative Commons Attribution 3.0 (creativecommons.org/licenses/by/3.0)."


def _nasa(file: str, nasa_id: str, sha256: str, credit: str) -> DemoSource:
    return DemoSource(
        file=file,
        url=f"{NASA_FILES}{nasa_id}/{nasa_id}~small.mp4",
        sha256=sha256,
        credit=f"Source: {NASA_PAGE}{nasa_id}\nCredit: {credit}\n{NASA_TERMS}",
    )


CHANNELS = (
    DemoChannel(
        "launch_pad",
        "Launch Pad",
        "Rockets, from the factory floor to orbit. Footage from NASA's public archive.",
        "1a4d8f",
        (
            DemoVideo(
                "How the ICON Launch Works",
                "#launch",
                "An animation of how a Pegasus rocket, dropped from a plane, carried NASA's ICON "
                "satellite to orbit to study where Earth's weather meets space weather.",
                61,
                2,
                184_200,
                _nasa(
                    "icon-launch.mp4",
                    "GSFC_20180602_Pegasus_m12910_Launch_Animation",
                    "16c43de71930c528bf5a4d469ed0d9e0911349f1f06df18a6b62b3b8af7a5ee0",
                    "NASA's Goddard Space Flight Center",
                ),
            ),
            DemoVideo(
                "Testing the SLS Rocket Booster",
                "#sls",
                "Why a full-scale firing of a Space Launch System booster in the Utah desert "
                "was a milestone on the way back to the Moon.",
                54,
                9,
                92_310,
                _nasa(
                    "sls-booster-test.mp4",
                    "JB_UtahFSB_Shorter",
                    "9a68366e20c46d7656f85c21145e1ecafed6fc3511a632e975a6cc1b131d7eda",
                    "NASA's Marshall Space Flight Center",
                ),
            ),
            DemoVideo(
                "Building the SLS Core Stage",
                "#factory",
                "Inside NASA's Michoud Assembly Facility, where teams joined the main structures "
                "of the Space Launch System's core stage.",
                68,
                21,
                410_000,
                _nasa(
                    "sls-core-stage.mp4",
                    "MAF_20191204_SLSAssembly-B-roll-UHD",
                    "60638cd60c7fd1b4fdb54b11ae577f6db740568f07fe8a18adbbf45edc4b7e37",
                    "NASA's Michoud Assembly Facility",
                ),
            ),
        ),
    ),
    DemoChannel(
        "sun_watch",
        "Sun Watch",
        "Flares, eruptions and plasma rain: our star, up close. From NASA's public archive.",
        "b8540f",
        (
            DemoVideo(
                "Firework Flare on the Sun",
                "#flare",
                "NASA's Solar Dynamics Observatory watched a solar flare light up the left side "
                "of the Sun on July 8, 2014, along with an eruption of solar material.",
                49,
                1,
                27_450,
                _nasa(
                    "firework-flare.mp4",
                    "GSFC_20140709_SDO_m11605_Firework_Flare",
                    "1901ba1b4c6e60a5a7bb63fe6df41b3f7fa3cac6c820e79257c70b54a926ff7e",
                    "NASA's Goddard Space Flight Center/SDO",
                ),
            ),
            DemoVideo(
                "Plasma Rain on the Sun",
                "#plasma",
                "After a flare on July 24, 2016, NASA's IRIS spacecraft saw plasma rain back down "
                "onto the solar surface along magnetic loops.",
                26,
                6,
                15_870,
                _nasa(
                    "plasma-rain.mp4",
                    "GSFC_20160624_IRIS_m12292_PlasmaRain",
                    "850575453a0ee2f11e90d2f11deb72c72c30ce216305eadc7e38c941184660dc",
                    "NASA's Goddard Space Flight Center/IRIS",
                ),
            ),
            DemoVideo(
                "Holiday Lights on the Sun",
                "#sdo",
                "A significant solar flare, peaking on December 19, 2014, seen in several "
                "wavelengths by NASA's Solar Dynamics Observatory.",
                67,
                12,
                8_640,
                _nasa(
                    "holiday-lights-sun.mp4",
                    "GSFC_20141222_SDO_m11721_Lights",
                    "82f848816930da348b2f6ca845a6020b5708b2f2579b15ae45deb425f685ae94",
                    "NASA's Goddard Space Flight Center/SDO",
                ),
            ),
        ),
    ),
    DemoChannel(
        "blue_planet_lab",
        "Blue Planet Lab",
        "Earth, the Moon and Mars, as spacecraft see them. From NASA's public archive.",
        "1f6f43",
        (
            DemoVideo(
                "Hurricanes Jose and Maria from Orbit",
                "#weather",
                "The Global Precipitation Measurement mission maps the rain inside two major "
                "storms churning across the Atlantic and the Caribbean in September 2017.",
                57,
                3,
                58_700,
                _nasa(
                    "hurricanes-jose-maria.mp4",
                    "GSFC_20170920_GPM_m12723_JoseMaria",
                    "5975034e753c6f6d5cc73d45e74e26d236e97e692471616bb80e4c68ddd156ea",
                    "NASA's Goddard Space Flight Center/GPM",
                ),
            ),
            DemoVideo(
                "Sounds Recorded on Mars",
                "#mars",
                "The first sounds from the surface of Mars, recorded by the microphone on NASA's "
                "Perseverance rover on February 20, 2021. Turn the volume up.",
                21,
                8,
                33_000,
                _nasa(
                    "mars-sounds.mp4",
                    "JPL-20210222-M2020f-0003a-M2020_Audio_A_002",
                    "7feab7fc4d6341e262c2eb0115682e3bdf251b31a82b2a9b9b0513a4370e30b3",
                    "NASA/JPL-Caltech",
                ),
            ),
            DemoVideo(
                "The Moon During an Eclipse",
                "#moon",
                "During the June 2011 lunar eclipse, the Lunar Reconnaissance Orbiter's Diviner "
                "instrument measured how fast the Moon's surface cools in Earth's shadow.",
                60,
                16,
                21_400,
                _nasa(
                    "moon-eclipse.mp4",
                    "GSFC_20110617_LRO_m10794_Eclipse_Moonview",
                    "66eb0f3a4caa980b3f902f118f71eca300133b51b3e6ad826fc22ed6bfbd57b0",
                    "NASA's Goddard Space Flight Center/LRO",
                ),
            ),
            DemoVideo(
                "NASA's Fleet Watching Earth",
                "#earth",
                "No planet is better studied than ours: a tour of the 26 NASA spacecraft that "
                "watch Earth's land, oceans, ice and air.",
                89,
                30,
                63_900,
                _nasa(
                    "earth-fleet.mp4",
                    "GSFC_20170419_EarthFleet_m12586_2017",
                    "a04f85d50e774d4dbebf8cce13b63f7862cd6ee2b5a91d26330c7867a4ca9a86",
                    "NASA's Goddard Space Flight Center",
                ),
            ),
        ),
    ),
    DemoChannel(
        "open_movie_night",
        "Open Movie Night",
        "Trailers of open movies: free to watch, share and remix.",
        "5b2a86",
        (
            DemoVideo(
                "Sintel (Official Trailer)",
                "#animation",
                "A lonely young woman searches for the baby dragon she raised. A short film made "
                "with free software by the Blender Institute.",
                52,
                4,
                91_200,
                DemoSource(
                    file="sintel-trailer.mp4",
                    url="https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4",
                    sha256="b670602fa00934ca27c4351bb0efe7ea7a07fae57284e44226025eeed7c51254",
                    credit="Sintel, (c) copyright Blender Foundation | durian.blender.org\n"
                    + BLENDER_TERMS,
                ),
            ),
            DemoVideo(
                "Big Buck Bunny (Official Trailer)",
                "#animation",
                "A giant rabbit takes on three bullying rodents. A short film made with free "
                "software by the Blender Institute.",
                32,
                14,
                120_000,
                DemoSource(
                    file="big-buck-bunny-trailer.mov",
                    url="https://download.blender.org/peach/trailer/trailer_480p.mov",
                    sha256="36801b74638c12be9aa587e93cd18edfc9bc51a1c089ab2a19ee42beed9f497d",
                    credit="Big Buck Bunny, (c) copyright 2008 Blender Foundation | "
                    "www.bigbuckbunny.org\n" + BLENDER_TERMS,
                ),
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
        "launch_pad",
        "Rockets, start to finish",
        "From the factory floor to the launch.",
        VideoVisibility.public,
        (
            "Building the SLS Core Stage",
            "Testing the SLS Rocket Booster",
            "How the ICON Launch Works",
        ),
    ),
    DemoPlaylist(
        "sun_watch",
        "Best of the Sun",
        "Our favourite flares.",
        VideoVisibility.public,
        ("Firework Flare on the Sun", "Plasma Rain on the Sun", "Holiday Lights on the Sun"),
    ),
    DemoPlaylist(
        "dana_dev",
        "Space picks",
        "What I show friends who say space is boring.",
        VideoVisibility.public,
        (
            "Sounds Recorded on Mars",
            "Hurricanes Jose and Maria from Orbit",
            "The Moon During an Eclipse",
            "NASA's Fleet Watching Earth",
        ),
    ),
    DemoPlaylist(
        "lucy_lints",
        "Watch later",
        "",
        VideoVisibility.private,
        ("Sintel (Official Trailer)", "Big Buck Bunny (Official Trailer)"),
    ),
)

COMMENTS = (
    "Wow, this is beautiful.",
    "Watched it three times already.",
    "Can you post more like this?",
    "The detail here is incredible.",
    "Sending this to my whole family.",
    "Best thing I've seen all week.",
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
    session: AsyncSession, make_clip: ClipMaker, workdir: Path, media_dir: Path | None = None
) -> list[Credential] | None:
    """Creates the demo data and returns the new accounts' credentials, or None when it is
    already there. Passwords are random and exist only in the return value. `media_dir` holds
    the downloaded videos; any missing or damaged one gets a title card instead."""
    accounts = _accounts()
    names = [account.username for account in accounts]
    existing = set(await session.scalars(select(User.username).where(User.username.in_(names))))
    if len(existing) == len(names):
        return None
    if existing and not existing & {channel.username for channel in CHANNELS}:
        # Demo data from an older catalog, whose viewers share these names: leave it be,
        # rather than fail an upgrade. A fresh database gets the current catalog.
        logger.info("Older demo data is present; leaving it as it is")
        return None
    if existing:
        raise PartiallySeeded(f"Some demo accounts already exist: {', '.join(sorted(existing))}")

    credentials, users = await _create_accounts(session, accounts)
    # Read now: after the rollback below, the objects are expired and can't load lazily.
    user_ids = [user.id for user in users.values()]
    try:
        video_ids = await _add_videos(session, users, make_clip, workdir, media_dir)
        await _subscribe_viewers(session, users)
        await _add_playlists(session, users, video_ids)
    except BaseException:
        # The passwords die with this run, so its accounts must too: otherwise a rerun would
        # find them, do nothing, and leave demo accounts nobody can log in to.
        await _undo(session, user_ids)
        raise
    return credentials


async def _add_videos(
    session: AsyncSession,
    users: dict[str, User],
    make_clip: ClipMaker,
    workdir: Path,
    media_dir: Path | None,
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
            media = await downloaded(media_dir, demo.source)
            if demo.source is not None and media is None:
                logger.warning("%s: no verified download; a title card stands in", demo.title)
            video_id = await _add_video(session, owner, demo, card, now, make_clip, workdir, media)
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


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def downloaded(media_dir: Path | None, source: DemoSource | None) -> Path | None:
    """The video's verified download, or None. Checked again here, so a damaged or swapped
    file never reaches the site."""
    if media_dir is None or source is None:
        return None
    path = media_dir / source.file
    if not path.is_file():
        return None
    if await asyncio.to_thread(sha256_of, path) != source.sha256:
        return None
    return path


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
    media: Path | None,
) -> uuid.UUID:
    data = VideoCreateIn(
        title=demo.title, description=demo.full_description, visibility=VideoVisibility.public
    )
    video, _ = await videos.create_video(session, owner, data)
    if media is not None:
        await storage.upload_raw(storage.raw_key(video.id), media)
    else:
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
