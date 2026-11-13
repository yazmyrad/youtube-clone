import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ModerationAction,
    ModerationActionType,
    Report,
    ReportReason,
    ReportStatus,
    User,
    Video,
)


async def _user(session: AsyncSession, name: str) -> User:
    user = User(username=name, email=f"{name}@example.com", password_hash="x", display_name=name)
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
async def video(session: AsyncSession) -> Video:
    owner = await _user(session, "owner")
    video = Video(owner_id=owner.id, title="Clip")
    session.add(video)
    await session.commit()
    return video


def _report(video: Video, reporter: User, **fields: object) -> Report:
    return Report(video_id=video.id, reporter_id=reporter.id, reason=ReportReason.spam, **fields)


async def test_one_open_report_per_user_and_video(session: AsyncSession, video: Video) -> None:
    """D56, in the schema."""
    alice = await _user(session, "alice")
    session.add(_report(video, alice))
    await session.commit()

    session.add(_report(video, alice))
    with pytest.raises(IntegrityError, match="uq_reports_open_video_reporter"):
        await session.commit()
    await session.rollback()


async def test_a_closed_report_doesnt_block_a_new_one(session: AsyncSession, video: Video) -> None:
    alice = await _user(session, "alice")
    session.add(_report(video, alice, status=ReportStatus.dismissed))
    session.add(_report(video, alice, status=ReportStatus.resolved))
    await session.commit()

    session.add(_report(video, alice))
    await session.commit()


async def test_reports_go_with_their_video(session: AsyncSession, video: Video) -> None:
    alice = await _user(session, "alice")
    session.add(_report(video, alice))
    await session.commit()

    await session.execute(delete(Video).where(Video.id == video.id))
    await session.commit()

    assert list(await session.scalars(select(Report))) == []


async def test_the_audit_log_outlives_its_targets(session: AsyncSession, video: Video) -> None:
    mod, alice = await _user(session, "mod"), await _user(session, "alice")
    report = _report(video, alice)
    session.add(report)
    await session.commit()
    session.add(
        ModerationAction(
            actor_id=mod.id,
            action=ModerationActionType.hide_video,
            target_video_id=video.id,
            target_user_id=alice.id,
            report_id=report.id,
        )
    )
    await session.commit()

    mod_id = mod.id
    await session.execute(delete(Video).where(Video.id == video.id))  # Takes the report too.
    await session.execute(delete(User).where(User.id == alice.id))
    await session.commit()

    session.expire_all()
    [action] = await session.scalars(select(ModerationAction))
    assert (action.target_video_id, action.target_user_id, action.report_id) == (None, None, None)
    assert action.actor_id == mod_id
    assert action.id >= 1


async def test_an_actor_with_audit_rows_cant_be_deleted(session: AsyncSession) -> None:
    mod = await _user(session, "mod")
    session.add(ModerationAction(actor_id=mod.id, action=ModerationActionType.enable_user))
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(delete(User).where(User.id == mod.id))
    await session.rollback()
