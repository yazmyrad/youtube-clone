# Import every model module here, so Alembic's autogenerate sees all tables.
from app.models.base import Base
from app.models.user import RefreshToken, User, UserRole
from app.models.video import Video, VideoStatus, VideoVisibility

__all__ = ["Base", "RefreshToken", "User", "UserRole", "Video", "VideoStatus", "VideoVisibility"]
