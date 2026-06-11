from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.cidr_database import CidrBase


class ProviderCidr(CidrBase):
    __tablename__ = "provider_cidr"
    __table_args__ = (
        UniqueConstraint("provider_key", "cidr", name="uq_provider_cidr_key_cidr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    cidr: Mapped[str] = mapped_column(String(50))
    region_scope: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    country_codes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
