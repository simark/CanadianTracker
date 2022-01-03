import click
import requests
import json
import pprint
import sys
import logging

import canadiantracker.triangle
import canadiantracker.storage


logger = logging.getLogger(__name__)


def print_welcome() -> None:
    click.echo(
        click.style(
            "Bienvenue chez Canadian Scrapper",
            fg="green",
            bold=True,
        )
        + " / "
        + click.style(
            "Welcome to Canadian Scrapper",
            fg="red",
            bold=True,
        )
    )


@click.group()
@click.option("-d", "--debug", is_flag=True, help="Set logging level to DEBUG")
def cli(debug: bool, args=None) -> None:
    """
    CanadianTracker tracks the inventory and prices of your favorite canadian
    retailer using the internal API that powers canadiantire.ca.

    \b
    Due to the design of the Canadian Tire API and its relatively poor
    performance, it does so in two steps implemented as two commands:
      - scrape-inventory:
        fetch static product properties (e.g. codes, description, etc.)
      - scrape-prices:
        fetch the current price of listed products

    Use --help on any of the commands for more information on their role and options.
    """
    print_welcome()
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)


@cli.command(name="scrape-inventory", short_help="fetch static product properties")
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
def scrape_inventory(db_path: str) -> None:
    """
    Fetch static product properties.
    """

    repository = canadiantracker.storage.get_product_repository_from_sqlite_file(
        db_path, should_create=True
    )
    inventory = canadiantracker.triangle.ProductInventory()

    for product_listing in inventory:
        repository.add_product_listing_entry(product_listing)


@cli.command(name="scrape-prices", short_help="fetch current product prices")
@click.option(
    "--db-path",
    required=True,
    type=str,
    metavar="PATH",
    help="Path to sqlite db instance",
)
@click.option(
    "--older-than",
    type=int,
    metavar="DAYS",
    default=1,
    show_default=True,
    help="Only scrape prices for products that were not updated in the last N days (ignored for the moment)",
)
def scrape_prices(db_path: str, older_than: int) -> None:
    """
    Fetch current product prices.
    """
    pass


if __name__ == "__main__":
    sys.exit(cli())  # pragma: no cover