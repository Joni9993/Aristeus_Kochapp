"""SQLAlchemy 2.0 models.

Phase 0 keeps this almost empty — full schema (households, profiles,
brochures, offers, weekly_plans, ...) lands with Phase 1+ migrations.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HealthPing(Base):
    """Trivial table so Alembic has something to migrate on day one."""

    __tablename__ = "health_pings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
