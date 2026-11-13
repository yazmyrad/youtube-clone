# Import every model module here, so Alembic's autogenerate sees all tables.
from app.models.base import Base
from app.models.engagement import Comment, ReactionType, VideoReaction
from app.models.history import VideoView, WatchHistory
from app.models.job import JobStatus, ProcessingJob
from app.models.playlist import Playlist, PlaylistItem
from app.models.user import RefreshToken, Subscription, User, UserRole
from app.models.video import Video, VideoAccess, VideoStatus, VideoVisibility

__all__ = [
    "Base",
    "Comment",
    "JobStatus",
    "Playlist",
    "PlaylistItem",
    "ProcessingJob",
    "ReactionType",
    "RefreshToken",
    "Subscription",
    "User",
    "UserRole",
    "Video",
    "VideoAccess",
    "VideoReaction",
    "VideoStatus",
    "VideoView",
    "VideoVisibility",
    "WatchHistory",
]
