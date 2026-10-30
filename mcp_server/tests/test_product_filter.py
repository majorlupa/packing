"""Server-side product queries preserve full queue counts."""
import asyncio

import httpx
from helpers import FakeAPI, make_order


def test_product_query_keeps_global_counts_and_combines_filters():
    api = FakeAPI()
    orders = [make_order(id="o1"), make_order(id="o2", status="packing")]

    def handler(request):
        return httpx.Response(200, json=orders[:1] if request.url.params.get("product") else orders)

    api.routes[("GET", "/api/orders/")] = handler
    result = asyncio.run(api.tools().list_orders(product=" LEGO ", status="pending", search="Jan"))
    assert [order["id"] for order in result["orders"]] == ["o1"]
    assert result["queue_counts"] == {"pending": 1, "picking": 0, "packing": 1, "done": 0}
    assert api.last().url.params["product"] == "LEGO"


def test_blank_product_does_not_issue_an_extra_request():
    api = FakeAPI()
    api.add("GET", "/api/orders/", json_body=[])
    assert asyncio.run(api.tools().list_orders(product="  "))["count"] == 0
    assert len(api.requests) == 1
