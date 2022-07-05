"""compress raw payload

Revision ID: 058f001e9563
Revises: 9169a7c5bda3
Create Date: 2022-07-05 20:59:28.948121

"""
from alembic import op
import sqlalchemy as sa
import pyzstd
from importlib import resources
from canadiantracker import compression

# revision identifiers, used by Alembic.
revision = "058f001e9563"
down_revision = "9169a7c5bda3"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()

    op.add_column("samples", sa.Column("raw_payload_compressed", sa.LargeBinary()))

    metadata = sa.MetaData()
    samples_table = sa.Table("samples", metadata, autoload_with=op.get_bind().engine)

    updates = []

    print(">>> Reading and compressing raw payload")
    for i, (
        index,
        sample_time,
        sku_index,
        price,
        in_promo,
        raw_payload,
        _,
    ) in enumerate(db.execute(sa.select(samples_table))):
        raw_payload_compressed = compression.zstd_compress(raw_payload.encode())
        updates.append((index, raw_payload_compressed))

        if i % 10000 == 0:
            print(f"  {i}")

    for i, (index, raw_payload_compressed) in enumerate(updates):
        db.execute(
            samples_table.update()
            .where(samples_table.c.index == index)
            .values(raw_payload_compressed=raw_payload_compressed)
        )

        if i % 10000 == 0:
            print(f"  {i}")


def downgrade():
    pass
