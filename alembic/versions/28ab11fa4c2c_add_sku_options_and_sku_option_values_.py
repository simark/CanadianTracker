"""add sku_options and sku_option_values tables

Revision ID: 28ab11fa4c2c
Revises: ac8256c291d4
Create Date: 2022-11-07 19:41:42.694998

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "28ab11fa4c2c"
down_revision = "ac8256c291d4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sku_options",
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("product_index", sa.Integer, nullable=False),
        sa.Column("descriptor", sa.String, nullable=False),
        sa.Column("display", sa.String, nullable=False),
        sa.PrimaryKeyConstraint("index"),
        sa.ForeignKeyConstraint(
            ["product_index"],
            ["products_static.index"],
        ),
    )

    op.create_table(
        "sku_option_values",
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("sku_option_index", sa.Integer, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.Column("id", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("index"),
        sa.ForeignKeyConstraint(
            ["sku_option_index"],
            ["sku_options.index"],
        ),
    )

    op.create_table(
        "skus_to_sku_option_values_rel",
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("sku_index", sa.Integer, nullable=False),
        sa.Column("sku_option_value_index", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("index"),
        sa.ForeignKeyConstraint(
            ["sku_index"],
            ["skus.index"],
        ),
        sa.ForeignKeyConstraint(
            ["sku_index"],
            ["sku_options_values.index"],
        ),
    )


def downgrade():
    pass
