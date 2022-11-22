from __future__ import annotations

import datetime
import decimal
import logging
import os
from collections.abc import Iterator
from typing import Iterable

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from canadiantracker import model

logger = logging.getLogger(__name__)


class _Base(orm.DeclarativeBase):
    metadata = sqlalchemy.MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class _AlembicRevision(_Base):
    __tablename__ = "alembic_version"

    version_num = sqlalchemy.Column(sqlalchemy.String, primary_key=True)


class _StorageProduct(_Base):
    # static product properties
    __tablename__ = "products_static"

    index: Mapped[int] = mapped_column(primary_key=True, unique=True, index=True)
    name: Mapped[str]
    code: Mapped[str] = mapped_column(unique=True)
    is_in_clearance: Mapped[bool | None]
    # last time this entry was returned when listing the inventory
    # this will be used to prune stale product entries
    last_listed: Mapped[datetime.datetime | None]
    url: Mapped[str | None]

    skus: Mapped[list[_StorageSku]] = relationship(back_populates="product")

    sku_options: Mapped[list[_StorageSkuOption]] = relationship(
        back_populates="product"
    )

    def __init__(self, name: str, code: str, is_in_clearance: bool, url: str):
        self.name = name
        self.code = code
        self.is_in_clearance = is_in_clearance
        self.last_listed = datetime.datetime.now()
        self.url = url


class _StorageSku(_Base):
    # skus table
    __tablename__ = "skus"

    index: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str]
    formatted_code: Mapped[str | None]
    product_index: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("products_static.index")
    )

    product: Mapped[_StorageProduct] = relationship(back_populates="skus")

    samples: Mapped[list[_StorageProductSample]] = relationship(back_populates="sku")

    def __init__(
        self,
        code: str,
        formatted_code: str,
        product: _StorageProduct,
    ):
        self.code = code
        self.formatted_code = formatted_code
        self.product = product

    def __repr__(self):
        return (
            "_StorageSku("
            + ", ".join(
                [
                    f"code={self.code}",
                    f"formatted_code={self.formatted_code}",
                    f"product_index={self.product_index}",
                ]
            )
            + ")"
        )


class _StorageSkuOption(_Base):
    __tablename__ = "sku_options"

    index: Mapped[int] = mapped_column(primary_key=True)
    product_index: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("products_static.index")
    )
    descriptor: Mapped[str]
    display: Mapped[str]

    product: Mapped[_StorageProduct] = relationship(back_populates="sku_options")
    values: Mapped[list[_StorageSkuOptionValue]] = relationship(back_populates="option")

    def __init__(self, product: _StorageProduct, descriptor: str, display: str):
        assert product is not None
        assert descriptor is not None
        assert display is not None
        self.product = product
        self.descriptor = descriptor
        self.display = display

    def __repr__(self):
        return (
            "_StorageSkuOption("
            + ", ".join(
                [
                    f"product_index={self.product_index}",
                    f"descriptor={self.descriptor}",
                    f"display={self.display}",
                ]
            )
            + ")"
        )


class _StorageSkuOptionValue(_Base):
    __tablename__ = "sku_option_values"

    index: Mapped[int] = mapped_column(primary_key=True)
    sku_option_index: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("sku_options.index")
    )
    value: Mapped[str]
    id: Mapped[int]

    option: Mapped[_StorageSkuOption] = relationship(back_populates="values")

    def __init__(self, option: _StorageSkuOption, value: str, id: int):
        assert option is not None
        assert value is not None
        assert id is not None
        self.option = option
        self.value = value
        self.id = id

    def __repr__(self):
        return (
            "_StorageSkuOptionValue("
            + ", ".join(
                [
                    f"sku_option_index={self.sku_option_index}",
                    f"value={self.value}",
                    f"id={self.id}",
                ]
            )
            + ")"
        )


class _StorageProductSample(_Base):
    # sample of dynamic product properties
    __tablename__ = "samples"

    index: Mapped[int] = mapped_column(primary_key=True, unique=True, index=True)
    sample_time: Mapped[datetime.date]
    sku_index: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("skus.index"),
        index=True,
    )
    in_promo: Mapped[bool]
    raw_payload: Mapped[str | None]
    price_cents: Mapped[int]

    sku: Mapped[list[_StorageSku]] = relationship(back_populates="samples")

    def __init__(
        self,
        price: decimal.Decimal,
        in_promo: bool,
        raw_payload: dict,
        sku: _StorageSku,
    ):
        self.price_cents = int(price * 100)
        self.in_promo = in_promo
        self.raw_payload = str(raw_payload)
        self.sample_time = datetime.datetime.now()
        self.sku = sku

    @property
    def price(self) -> decimal.Decimal:
        return decimal.Decimal(self.price_cents) / 100

    def __repr__(self):
        return (
            "_StorageProductSample("
            + ", ".join(
                [
                    f"index={self.index}",
                    f"sample_time={self.sample_time}",
                    f"sku_index={self.sku_index}",
                    f"price_cents={self.price_cents}",
                ]
            )
            + ")"
        )


