"""Add Farm Manager operator audit history."""
from alembic import op
import sqlalchemy as sa

revision = "20260805_02"
down_revision = "20260805_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("farm_audit_log", sa.Column("id", sa.Integer, primary_key=True), sa.Column("recorded_at", sa.Text, nullable=False), sa.Column("actor", sa.Text, nullable=False), sa.Column("action", sa.Text, nullable=False), sa.Column("path", sa.Text, nullable=False), sa.Column("status_code", sa.Integer, nullable=False), sa.Column("client_ip", sa.Text))
    op.create_index("idx_farm_audit_time", "farm_audit_log", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("idx_farm_audit_time", table_name="farm_audit_log")
    op.drop_table("farm_audit_log")
