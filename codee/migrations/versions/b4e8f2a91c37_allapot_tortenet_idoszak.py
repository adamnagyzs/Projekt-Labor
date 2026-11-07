"""allapot, tortenet, idoszak

A 9-10. alkalom sémája. Eszközállapot és csak hozzáírható állapotnapló; az eszköz, a
felelős-kapcsolat és a napló sora nem törölhető (logikai törlés az állapottal); az
időszakból egyszerre egy aktív lehet, és a lezárt időszakba semmi nem kerülhet.

Minden szabálysértés `check_violation` (23514) hibakóddal áll meg, így a szerver
IntegrityErrorként kapja, és 409-et adhat belőle.

Revision ID: b4e8f2a91c37
Revises: 7c1d2e8f4a10
Create Date: 2026-11-07 19:30:00

"""

# ruff: noqa: E501
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8f2a91c37"
down_revision: str | Sequence[str] | None = "7c1d2e8f4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "('ACTIVE', 'SCRAPPED', 'LOST', 'STOLEN', 'OTHER')"


def upgrade() -> None:
    # --- eszközállapot és napló -------------------------------------------------------
    op.add_column(
        "asset",
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ACTIVE'")),
    )
    op.create_check_constraint("ck_asset_status", "asset", f"status IN {STATUSES}")

    op.create_table(
        "asset_status_change",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("asset.id"), nullable=False),
        sa.Column("old_status", sa.Text(), nullable=False),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changed_by", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.CheckConstraint(f"old_status IN {STATUSES}", name="ck_status_change_old"),
        sa.CheckConstraint(f"new_status IN {STATUSES}", name="ck_status_change_new"),
        sa.CheckConstraint("new_status <> old_status", name="ck_status_change_differs"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_status_change_reason"),
    )
    op.create_index(
        "ix_asset_status_change_asset", "asset_status_change", ["asset_id", "changed_at"]
    )

    # A napló sora állítja át az eszközt, és csak akkor, ha az old_status a mostani
    # állapot. Két egyidejű váltásnál a második UPDATE megvárja az elsőt, utána nem talál
    # sort, és elbukik: nem lesz olyan napló, amelyik rossz állapotból indul.
    op.execute("""
        CREATE FUNCTION asset_status_change_apply() RETURNS trigger AS $BODY$
        BEGIN
          UPDATE asset SET status = NEW.new_status, updated_at = now()
           WHERE id = NEW.asset_id AND status = NEW.old_status;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'az eszkoz allapota mar nem %', NEW.old_status
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER asset_status_change_apply AFTER INSERT ON asset_status_change
          FOR EACH ROW EXECUTE FUNCTION asset_status_change_apply();
    """)

    # Közvetlenül nem írható át az állapot, csak a naplón át (akkor a trigger mélysége 2).
    # Így a napló mindig teljes, és egy korábbi állapot visszaszámolható belőle.
    op.execute("""
        CREATE FUNCTION asset_status_only_via_log() RETURNS trigger AS $BODY$
        BEGIN
          IF NEW.status IS DISTINCT FROM OLD.status AND pg_trigger_depth() < 2 THEN
            RAISE EXCEPTION 'az allapot csak az asset_status_change tablan at valtozhat'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER asset_status_only_via_log BEFORE UPDATE OF status ON asset
          FOR EACH ROW EXECUTE FUNCTION asset_status_only_via_log();
    """)

    # --- ami a történethez tartozik, nem törölhető ----------------------------------------
    op.execute("""
        CREATE FUNCTION history_is_permanent() RETURNS trigger AS $BODY$
        BEGIN
          RAISE EXCEPTION '%: a sor nem torolheto/modosithato, a tortenet resze', TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
        END;
        $BODY$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER asset_no_delete BEFORE DELETE ON asset
          FOR EACH ROW EXECUTE FUNCTION history_is_permanent();
    """)
    op.execute("""
        CREATE TRIGGER asset_responsible_no_delete BEFORE DELETE ON asset_responsible
          FOR EACH ROW EXECUTE FUNCTION history_is_permanent();
    """)
    op.execute("""
        CREATE TRIGGER asset_status_change_no_update_delete
          BEFORE UPDATE OR DELETE ON asset_status_change
          FOR EACH ROW EXECUTE FUNCTION history_is_permanent();
    """)

    # --- leltári időszak ------------------------------------------------------------------
    op.execute("UPDATE inventory_period SET state = 'DRAFT' WHERE state IS NULL")
    op.execute("UPDATE inventory_period SET closed_at = NULL WHERE state <> 'CLOSED'")
    op.execute(
        "UPDATE inventory_period SET closed_at = coalesce(opened_at, now())"
        " WHERE state = 'CLOSED' AND closed_at IS NULL"
    )
    op.alter_column("inventory_period", "state", existing_type=sa.Text(), nullable=False)
    op.create_check_constraint(
        "ck_inventory_period_closed_at",
        "inventory_period",
        "(state = 'CLOSED') = (closed_at IS NOT NULL)",
    )
    op.create_index(
        "uq_inventory_period_one_active",
        "inventory_period",
        ["state"],
        unique=True,
        postgresql_where=sa.text("state = 'ACTIVE'"),
    )

    # A lezárt időszak végleges, és csak akkor zárható le, ha nincs nyitott munkamenete.
    # Mivel lezárt munkamenetbe a 7-8. alkalom triggere nem enged beolvasást, a lezárt
    # időszak eredménye ezzel nem változhat meg.
    op.execute("""
        CREATE FUNCTION inventory_period_guard() RETURNS trigger AS $BODY$
        BEGIN
          IF OLD.state = 'CLOSED' THEN
            RAISE EXCEPTION 'lezart idoszak nem modosithato'
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.state = 'CLOSED' AND EXISTS (
               SELECT 1 FROM inventory_session
                WHERE period_id = NEW.id AND closed_at IS NULL) THEN
            RAISE EXCEPTION 'az idoszaknak van nyitott munkamenete'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER inventory_period_guard BEFORE UPDATE ON inventory_period
          FOR EACH ROW EXECUTE FUNCTION inventory_period_guard();
    """)
    op.execute("""
        CREATE TRIGGER inventory_period_no_delete BEFORE DELETE ON inventory_period
          FOR EACH ROW EXECUTE FUNCTION history_is_permanent();
    """)

    # Nyitott munkamenet csak aktív időszakban lehet: újat nyitni és lezártat újranyitni
    # sem lehet máshol.
    op.execute("""
        CREATE FUNCTION session_needs_active_period() RETURNS trigger AS $BODY$
        BEGIN
          IF NEW.closed_at IS NULL AND NOT EXISTS (
               SELECT 1 FROM inventory_period
                WHERE id = NEW.period_id AND state = 'ACTIVE') THEN
            RAISE EXCEPTION 'munkamenet csak aktiv idoszakban lehet nyitva'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER session_needs_active_period BEFORE INSERT OR UPDATE ON inventory_session
          FOR EACH ROW EXECUTE FUNCTION session_needs_active_period();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS session_needs_active_period ON inventory_session")
    op.execute("DROP FUNCTION IF EXISTS session_needs_active_period()")
    op.execute("DROP TRIGGER IF EXISTS inventory_period_no_delete ON inventory_period")
    op.execute("DROP TRIGGER IF EXISTS inventory_period_guard ON inventory_period")
    op.execute("DROP FUNCTION IF EXISTS inventory_period_guard()")
    op.drop_index("uq_inventory_period_one_active", table_name="inventory_period")
    op.drop_constraint("ck_inventory_period_closed_at", "inventory_period", type_="check")
    op.alter_column("inventory_period", "state", existing_type=sa.Text(), nullable=True)

    op.execute("DROP TRIGGER IF EXISTS asset_status_change_no_update_delete ON asset_status_change")
    op.execute("DROP TRIGGER IF EXISTS asset_responsible_no_delete ON asset_responsible")
    op.execute("DROP TRIGGER IF EXISTS asset_no_delete ON asset")
    op.execute("DROP FUNCTION IF EXISTS history_is_permanent()")
    op.execute("DROP TRIGGER IF EXISTS asset_status_only_via_log ON asset")
    op.execute("DROP FUNCTION IF EXISTS asset_status_only_via_log()")
    op.execute("DROP TRIGGER IF EXISTS asset_status_change_apply ON asset_status_change")
    op.execute("DROP FUNCTION IF EXISTS asset_status_change_apply()")
    op.drop_index("ix_asset_status_change_asset", table_name="asset_status_change")
    op.drop_table("asset_status_change")
    op.drop_constraint("ck_asset_status", "asset", type_="check")
    op.drop_column("asset", "status")
