"""Shared fixtures for the Value IP PDU tests."""

from __future__ import annotations

import gzip

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

STATUS_XML = """<response>
<cur0>1.7</cur0>
<stat0>normal</stat0>
<curBan>1.7</curBan>
<tempBan>20</tempBan>
<humBan>48</humBan>
<statBan>normal</statBan>
<outletStat0>on</outletStat0>
<outletStat1>off</outletStat1>
<outletStat2>on</outletStat2>
<outletStat3>off</outletStat3>
<outletStat4>on</outletStat4>
<outletStat5>off</outletStat5>
<outletStat6>on</outletStat6>
<outletStat7>on</outletStat7>
<userVerifyRes>0</userVerifyRes>
</response>"""


def _gzip_response(text: str) -> web.Response:
    return web.Response(
        body=gzip.compress(text.encode("utf-8")),
        content_type="text/xml",
        headers={"Content-Encoding": "gzip"},
    )


def _make_app() -> web.Application:
    """A fake PDU: gzip status.xml + a control endpoint that records queries."""
    control_queries: list[dict[str, str]] = []

    async def handle_status(request: web.Request) -> web.Response:
        if request.app.get("fail_status"):
            return web.Response(status=500)
        return _gzip_response(STATUS_XML)

    async def handle_control(request: web.Request) -> web.Response:
        control_queries.append(dict(request.query))
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/status.xml", handle_status)
    app.router.add_get("/control_outlet.htm", handle_control)
    app["control_queries"] = control_queries
    app["fail_status"] = False
    return app


@pytest.fixture
async def pdu_client() -> TestClient:
    """TestClient against the fake PDU (session available as .session)."""
    server = TestServer(_make_app())
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


@pytest.fixture
def control_queries(pdu_client: TestClient) -> list[dict[str, str]]:
    return pdu_client.server.app["control_queries"]
