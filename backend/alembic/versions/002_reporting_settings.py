"""Add GA4 funnel event mappings."""

from alembic import op
import sqlalchemy as sa


revision = "002_reporting_settings"
down_revision = "001_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("google_connections", sa.Column("site_url", sa.String(length=512), nullable=True))
    op.add_column("google_connections", sa.Column("cta_event", sa.String(length=100), nullable=True))
    op.add_column("google_connections", sa.Column("invite_submit_event", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("google_connections", "invite_submit_event")
    op.drop_column("google_connections", "cta_event")
    op.drop_column("google_connections", "site_url")