class InvalidDatabaseRevisionException(Exception):
    def __init__(self, msg: str):
        self._msg = msg

    def __str__(self):
        return f"Failed to validate database revision: {self._msg}"


class ProductRepository:
    ALEMBIC_REVISION = "28ab11fa4c2c"

    def __init__(self, path: str):
        db_url = "sqlite:///" + os.path.abspath(path)
        logger.debug(f"Creating ProductRepository with url {db_url}")
        self._engine = sqlalchemy.create_engine(db_url, echo=False)
        inspector: sqlalchemy.engine.reflection.Inspector = sqlalchemy.inspect(
            self._engine
        )
        if not inspector.has_table("alembic_version"):
            raise InvalidDatabaseRevisionException(
                "database is missing the alembic_version table"
            )

        self._session: sqlalchemy.Session = orm.sessionmaker(bind=self._engine)()

        revs: list[_AlembicRevision] = self._session.query(_AlembicRevision).all()

        if len(revs) == 0:
            raise InvalidDatabaseRevisionException("table alembic_revision is empty")

        rev = revs[0].version_num
        if rev != self.ALEMBIC_REVISION:
            raise InvalidDatabaseRevisionException(
                f"expected {self.ALEMBIC_REVISION}, got {rev}"
            )

    def __del__(self):
        if hasattr(self, "_session"):
            self._session.commit()

    def products(self, codes: Iterable[str] | None = None) -> Iterator[model.Product]:
        q = self._session.query(_StorageProduct)

        if codes is not None:
            q = q.filter(_StorageProduct.code.in_(codes))

        return q

    @property
    def skus(self) -> Iterator[model.Sku]:
        return self._session.query(_StorageSku)

    @property
    def samples(self) -> Iterator[model.ProductInfoSample]:
        # Use "yield_per" to prevent SQLAlchemy from instantiting objects for
        # all samples at once.
        return self._session.query(_StorageProductSample).yield_per(10000)

    def flush(self):
        self._session.flush()

    def vacuum(self):
        # Vacuum can't be run during a transaction; complete the current
        # transaction before vacuuming.
        #
        # FIXME This may be a bit surprising, should the API ask that users
        # commit explicitly (adding a new method) to make sure they are aware
        # of the risks? 😏
        if self._session.in_transaction():
            self._session.commit()
        self._session.execute("VACUUM")

    def get_product_by_code(self, product_id: str) -> model.Product:
        result = self.products().filter(_StorageProduct.code == product_id)
        return result.first() if result else None

    def get_sku_by_code(self, code: str) -> _StorageSku:
        result = self.skus.filter(_StorageSku.code == code)
        return result.first() if result else None

    def get_sku_by_formatted_code(self, sku_formatted_code: str) -> model.Sku:
        result = self.skus.filter(_StorageSku.formatted_code == sku_formatted_code)
        return result.first() if result else None

    def get_product_info_samples_by_code(
        self, product_id: str
    ) -> Iterator[model.ProductInfoSample]:
        result = (
            self._session.query(_StorageProductSample)
            .filter(_StorageProductSample.code == product_id)
            .order_by(_StorageProductSample.sample_time)
        )
        return result.all() if result else None

    def add_product(self, product: model.Product) -> None:
        logger.debug("Attempting to add product: code = `%s`", product.code)
        entry = (
            self._session.query(_StorageProduct).filter_by(code=product.code).first()
        )
        logger.debug("Product %s present in storage", "is" if entry else "is not")

        if not entry:
            self._session.add(
                _StorageProduct(
                    product.name,
                    product.code.upper(),
                    product.is_in_clearance,
                    product.url,
                )
            )
        else:
            # update last listed time
            entry.last_listed = datetime.datetime.now()

            # Update URL, name and "in clearance" status, these can change over
            # time.
            if entry.url != product.url:
                entry.url = product.url

            if entry.name != product.name:
                entry.name = product.name

            if entry.is_in_clearance != product.is_in_clearance:
                entry.is_in_clearance = product.is_in_clearance

    def sku_options(self, product: model.Product) -> Iterator[model.SkuOption]:
        product_row = (
            self._session.query(_StorageProduct)
            .filter(_StorageProduct.code == product.code)
            .one_or_none()
        )
        if product_row is None:
            raise RuntimeError(f"Product with code {product.code} not found in storage")

        option_rows: Iterator[_StorageSkuOption] = self._session.query(
            _StorageSkuOption
        ).filter(_StorageSkuOption.product_index == product_row.index)

        options = []
        for option_row in option_rows:
            value_rows = self._session.query(_StorageSkuOptionValue).filter(
                _StorageSkuOptionValue.sku_option_index == option_row.index
            )

            values = []
            for value_row in value_rows:
                values.append(model.SkuOptionValue(value_row.id, value_row.value))

            options.append(
                model.SkuOption(option_row.descriptor, option_row.display, values)
            )

        return options

    @staticmethod
    def compare_options(
        user_options: list[model.SkuOption],
        storage_options: list[_StorageSkuOption],
    ) -> bool:
        if len(user_options) != len(storage_options):
            return False

        user_options = sorted(user_options, key=lambda x: x.descriptor)
        storage_options = sorted(storage_options, key=lambda x: x.descriptor)

        for user_option, storage_option in zip(user_options, storage_options):
            if (
                user_option.descriptor != storage_option.descriptor
                or user_option.display != storage_option.display
            ):
                return False

            user_values = user_option.values
            storage_values = storage_option.values

            if len(user_values) != len(storage_values):
                return False

            user_values = sorted(user_values, key=lambda x: x.id)
            storage_values = sorted(storage_values, key=lambda x: x.id)

            for user_value, storage_value in zip(user_values, storage_values):
                if (
                    user_value.id != storage_value.id
                    or user_value.value != storage_value.value
                ):
                    return False

        return True

    def set_sku_options(
        self,
        product: model.Product,
        options: list[model.SkuOption],
    ) -> None:
        logger.debug(f"Set SKU options for product {product.code}")
        product_row = (
            self._session.query(_StorageProduct)
            .filter(_StorageProduct.code == product.code)
            .one_or_none()
        )
        if product_row is None:
            raise RuntimeError(f"Product with code {product.code} not found in storage")

        storage_options: list[_StorageSkuOption] = (
            self._session.query(_StorageSkuOption)
            .filter(_StorageSkuOption.product == product_row)
            .all()
        )

        if ProductRepository.compare_options(options, storage_options):
            logger.debug("    All equal")
            return

        logger.debug("    Not equal, adding")
        for storage_option in storage_options:
            for storage_value in storage_option.values:
                self._session.delete(storage_value)

            self._session.delete(storage_option)

        for option in options:
            option_row = _StorageSkuOption(product, option.descriptor, option.display)
            self._session.add(option_row)

            for value in option.values:
                self._session.add(
                    _StorageSkuOptionValue(option_row, value.value, value.id)
                )

    def add_sku(
        self,
        product: model.Product,
        sku: model.Sku,
    ) -> None:
        sku_entry: _StorageSku | None = (
            self._session.query(_StorageSku).filter_by(code=sku.code).first()
        )

        if sku_entry is None:
            logger.debug(f"  SKU {sku.code} not present in storage, adding")
            # Create a new sku entry.
            product_entry = self.get_product_by_code(product.code)
            assert product_entry is not None
            self._session.add(_StorageSku(sku.code, sku.formatted_code, product_entry))
        else:
            logger.debug(f"  SKU {sku.code} is already present")
            if sku_entry.product.code != product.code:
                # A sku with this code already exists, but it is
                # associated with a different product. These kind of "migrations"
                # happen periodically when a sku is re-parented to a different
                # product (typically because it changed names). In this case,
                # edit the existing entry.
                logger.debug(
                    f"  SKU {sku.code} is associated to a different product: previous product was '{sku_entry.product.name} ({sku_entry.product.code})', new product is '{product.name} ({product.code})'"
                )
                sku_entry.product = product

    def add_product_price_samples(
        self,
        product_infos: Iterator[model.ProductInfo],
        discard_equal: bool,
    ):
        for info in product_infos:
            # Some responses have null as the current price.
            price = info.price
            if price is None:
                continue

            sku = self.get_sku_by_code(info.code)
            assert sku

            logger.debug(f"adding sample for {sku}")

            if discard_equal:
                last_sample = (
                    self._session.query(_StorageProductSample)
                    .filter(_StorageProductSample.sku_index == sku.index)
                    .order_by(_StorageProductSample.sample_time.desc())
                    .limit(1)
                    .one_or_none()
                )

                if last_sample:
                    equal = price == last_sample.price
                    logger.debug(
                        f"last price={last_sample.price}, new price={price}, equal={equal}"
                    )

                    if equal:
                        self._session.delete(last_sample)
                else:
                    logger.debug("no previous sample found")

            new_sample = _StorageProductSample(
                price=price,
                in_promo=info.in_promo,
                raw_payload=info.raw_payload,
                sku=sku,
            )
            self._session.add(new_sample)

    def delete_sample(self, sample: model.ProductInfoSample):
        self._session.delete(sample)


def get_product_repository_from_sqlite_file(path: str) -> ProductRepository:
    return ProductRepository(path)
