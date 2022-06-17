import os
from typing import Callable, List, Union
from unicodedata import name

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.datastructures import QueryParams

import canadiantracker.storage
from canadiantracker.model import ProductInfo, ProductInfoSample, ProductListingEntry

app = FastAPI()
_db_path = os.environ["CTSERVER_SERVE_DB_PATH"]
_templates = Jinja2Templates(directory=os.path.dirname(__file__) + "/web/templates")
_repository = canadiantracker.storage.get_product_repository_from_sqlite_file(_db_path)

# Decode `foo[bar][2]` to ["foo", "bar", 2]
def decode_query_param_name(name: str) -> List[str]:
    items = []

    idx = name.find("[")
    if idx == -1:
        return [name]

    items.append(name[:idx])

    # Remove item
    name = name[idx:]

    while len(name) > 0:
        # Remove [
        name = name[1:]

        idx = name.find("]")
        if idx < 1:
            raise RuntimeError("Invalid query string")

        items.append(name[:idx])

        # Remove item
        name = name[idx:]

        # Remove ]
        name = name[1:]

    return items


def is_int(s: str):
    try:
        int(s)
        return True
    except ValueError:
        return False


def decode_query_params(query_params: QueryParams):
    ret = {}

    for k, v in query_params.items():
        items = decode_query_param_name(k)

        last_container = ret
        for i, item in enumerate(items):
            if i == len(items) - 1:
                # Last item, just value in current container
                if type(last_container) is dict:
                    last_container[item] = v
                else:
                    assert type(last_container) is list
                    idx = int(item)
                    while len(last_container) <= idx:
                        last_container.append(None)

                    last_container[idx] = v
            else:
                container_type = list if is_int(items[i + 1]) else dict

                if type(last_container) is dict:
                    if item not in last_container:
                        last_container[item] = container_type()
                    else:
                        assert type(last_container[item]) == container_type

                    last_container = last_container[item]
                else:
                    assert type(last_container) is list
                    idx = int(item)
                    while len(last_container) <= idx:
                        last_container.append(None)

                    if last_container[idx] is None:
                        last_container[idx] = container_type()
                    else:
                        assert type(last_container[idx] == container_type)

                    last_container = last_container[idx]

    return ret


@app.get("/api/products")
async def api_products(request: Request):
    ret = []

    params = decode_query_params(request.query_params)
    from pprint import pprint

    pprint(params)

    all_products = list(_repository.products)

    filtered_products = []
    search = params["search"]["value"]
    for p in all_products:
        add = False

        for c in params["columns"]:
            if c["data"] == "name":
                add = search in p.name
            elif c["data"] == "code":
                add = search in p.code
            else:
                raise RuntimeError("Invalid column")

            if add:
                filtered_products.append(p)
                break

    sorted_products = filtered_products

    for order in params["order"]:
        col_index = int(order["column"])
        column = params["columns"][col_index]

        if column["data"] == "name":
            key: Callable[[ProductListingEntry], str] = lambda x: x.name
        elif column["data"] == "code":
            key: Callable[[ProductListingEntry], str] = lambda x: x.code
        else:
            raise RuntimeError("Invalid column")

        sorted_products = sorted(
            sorted_products, key=key, reverse=order["dir"] == "desc"
        )

    start = int(params["start"])
    length = int(params["length"])
    paginated_products = sorted_products[start : start + length]

    data = []
    for p in paginated_products:
        p_data = {}
        for c in params["columns"]:
            if c["data"] == "name":
                p_data["name"] = p.name
            elif c["data"] == "code":
                p_data["code"] = p.code
            else:
                raise RuntimeError("Invalid column")

        data.append(p_data)

    return {
        "draw": int(params["draw"]),
        "recordsTotal": len(all_products),
        "recordsFiltered": len(filtered_products),
        "data": data,
    }


def serialize_product_info(info: ProductInfo):
    return {
        "price": info.price,
        "in_promo": info.in_promo,
    }


def serialize_product_info_sample(sample: ProductInfoSample):
    return {
        "sample_time": sample.sample_time,
        "product_info": serialize_product_info(sample),
    }


@app.get("/api/products/{product_id}/samples")
async def api_product_samples(product_id):
    samples = _repository.get_product_info_samples_by_code(product_id)
    return [serialize_product_info_sample(sample) for sample in samples]


@app.get("/", response_class=HTMLResponse)
async def products(request: Request):

    return _templates.TemplateResponse("index.html", {"request": request})


def sanitize_sku(listing: ProductListingEntry) -> str:
    if not listing.sku:
        return listing.code

    return listing.sku.split("|")[0]


@app.get("/products/{product_id}", response_class=HTMLResponse)
async def one_product(request: Request, product_id):
    listing = _repository.get_product_listing_by_code(product_id)

    listing.sku = sanitize_sku(listing)

    return _templates.TemplateResponse(
        "product.html", {"request": request, "listing": listing}
    )
