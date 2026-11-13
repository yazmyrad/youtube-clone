"""Playlists. Being in one grants no access: every read filters items through
`permissions.playable_videos` for the caller (D34)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import Conflict, NotFound
from app.core.pagination import decode_cursor, encode_cursor
from app.core.permissions import (
    channel_playlists,
    ensure_can_view,
    ensure_can_view_playlist,
    ensure_playlist_owner,
    playable_videos,
)
from app.models import Playlist, PlaylistItem, User, Video, VideoVisibility
from app.schemas.playlists import PlaylistCreateIn, PlaylistUpdateIn
from app.services import playback
from app.services.channels import get_channel_user
from app.services.videos import VideoCard, to_card

# Enough for any real list, and it bounds what one read of a playlist costs.
MAX_PLAYLIST_ITEMS = 500


@dataclass(frozen=True)
class PlaylistSummary:
    id: uuid.UUID
    title: str
    visibility: VideoVisibility
    channel: User
    video_count: int
    thumbnail_url: str | None
    updated_at: datetime


@dataclass(frozen=True)
class PlaylistDetails(PlaylistSummary):
    description: str
    created_at: datetime
    items: list[VideoCard]


async def _get(session: AsyncSession, playlist_id: uuid.UUID, *, lock: bool = False) -> Playlist:
    query = select(Playlist).options(joinedload(Playlist.owner, innerjoin=True))
    if lock:
        # Only the playlist row: one owner's concurrent edits take turns.
        query = query.with_for_update(of=Playlist)
    playlist = await session.scalar(query.where(Playlist.id == playlist_id))
    if playlist is None:
        raise NotFound("Playlist not found")
    return playlist


async def get_owned_for_update(
    session: AsyncSession, user: User, playlist_id: uuid.UUID
) -> Playlist:
    playlist = await _get(session, playlist_id, lock=True)
    ensure_playlist_owner(user, playlist)
    return playlist


async def _summaries(
    session: AsyncSession, viewer: User | None, playlists: list[Playlist]
) -> list[PlaylistSummary]:
    """Counts and thumbnails for a page of playlists, in two queries whatever its size."""
    ids = [playlist.id for playlist in playlists]
    visible = (
        select(PlaylistItem.playlist_id, PlaylistItem.video_id, PlaylistItem.position)
        .join(Video, Video.id == PlaylistItem.video_id)
        .where(PlaylistItem.playlist_id.in_(ids), playable_videos(viewer))
    ).subquery()
    counts: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(visible.c.playlist_id, func.count()).group_by(visible.c.playlist_id)
            )
        ).all()
    )
    firsts: dict[uuid.UUID, uuid.UUID] = dict(
        (
            await session.execute(
                select(visible.c.playlist_id, visible.c.video_id)
                .ext(distinct_on(visible.c.playlist_id))
                .order_by(visible.c.playlist_id, visible.c.position)
            )
        ).all()
    )
    return [
        PlaylistSummary(
            id=playlist.id,
            title=playlist.title,
            visibility=playlist.visibility,
            channel=playlist.owner,
            video_count=counts.get(playlist.id, 0),
            thumbnail_url=(
                playback.thumbnail_url(firsts[playlist.id]) if playlist.id in firsts else None
            ),
            updated_at=playlist.updated_at,
        )
        for playlist in playlists
    ]


async def _details(
    session: AsyncSession, viewer: User | None, playlist: Playlist
) -> PlaylistDetails:
    videos = await session.scalars(
        select(Video)
        .join(PlaylistItem, PlaylistItem.video_id == Video.id)
        .options(joinedload(Video.owner, innerjoin=True))
        .where(PlaylistItem.playlist_id == playlist.id, playable_videos(viewer))
        .order_by(PlaylistItem.position)
    )
    items = [to_card(video) for video in videos]
    return PlaylistDetails(
        id=playlist.id,
        title=playlist.title,
        visibility=playlist.visibility,
        channel=playlist.owner,
        video_count=len(items),
        thumbnail_url=items[0].thumbnail_url if items else None,
        updated_at=playlist.updated_at,
        description=playlist.description,
        created_at=playlist.created_at,
        items=items,
    )


async def create_playlist(
    session: AsyncSession, user: User, data: PlaylistCreateIn
) -> PlaylistDetails:
    playlist = Playlist(
        owner_id=user.id,
        title=data.title,
        description=data.description,
        visibility=data.visibility,
    )
    session.add(playlist)
    await session.commit()
    # Read back fresh, with the timestamps the database set.
    session.expunge(playlist)
    return await get_playlist(session, user, playlist.id)


async def get_playlist(
    session: AsyncSession, viewer: User | None, playlist_id: uuid.UUID
) -> PlaylistDetails:
    playlist = await _get(session, playlist_id)
    ensure_can_view_playlist(viewer, playlist)
    return await _details(session, viewer, playlist)


async def update_playlist(
    session: AsyncSession, user: User, playlist_id: uuid.UUID, data: PlaylistUpdateIn
) -> PlaylistDetails:
    playlist = await get_owned_for_update(session, user, playlist_id)
    if data.title is not None:
        playlist.title = data.title
    if data.description is not None:
        playlist.description = data.description
    if data.visibility is not None:
        playlist.visibility = data.visibility
    await session.commit()
    session.expunge(playlist)
    return await get_playlist(session, user, playlist_id)


async def delete_playlist(session: AsyncSession, user: User, playlist_id: uuid.UUID) -> None:
    playlist = await get_owned_for_update(session, user, playlist_id)
    await session.delete(playlist)
    await session.commit()


async def list_channel_playlists(
    session: AsyncSession, viewer: User | None, username: str, *, cursor: str | None, limit: int
) -> tuple[list[PlaylistSummary], str | None]:
    """Newest first. The owner sees all of theirs; others see the public ones."""
    channel = await get_channel_user(session, username)
    query = (
        select(Playlist)
        .options(joinedload(Playlist.owner, innerjoin=True))
        .where(channel_playlists(viewer, channel))
        .order_by(Playlist.created_at.desc(), Playlist.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        query = query.where(tuple_(Playlist.created_at, Playlist.id) < decode_cursor(cursor))
    playlists = list(await session.scalars(query))
    next_cursor = None
    if len(playlists) > limit:
        playlists = playlists[:limit]
        next_cursor = encode_cursor(playlists[-1].created_at, playlists[-1].id)
    return await _summaries(session, viewer, playlists), next_cursor


async def _touch(session: AsyncSession, playlist: Playlist) -> None:
    """Item changes count as edits of the playlist."""
    playlist.updated_at = func.now()
    await session.commit()
    session.expunge(playlist)


async def add_item(
    session: AsyncSession, user: User, playlist_id: uuid.UUID, video_id: uuid.UUID
) -> PlaylistDetails:
    """Appends the video. Safe to repeat: a video already there stays where it is. The
    playlist's row lock makes concurrent adds take turns, so positions stay unique."""
    playlist = await get_owned_for_update(session, user, playlist_id)
    video = await session.get(Video, video_id)
    if video is None:
        raise NotFound("Video not found")
    await ensure_can_view(session, user, video)
    if await session.get(PlaylistItem, (playlist.id, video.id)) is None:
        count = await session.scalar(
            select(func.count())
            .select_from(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist.id)
        )
        if (count or 0) >= MAX_PLAYLIST_ITEMS:
            raise Conflict(f"A playlist holds at most {MAX_PLAYLIST_ITEMS} videos")
        last = await session.scalar(
            select(func.max(PlaylistItem.position)).where(PlaylistItem.playlist_id == playlist.id)
        )
        position = 0 if last is None else last + 1
        session.add(PlaylistItem(playlist_id=playlist.id, video_id=video.id, position=position))
        await _touch(session, playlist)
    else:
        await session.commit()
    return await get_playlist(session, user, playlist_id)


