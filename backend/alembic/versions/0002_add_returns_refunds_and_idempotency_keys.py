"""add returns refunds and idempotency keys

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("return_number_seq", start=500000)))
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_idempotency_keys")),
    )
    op.create_index(
        op.f("ix_idempotency_keys_created_at"), "idempotency_keys", ["created_at"], unique=False
    )
    op.create_table(
        "returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "return_number",
            sa.String(length=20),
            server_default=sa.text("'RT-' || nextval('return_number_seq')"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("order_item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assigned_team", sa.String(length=24), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assigned_team IS NULL OR assigned_team IN ('logistics', 'quality', 'fulfillment', 'customer_care')",
            name=op.f("ck_returns_team_valid"),
        ),
        sa.CheckConstraint(
            "reason_code IN ('damaged', 'defective', 'wrong_item', 'missing_parts', 'not_as_described', 'size_fit', 'late_delivery', 'changed_mind')",
            name=op.f("ck_returns_reason_code_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected', 'received', 'refunded')",
            name=op.f("ck_returns_status_valid"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_returns_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_returns_order_id_orders")
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"], ["order_items.id"], name=op.f("fk_returns_order_item_id_order_items")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_returns")),
        sa.UniqueConstraint("return_number", name=op.f("uq_returns_return_number")),
    )
    op.create_index(op.f("ix_returns_order_id"), "returns", ["order_id"], unique=False)
    op.create_index(op.f("ix_returns_order_item_id"), "returns", ["order_item_id"], unique=False)
    op.create_index(
        "ix_returns_status_requested_at", "returns", ["status", "requested_at"], unique=False
    )
    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_reference", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_cents > 0", name=op.f("ck_refunds_amount_positive")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_refunds_order_id_orders")
        ),
        sa.ForeignKeyConstraint(
            ["return_id"], ["returns.id"], name=op.f("fk_refunds_return_id_returns")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        sa.UniqueConstraint("provider_reference", name=op.f("uq_refunds_provider_reference")),
        sa.UniqueConstraint("return_id", name=op.f("uq_refunds_return_id")),
    )
    op.create_index(op.f("ix_refunds_order_id"), "refunds", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_refunds_order_id"), table_name="refunds")
    op.drop_table("refunds")
    op.drop_index("ix_returns_status_requested_at", table_name="returns")
    op.drop_index(op.f("ix_returns_order_item_id"), table_name="returns")
    op.drop_index(op.f("ix_returns_order_id"), table_name="returns")
    op.drop_table("returns")
    op.drop_index(op.f("ix_idempotency_keys_created_at"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.execute(sa.schema.DropSequence(sa.Sequence("return_number_seq")))
