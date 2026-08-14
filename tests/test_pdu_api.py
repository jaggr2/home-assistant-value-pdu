"""Unit tests for the VALUE IP PDU HTTP client + status.xml parser."""

from __future__ import annotations

import base64

import pytest
from aiohttp.test_utils import TestClient
from xml.etree import ElementTree

from loader import load_module

pdu_api = load_module("pdu_api", "pdu_api.py")
parse_status_xml = pdu_api.parse_status_xml
ValuePDU = pdu_api.ValuePDU
PDUSessionError = pdu_api.PDUSessionError


def test_parse_delays_html():
    html = (
        '<input name="ondly0" value="5" maxlength="3">'
        '<input name="ofdly0" value="5" maxlength="3">'
        '<input name="ondly1" value="6" maxlength="3">'
        '<input name="ofdly1" value="6" maxlength="3">'
    )
    delays = pdu_api.parse_delays_html(html)
    assert delays[0] == (5, 5)
    assert delays[1] == (6, 6)
    # Outlets absent from the page fall back to immediate switching.
    assert delays[7] == (0, 0)
    assert len(delays) == 8


async def test_fetch_delays_via_gb2312(pdu_client: TestClient):
    pdu_client.server.app["config_pdu_html"] = (
        '<input name="ondly0" value="9">'
        '<input name="ofdly0" value="4">'
    )
    client = ValuePDU(
        host=f"{pdu_client.host}:{pdu_client.port}",
        username="admin",
        password="admin",
        session=pdu_client.session,
    )
    delays = await client.async_fetch_delays()
    assert delays[0] == (9, 4)
    assert delays[7] == (0, 0)


async def test_basic_auth_header_is_well_formed():
    """Regression: encode_basic_auth() already includes 'Basic ' — do not
    prepend it again or the PDU rejects control commands with HTTP 401."""
    client = ValuePDU(
        host="192.168.1.4", username="admin", password="admin", session=object()
    )
    header = client._headers["Authorization"]
    assert header == "Basic " + base64.b64encode(b"admin:admin").decode()


def test_parse_status_xml_full():
    xml = """<response>
    <cur0>1.7</cur0>
    <stat0>normal</stat0>
    <tempBan>20</tempBan>
    <humBan>48</humBan>
    <outletStat0>on</outletStat0>
    <outletStat1>off</outletStat1>
    <outletStat2>on</outletStat2>
    <outletStat3>off</outletStat3>
    <outletStat4>on</outletStat4>
    <outletStat5>off</outletStat5>
    <outletStat6>on</outletStat6>
    <outletStat7>on</outletStat7>
    </response>"""
    snap = parse_status_xml(xml)
    assert snap.current == 1.7
    assert snap.temperature == 20
    assert snap.humidity == 48
    assert snap.status == "normal"
    assert snap.outlets == [True, False, True, False, True, False, True, True]


def test_parse_status_xml_missing_fields_degrades_gracefully():
    snap = parse_status_xml("<response/>")
    assert snap.current == 0.0
    assert snap.temperature == 0.0
    assert snap.humidity == 0.0
    assert snap.outlets == [False] * 8
    assert snap.all_off is True


def test_parse_status_xml_invalid_raises():
    with pytest.raises(ElementTree.ParseError):
        parse_status_xml("this is not xml")


async def test_fetch_status_via_gzip(pdu_client: TestClient):
    client = ValuePDU(
        host=f"{pdu_client.host}:{pdu_client.port}",
        username="admin",
        password="admin",
        session=pdu_client.session,
    )
    snap = await client.async_fetch_status()
    assert snap.current == 1.7
    assert snap.outlets[1] is False
    assert snap.outlets[7] is True


async def test_control_outlet_sends_expected_params(
    pdu_client: TestClient, control_queries: list[dict[str, str]]
):
    client = ValuePDU(
        host=f"{pdu_client.host}:{pdu_client.port}",
        username="admin",
        password="admin",
        session=pdu_client.session,
    )
    await client.async_control_outlets({0, 3}, "2")
    assert control_queries == [{"outlet0": "1", "outlet3": "1", "op": "2"}]


async def test_control_outlet_tolerates_gb2312_body(pdu_client: TestClient):
    """Regression: the device's control page is GB2312 (not UTF-8); the client
    must check the status code without decoding the body."""
    client = ValuePDU(
        host=f"{pdu_client.host}:{pdu_client.port}",
        username="admin",
        password="admin",
        session=pdu_client.session,
    )
    await client.async_control_outlets({1}, "1")


async def test_fetch_status_rejects_bad_status(pdu_client: TestClient):
    pdu_client.server.app["fail_status"] = True
    client = ValuePDU(
        host=f"{pdu_client.host}:{pdu_client.port}",
        username="admin",
        password="admin",
        session=pdu_client.session,
    )
    with pytest.raises(PDUSessionError):
        await client.async_fetch_status()
