import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Playlist, PlaylistItem, User, Video, VideoVisibility


@pytest.fixture
async def user(session: AsyncSession) -> User:
    user = User(username="alice", email="alice@example.com", password_hash="x", display_name="A")
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
async def playlist(session: AsyncSession, user: User) -> Playlist:
    playlist = Playlist(owner_id=user.id, title="Favourites")
    session.add(playlist)
    await session.commit()
    return playlist


async def _videos(session: AsyncSession, user: User, count: int) -> list[Video]:
    videos = [Video(owner_id=user.id, title=f"Clip {i}") for i in range(count)]
    session.add_all(videos)
    await session.commit()
    return videos


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_defaults(session: AsyncSession, playlist: Playlist) -> None:
    await session.refresh(playlist)

    assert playlist.visibility == VideoVisibility.public
    assert playlist.description == ""


async def test_title_cant_be_blank(session: AsyncSession, user: User) -> None:
    session.add(Playlist(owner_id=user.id, title="   "))

    with pytest.raises(IntegrityError, match="ck_playlists_title_not_blank"):
        await session.commit()
    await session.rollback()


async def test_a_video_appears_once_per_playlist(
    session: AsyncSession, user: User, playlist: Playlist
) -> None:
    [video] = await _videos(session, user, 1)
    session.add(PlaylistItem(playlist_id=playlist.id, video_id=video.id, position=0))
    await session.commit()
    session.expunge_all()

    session.add(PlaylistItem(playlist_id=playlist.id, video_id=video.id, position=1))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_positions_are_unique_at_commit(
    session: AsyncSession, user: User, playlist: Playlist
) -> None:
    a, b = await _videos(session, user, 2)
    session.add_all(
        [
            PlaylistItem(playlist_id=playlist.id, video_id=a.id, position=0),
            PlaylistItem(playlist_id=playlist.id, video_id=b.id, position=0),
        ]
    )

    with pytest.raises(IntegrityError, match="uq_playlist_items_playlist_id_position"):
        await session.commit()
    await session.rollback()


async def test_a_reorder_may_pass_through_duplicates_in_one_transaction(
    session: AsyncSession, user: User, playlist: Playlist
) -> None:
    """The constraint is deferred, so swapping two positions needs no temporary values."""
    a, b = await _videos(session, user, 2)
    session.add_all(
        [
            PlaylistItem(playlist_id=playlist.id, video_id=a.id, position=0),
            PlaylistItem(playlist_id=playlist.id, video_id=b.id, position=1),
        ]
    )
    await session.commit()

    for video, position in ((a, 1), (b, 0)):
        await session.execute(
            update(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist.id, PlaylistItem.video_id == video.id)
            .values(position=position)
        )
    await session.commit()

    rows = await session.execute(select(PlaylistItem.video_id).order_by(PlaylistItem.position))
    assert list(rows.scalars()) == [b.id, a.id]


async def test_position_cant_be_negative(
    session: AsyncSession, user: User, playlist: Playlist
) -> None:
    [video] = await _videos(session, user, 1)
    session.add(PlaylistItem(playlist_id=playlist.id, video_id=video.id, position=-1))

    with pytest.raises(IntegrityError, match="ck_playlist_items_position_non_negative"):
        await session.commit()
    await session.rollback()


@pytest.mark.parametrize("deleted", ["playlist", "video"])
async def test_items_go_with_their_playlist_or_video(
    session: AsyncSession, user: User, playlist: Playlist, deleted: str
) -> None:
    [video] = await _videos(session, user, 1)
    session.add(PlaylistItem(playlist_id=playlist.id, video_id=video.id, position=0))
    await session.commit()

    if deleted == "playlist":
        await session.execute(delete(Playlist).where(Playlist.id == playlist.id))
    else:
        await session.execute(delete(Video).where(Video.id == video.id))
    await session.commit()

    assert await _count(session, PlaylistItem) == 0


async def test_playlists_go_with_their_owner(
    session: AsyncSession, user: User, playlist: Playlist
) -> None:
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()

    assert await _count(session, Playlist) == 0
