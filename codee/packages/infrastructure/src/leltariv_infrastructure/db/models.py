from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from leltariv_infrastructure.db.base import Base


class InventoryZone(Base):
    __tablename__ = "inventory_zone"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    site_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)

    assets: Mapped[list[Asset]] = relationship(back_populates="zone")
    codes: Mapped[list[AssetCode]] = relationship(back_populates="zone")


class AssetType(Base):
    __tablename__ = "asset_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    assets: Mapped[list[Asset]] = relationship(back_populates="asset_type")


class ImportBatch(Base):
    __tablename__ = "import_batch"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_system: Mapped[str | None] = mapped_column(Text, nullable=True)
    rows_read: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_ok: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
    )
    imported_by: Mapped[UUID | None] = mapped_column(nullable=True)

    assets: Mapped[list[Asset]] = relationship(back_populates="import_batch")


class Asset(Base):
    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("asset_number", "sub_number", name="uq_asset_number_sub_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_number: Mapped[str] = mapped_column(Text, nullable=False)
    sub_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)

    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_zone.id"),
        nullable=True,
    )
    asset_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("asset_type.id"),
        nullable=True,
    )
    parent_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("asset.id"),
        nullable=True,
    )

    original_asset: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    gross_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    accum_depreciation: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )
    book_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default=text("'HUF'"),
    )

    serial_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )

    import_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_batch.id"),
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    zone: Mapped[InventoryZone | None] = relationship(back_populates="assets")
    asset_type: Mapped[AssetType | None] = relationship(back_populates="assets")
    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="assets")
    parent_asset: Mapped[Asset | None] = relationship(
        remote_side="Asset.id",
        back_populates="child_assets",
    )
    child_assets: Mapped[list[Asset]] = relationship(back_populates="parent_asset")
    codes: Mapped[list[AssetCode]] = relationship(back_populates="asset")


class AssetCode(Base):
    __tablename__ = "asset_code"
    __table_args__ = (
        UniqueConstraint("zone_id", "code_normalized", name="uq_asset_code_zone_normalized"),
        CheckConstraint(
            "code_type IN ('LELTARSZAM', 'ESZKOZSZAM', 'GYARI_SZAM', 'SAJAT_CIMKE')",
            name="ck_asset_code_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("asset.id"), nullable=False)
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_zone.id"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    code_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    code_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    asset: Mapped[Asset] = relationship(back_populates="codes")
    zone: Mapped[InventoryZone] = relationship(back_populates="codes")


class Room(Base):
    __tablename__ = "room"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    zone_id: Mapped[int] = mapped_column(ForeignKey("inventory_zone.id"), nullable=False)
    building: Mapped[str | None] = mapped_column(Text, nullable=True)
    floor: Mapped[str | None] = mapped_column(Text, nullable=True)
    room_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN', 'LELTAROZO', 'OLVASO')",
            name="ck_app_user_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )


class InventoryPeriod(Base):
    __tablename__ = "inventory_period"
    __table_args__ = (
        CheckConstraint(
            "state IN ('DRAFT', 'ACTIVE', 'CLOSED')",
            name="ck_inventory_period_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)


class InventorySession(Base):
    __tablename__ = "inventory_session"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    period_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_period.id"),
        nullable=False,
    )
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_zone.id"),
        nullable=False,
    )
    room_id: Mapped[UUID | None] = mapped_column(ForeignKey("room.id"), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Scan(Base):
    __tablename__ = "scan"
    __table_args__ = (
        CheckConstraint(
            "result IN ('FOUND', 'UNKNOWN_CODE', 'FOREIGN_ZONE', 'SURPLUS')",
            name="ck_scan_result",
        ),
        CheckConstraint(
            "verification IN ('DIRECT', 'INHERITED')",
            name="ck_scan_verification",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("inventory_session.id"),
        nullable=False,
    )
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("asset.id"), nullable=True)
    raw_code: Mapped[str] = mapped_column(Text, nullable=False)
    code_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_delta: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    verification: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'DIRECT'"),
    )
    room_id: Mapped[UUID | None] = mapped_column(ForeignKey("room.id"), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    scanned_by: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    compensates_scan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("scan.id"),
        nullable=True,
    )
