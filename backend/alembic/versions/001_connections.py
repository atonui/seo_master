"""Create the single-owner Google connection table."""

from alembic import op
import sqlalchemy as sa


revision = "001_connections"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("search_console_site", sa.String(length=512), nullable=True),
        sa.Column("ga4_property_id", sa.String(length=32), nullable=True),
        sa.Column("reconnect_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_email"),
    )


def downgrade() -> None:
    op.drop_table("google_connections")
