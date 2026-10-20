"""Persist aggregate marketing reports."""

from alembic import op
import sqlalchemy as sa


revision = "003_reports"
down_revision = "002_reporting_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column("source_timestamps", sa.JSON(), nullable=False),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_saved_reports_created_at", "saved_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_saved_reports_created_at", table_name="saved_reports")
    op.drop_table("saved_reports")