async def remove_item(
    session: AsyncSession, user: User, playlist_id: uuid.UUID, video_id: uuid.UUID
) -> PlaylistDetails:
    """Safe to repeat. The items after it move up, so positions stay 0..n-1."""
    playlist = await get_owned_for_update(session, user, playlist_id)
    position = await session.scalar(
        delete(PlaylistItem)
        .where(PlaylistItem.playlist_id == playlist.id, PlaylistItem.video_id == video_id)
        .returning(PlaylistItem.position)
    )
    if position is not None:
        await session.execute(
            update(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist.id, PlaylistItem.position > position)
            .values(position=PlaylistItem.position - 1)
        )
        await _touch(session, playlist)
    else:
        await session.commit()
    return await get_playlist(session, user, playlist_id)


async def reorder_items(
    session: AsyncSession, user: User, playlist_id: uuid.UUID, video_ids: list[uuid.UUID]
) -> PlaylistDetails:
    """`video_ids` is the new order of exactly the videos the owner sees in the playlist.
    Any the owner can no longer watch keep their order, after those."""
    playlist = await get_owned_for_update(session, user, playlist_id)
    rows = (
        await session.execute(
            select(PlaylistItem.video_id, playable_videos(user).label("shown"))
            .join(Video, Video.id == PlaylistItem.video_id)
            .where(PlaylistItem.playlist_id == playlist.id)
            .order_by(PlaylistItem.position)
        )
    ).all()
    shown = [row.video_id for row in rows if row.shown]
    if len(set(video_ids)) != len(video_ids) or set(video_ids) != set(shown):
        raise Conflict("The playlist has changed. Reload it and try again")
    order = [*video_ids, *(row.video_id for row in rows if not row.shown)]
    # The unique (playlist, position) check is deferred to commit, so swaps are fine.
    for position, video_id in enumerate(order):
        await session.execute(
            update(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist.id, PlaylistItem.video_id == video_id)
            .values(position=position)
        )
    await _touch(session, playlist)
    return await get_playlist(session, user, playlist_id)
