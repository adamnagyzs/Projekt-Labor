"""helyiseg, felelos, visszavonas

A 7-8. alkalom sémája: felelős személy és időbélyeges felelős-kapcsolat, a helyiség
egyedisége a körzeten belül, és a beolvasásnapló három szabálya (egyszeri visszavonás,
negatív darab csak visszavonásnál, lezárt munkamenetbe nem kerül sor).

Revision ID: 7c1d2e8f4a10
Revises: 1ed3a9e31e3a
Create Date: 2026-10-18 10:00:00

"""

# ruff: noqa: E501
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c1d2e8f4a10"
down_revision: str | Sequence[str] | None = "1ed3a9e31e3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("org_unit", sa.Text(), nullable=True),
    )
    op.create_table(
        "asset_responsible",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_asset_responsible_interval"
        ),
    )
    # egy eszköznek egyszerre legfeljebb egy nyitott felelőse lehet
    op.create_index(
        "uq_asset_responsible_open",
        "asset_responsible",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    op.alter_column("room", "room_number", existing_type=sa.Text(), nullable=False)
    op.create_unique_constraint("uq_room_zone_number", "room", ["zone_id", "room_number"])

    op.create_unique_constraint("uq_scan_compensates", "scan", ["compensates_scan_id"])
    op.create_check_constraint(
        "ck_scan_quantity_sign",
        "scan",
        "(compensates_scan_id IS NULL AND quantity_delta > 0)"
        " OR (compensates_scan_id IS NOT NULL AND quantity_delta < 0)",
    )
    op.execute("""
        CREATE FUNCTION scan_session_must_be_open() RETURNS trigger AS $BODY$
        BEGIN
          IF EXISTS (SELECT 1 FROM inventory_session
                     WHERE id = NEW.session_id AND closed_at IS NOT NULL) THEN
            RAISE EXCEPTION 'lezart munkamenetbe nem kerulhet beolvasas';
          END IF;
          RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER scan_session_open BEFORE INSERT ON scan
          FOR EACH ROW EXECUTE FUNCTION scan_session_must_be_open();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS scan_session_open ON scan")
    op.execute("DROP FUNCTION IF EXISTS scan_session_must_be_open()")
    op.drop_constraint("ck_scan_quantity_sign", "scan", type_="check")
    op.drop_constraint("uq_scan_compensates", "scan", type_="unique")
    op.drop_constraint("uq_room_zone_number", "room", type_="unique")
    op.alter_column("room", "room_number", existing_type=sa.Text(), nullable=True)
    op.drop_index("uq_asset_responsible_open", table_name="asset_responsible")
    op.drop_table("asset_responsible")
    op.drop_table("person")
