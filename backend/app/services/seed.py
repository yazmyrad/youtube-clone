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
from app.services import channel_images, storage, videos
from app.services import channels as channels_service
from app.services.channel_images import ImageKind
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
    # Vertical: a Short. Its stand-in title card is vertical too.
    short: bool = False

    @property
    def full_description(self) -> str:
        if self.source is None:
            return self.description
        return f"{self.description}\n\n{self.source.credit}"


@dataclass(frozen=True)
class DemoFrame:
    """A still from one of the channel's own videos: `at` is how far in, from 0 to 1."""

    video: str
    at: float


@dataclass(frozen=True)
class DemoChannel:
    username: str
    display_name: str
    description: str
    color: str
    videos: tuple[DemoVideo, ...]
    # Without a verified download, the letter avatar and no banner, as for a new channel.
    avatar: DemoFrame | None = None
    banner: DemoFrame | None = None


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
COMMONS_PAGE = "https://commons.wikimedia.org/wiki/File:"
COMMONS_FILES = "https://upload.wikimedia.org/wikipedia/commons/transcoded/"
NOAA_TERMS = (
    "Public domain: imagery from NOAA satellites, processed by CSU/CIRA; via Wikimedia Commons."
)
SVS_TERMS = (
    "Public domain: NASA's Scientific Visualization Studio, via Wikimedia Commons. "
    "NASA does not endorse this site."
)
CC0_TERMS = "License: Creative Commons CC0 1.0, a public domain dedication."
CC_BY_4_TERMS = (
    "License: Creative Commons Attribution 4.0 (creativecommons.org/licenses/by/4.0). "
    "Converted for streaming."
)
CC_BY_3_TERMS = (
    "License: Creative Commons Attribution 3.0 (creativecommons.org/licenses/by/3.0). "
    "Converted for streaming."
)


