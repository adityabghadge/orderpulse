"""return routing and priority fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("returns", sa.Column("routing_source", sa.String(length=8), nullable=True))
    op.add_column("returns", sa.Column("routing_confidence", sa.Float(), nullable=True))
    op.add_column("returns", sa.Column("priority_score", sa.Float(), nullable=True))
    op.add_column("returns", sa.Column("escalated", sa.Boolean(), nullable=True))
    op.create_check_constraint(
        op.f("ck_returns_routing_source_valid"),
        "returns",
        "routing_source IS NULL OR routing_source IN ('rule', 'model', 'agent')",
    )
    op.create_index(
        "ix_returns_status_priority_score", "returns", ["status", "priority_score"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_returns_status_priority_score", table_name="returns")
    op.drop_constraint(op.f("ck_returns_routing_source_valid"), "returns", type_="check")
    op.drop_column("returns", "escalated")
    op.drop_column("returns", "priority_score")
    op.drop_column("returns", "routing_confidence")
    op.drop_column("returns", "routing_source")
