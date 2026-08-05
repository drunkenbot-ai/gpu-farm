"""Farm telemetry and cloud-usage ledger baseline."""
from alembic import op
import sqlalchemy as sa

revision = "20260805_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("farm_telemetry", sa.Column("id", sa.Integer, primary_key=True), sa.Column("recorded_at", sa.Text, nullable=False), sa.Column("worker_id", sa.Text, nullable=False), sa.Column("kind", sa.Text, nullable=False), sa.Column("payload", sa.Text, nullable=False))
    op.create_index("idx_farm_telemetry_worker_time", "farm_telemetry", ["worker_id", "recorded_at"])
    op.create_table("cloud_usage", sa.Column("job_id", sa.Text, primary_key=True), sa.Column("account_id", sa.Text, nullable=False), sa.Column("started_at", sa.Text), sa.Column("completed_at", sa.Text), sa.Column("gpu_count", sa.Integer, nullable=False, server_default="1"), sa.Column("gpu_hours", sa.Float, nullable=False, server_default="0"), sa.Column("report_status", sa.Text, nullable=False, server_default="pending"))


def downgrade() -> None:
    op.drop_table("cloud_usage")
    op.drop_index("idx_farm_telemetry_worker_time", table_name="farm_telemetry")
    op.drop_table("farm_telemetry")