def _commons(file: str, name: str, path: str, sha256: str, credit: str, terms: str) -> DemoSource:
    """A file on Wikimedia Commons, in its 1080p VP9 rendition, which Commons makes itself."""
    return DemoSource(
        file=file,
        url=f"{COMMONS_FILES}{path}/{path.rsplit('/', 1)[-1]}.1080p.vp9.webm",
        sha256=sha256,
        credit=f"Source: {COMMONS_PAGE}{name}\nCredit: {credit}\n{terms}",
    )


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
            DemoVideo(
                "How Close Apophis Will Pass in 2029",
                "#shorts",
                "On April 13, 2029, asteroid Apophis will pass closer to Earth than some of our "
                "satellites. A short animation of its path.",
                23,
                1.5,
                71_400,
                _commons(
                    "apophis.webm",
                    "Asteroid_Apophis_2029_Earth_Flyby_%E2%80%93_Animations_(SVS20414_-_Apophis_"
                    "Distance_Animation_Vertical_4k).webm",
                    "2/2e/Asteroid_Apophis_2029_Earth_Flyby_%E2%80%93_Animations_%28SVS20414_-_"
                    "Apophis_Distance_Animation_Vertical_4k%29.webm",
                    "1b38ba39524370100a84a81a1813144bb1b28282e38dd6dec04a524f12683f9b",
                    "NASA's Scientific Visualization Studio",
                    SVS_TERMS,
                ),
                short=True,
            ),
            DemoVideo(
                "Reading an Exoplanet's Air",
                "#shorts",
                "How starlight passing through a distant planet's atmosphere tells astronomers "
                "what it's made of.",
                13,
                5,
                18_900,
                _commons(
                    "exoplanet.webm",
                    "Viewing_an_Exoplanet_Transmission_Spectrum_(SVS14946_-_GasGiant_Vertical).webm",
                    "b/b4/Viewing_an_Exoplanet_Transmission_Spectrum_%28SVS14946_-_GasGiant_"
                    "Vertical%29.webm",
                    "b83ca7a5182aca63008e1094c5b49b64b37c0aeec9931a45bb198d91836f2b54",
                    "NASA's Scientific Visualization Studio",
                    SVS_TERMS,
                ),
                short=True,
            ),
        ),
        avatar=DemoFrame("Testing the SLS Rocket Booster", 0.65),
        banner=DemoFrame("Testing the SLS Rocket Booster", 0.55),
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
        avatar=DemoFrame("Firework Flare on the Sun", 0.67),
        banner=DemoFrame("Firework Flare on the Sun", 0.5),
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
            DemoVideo(
                "Hurricane Melissa, Seen From Space",
                "#shorts",
                "Days of Hurricane Melissa as a major storm, in one timelapse from weather "
                "satellites.",
                17,
                0.5,
                240_000,
                _commons(
                    "melissa.webm",
                    "Hurricane_Melissa%E2%80%99s_Life_as_a_Major_Storm_(CIRA_2025-10-29_-_"
                    "nolabels_portrait).webm",
                    "b/bf/Hurricane_Melissa%E2%80%99s_Life_as_a_Major_Storm_%28CIRA_2025-10-29_-_"
                    "nolabels_portrait%29.webm",
                    "a83290608f855f98af14a100a4ee7948fe01f5763e6e2387965aad2c13e6be66",
                    "GOES imagery: CSU/CIRA & NOAA",
                    NOAA_TERMS,
                ),
                short=True,
            ),
            DemoVideo(
                "Saharan Dust Crossing the Atlantic",
                "#shorts",
                "A plume of Saharan dust drifts thousands of kilometres across the Atlantic over "
                "several days.",
                15,
                2.5,
                54_100,
                _commons(
                    "saharan-dust.webm",
                    "Multi-Day_Timelapse_of_Saharan_Dust_Traversing_the_Atlantic_(CIRA_2024-06-26_-"
                    "_nolabels_portrait).webm",
                    "d/d6/Multi-Day_Timelapse_of_Saharan_Dust_Traversing_the_Atlantic_%28CIRA_"
                    "2024-06-26_-_nolabels_portrait%29.webm",
                    "e607de04c79ec5e3b377eab5dc9121577ea905632722e61dc855b4bb0c94ab46",
                    "GOES imagery: CSU/CIRA & NOAA",
                    NOAA_TERMS,
                ),
                short=True,
            ),
            DemoVideo(
                "Three Weeks of Western Wildfires",
                "#shorts",
                "Three weeks of wildfires and their smoke across the western United States, from "
                "orbit.",
                14,
                7,
                12_300,
                _commons(
                    "wildfires.webm",
                    "Three-Week_Timelapse_of_Wildfires_in_the_Western_U_S_(CIRA_2026-07-08_-_"
                    "nolabels_portrait).webm",
                    "5/5d/Three-Week_Timelapse_of_Wildfires_in_the_Western_U_S_%28CIRA_2026-07-08"
                    "_-_nolabels_portrait%29.webm",
                    "de154b69960c94f71aeb1a6008a768dcdfc5a6f425eae4f9edf565f30f7e486b",
                    "JPSS imagery: CSU/CIRA & NOAA/NESDIS",
                    NOAA_TERMS,
                ),
                short=True,
            ),
        ),
        avatar=DemoFrame("NASA's Fleet Watching Earth", 0.9),
        banner=DemoFrame("Hurricanes Jose and Maria from Orbit", 0.5),
    ),
    DemoChannel(
        "wild_water",
        "Wild Water",
        "Waterfalls, birds and other short moments outdoors. Freely licensed clips.",
        "0e6b74",
        (
            DemoVideo(
                "Watagataki Falls",
                "#shorts",
                "Fifteen seconds at Watagataki Falls. Sound on.",
                15,
                1.2,
                33_800,
                _commons(
                    "watagataki.webm",
                    "Watagataki_Falls_(Video).webm",
                    "8/86/Watagataki_Falls_%28Video%29.webm",
                    "837872973d4c71e8ebc5ed8b2eecfd40dac955001c33c5f84cde63b95a2dcaa1",
                    "Yoshi Canopus",
                    CC0_TERMS,
                ),
                short=True,
            ),
            DemoVideo(
                "Cascade de Syratu",
                "#shorts",
                "A waterfall in the forest, filmed straight up.",
                16,
                3.3,
                21_700,
                _commons(
                    "syratu.webm",
                    "Cascade_de_Syratu.webm",
                    "9/94/Cascade_de_Syratu.webm",
                    "dc02d7daaa41e047d9555b9fe9de4be572197b208a77d041933c9ddf9fb5d9a0",
                    "Arie m den toom",
                    CC_BY_4_TERMS,
                ),
                short=True,
            ),
            DemoVideo(
                "Waterfall on Nimrod Stream",
                "#shorts",
                "Mt Nimrod Scenic Reserve, New Zealand.",
                12,
                5.5,
                9_400,
                _commons(
                    "nimrod.webm",
                    "Mt_Nimrod_Scenic_Reserve_-_Waterfall_on_Nimrod_Stream_(video).webm",
                    "9/9f/Mt_Nimrod_Scenic_Reserve_-_Waterfall_on_Nimrod_Stream_%28video%29.webm",
                    "0ba54b546c689f360927ebdee8c53cd25cba323744ca1b32ef57673a1562eba2",
                    "David Nind",
                    CC0_TERMS,
                ),
                short=True,
            ),
            DemoVideo(
                "Seagull vs. Pigeons",
                "#shorts",
                "Who gets the bread? Place your bets.",
                15,
                9.5,
                402_000,
                _commons(
                    "seagull.webm",
                    "Seagull_and_pigeons_eating_bread.webm",
                    "4/4d/Seagull_and_pigeons_eating_bread.webm",
                    "53b7f6f0229ac1761aae851526f620ebf74817e3d2313a2596f8b9290f12b30b",
                    "Atomicdragon136",
                    CC_BY_3_TERMS,
                ),
                short=True,
            ),
        ),
        avatar=DemoFrame("Watagataki Falls", 0.05),
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
        avatar=DemoFrame("Big Buck Bunny (Official Trailer)", 0.5),
        banner=DemoFrame("Sintel (Official Trailer)", 0.72),
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
# (video, how far in from 0 to 1, where to write the JPEG)
FrameGrabber = Callable[[Path, float, Path], Awaitable[None]]


def _accounts() -> list[DemoAccount]:
    channels = [
        DemoAccount(c.username, c.display_name, description=c.description) for c in CHANNELS
    ]
    return [*channels, *VIEWERS, ADMIN]


class PartiallySeeded(Exception):
    """Some demo accounts exist and some don't. Seeding again would be guesswork."""


async def seed(
    session: AsyncSession,
    make_clip: ClipMaker,
    workdir: Path,
    media_dir: Path | None = None,
    grab_frame: FrameGrabber | None = None,
) -> list[Credential] | None:
    """Creates the demo data and returns the new accounts' credentials, or None when it is
    already there. Passwords are random and exist only in the return value. `media_dir` holds
    the downloaded videos; any missing or damaged one gets a title card instead. With
    `grab_frame`, channels get an avatar and banner from stills of their own videos."""
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
        if grab_frame is not None:
            await _add_channel_images(session, users, grab_frame, workdir, media_dir)
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
                vertical=demo.short,
            )
            media = await downloaded(media_dir, demo.source)
            if demo.source is not None and media is None:
                logger.warning("%s: no verified download; a title card stands in", demo.title)
            video_id = await _add_video(session, owner, demo, card, now, make_clip, workdir, media)
            await _engage(session, rng, viewers, video_id, demo.days_ago, now)
            video_ids[demo.title] = video_id
            index += 1
    return video_ids


async def _add_channel_images(
    session: AsyncSession,
    users: dict[str, User],
    grab_frame: FrameGrabber,
    workdir: Path,
    media_dir: Path | None,
) -> None:
    """Through the same checks and re-encoding as an upload. Decoration only: a still that
    can't be made leaves that channel as a new one looks, and seeding goes on."""
    for channel in CHANNELS:
        for kind, frame in ((ImageKind.avatar, channel.avatar), (ImageKind.banner, channel.banner)):
            if frame is None:
                continue
            demo = next(video for video in channel.videos if video.title == frame.video)
            media = await downloaded(media_dir, demo.source)
            if media is None:
                continue
            still = workdir / f"{channel.username}-{kind}.jpg"
            try:
                await grab_frame(media, frame.at, still)
                await channel_images.set_image(
                    session,
                    users[channel.username],
                    kind,
                    await asyncio.to_thread(still.read_bytes),
                    "image/jpeg",
                )
            except Exception:
                await session.rollback()
                logger.warning(
                    "%s: no %s; it keeps the default", channel.username, kind, exc_info=True
                )
            finally:
                still.unlink(missing_ok=True)


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
    for user_id in user_ids:
        with contextlib.suppress(Exception):
            await storage.delete_prefix(
                settings.media_bucket, f"{channel_images.CHANNEL_PREFIX}{user_id}/"
            )
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
    # A channel's demo videos go up while the worker still processes the first ones, so the
    # per-account cap on unfinished uploads, meant for people, doesn't apply.
    video, _ = await videos.create_video(session, owner, data, enforce_limits=False)
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
