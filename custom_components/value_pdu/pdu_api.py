"""Async client for the VALUE IP PDU HTTP API.

The device is a Microchip TCP/IP-stack appliance that exposes a small HTTP
surface protected by HTTP Basic auth:

  GET /status.xml            → telemetry (current, temperature, humidity,
                               outlet states)
  GET /control_outlet.htm    → outlet control via query params
                                 outlet0..outlet7 = 1  (which outlets)
                                 op = 0 (ON) | 1 (OFF) | 2 (ON/OFF cycle)

Responses are gzip-encoded regardless of the Accept-Encoding header;
aiohttp transparently decodes Content-Encoding: gzip.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10

# Device protocol field names / operations (see module docstring). Kept local
# to the client so the module stays importable without the HA package.
FIELD_CURRENT = "cur0"
FIELD_TEMPERATURE = "tempBan"
FIELD_HUMIDITY = "humBan"
FIELD_STATUS = "stat0"
FIELD_OUTLET_STATE = "outletStat{index}"
OUTLET_COUNT = 8

# Per-outlet ON/OFF delays, exposed as form fields on config_PDU.htm (GB2312).
DELAY_ON_RE = re.compile(r'name="ondly(\d)"[^>]*value="(\d+)"')
DELAY_OFF_RE = re.compile(r'name="ofdly(\d)"[^>]*value="(\d+)"')


class PDUSessionError(Exception):
    """Raised when the PDU cannot be reached or returns an unexpected response."""


@dataclass
class PDUSnapshot:
    """Parsed snapshot of one status.xml poll."""

    current: float
    temperature: float
    humidity: float
    status: str
    outlets: list[bool] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def all_off(self) -> bool:
        return not any(self.outlets)


def parse_status_xml(xml_text: str) -> PDUSnapshot:
    """Parse a status.xml payload into a PDUSnapshot.

    Pure function (no I/O) so it can be unit-tested without a live device.
    Missing/empty fields degrade gracefully to 0.0 / False.
    """
    root = ElementTree.fromstring(xml_text)
    data: dict[str, str] = {}
    for child in root.iter():
        if child.text:
            data[child.tag] = child.text.strip()

    outlets: list[bool] = []
    for index in range(OUTLET_COUNT):
        outlets.append(data.get(FIELD_OUTLET_STATE.format(index=index)) == "on")

    def _float(key: str) -> float:
        try:
            return float(data.get(key, ""))
        except (TypeError, ValueError):
            return 0.0

    return PDUSnapshot(
        current=_float(FIELD_CURRENT),
        temperature=_float(FIELD_TEMPERATURE),
        humidity=_float(FIELD_HUMIDITY),
        status=data.get(FIELD_STATUS, "unknown"),
        outlets=outlets,
        raw=data,
    )


def parse_delays_html(html: str) -> dict[int, tuple[int, int]]:
    """Parse per-outlet (on_delay, off_delay) seconds from config_PDU.htm.

    Pure function (no I/O) so it can be unit-tested. Missing outlets default
    to (0, 0) — i.e. immediate switching.
    """
    on_delays = {int(i): int(v) for i, v in DELAY_ON_RE.findall(html)}
    off_delays = {int(i): int(v) for i, v in DELAY_OFF_RE.findall(html)}
    return {
        index: (on_delays.get(index, 0), off_delays.get(index, 0))
        for index in range(OUTLET_COUNT)
    }


class ValuePDU:
    """HTTP client for a single VALUE IP PDU."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host.rstrip("/")
        self._base_url = f"http://{self._host}"
        # encode_basic_auth() already returns the full "Basic <b64>" header value.
        self._headers = {"Authorization": aiohttp.encode_basic_auth(username, password)}
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def async_fetch_status(self) -> PDUSnapshot:
        """Fetch and parse status.xml."""
        text = await self._async_get_text("/status.xml")
        try:
            return parse_status_xml(text)
        except ElementTree.ParseError as err:
            raise PDUSessionError(f"Invalid status.xml response: {err}") from err

    async def async_control_outlets(self, outlets: set[int], op: str) -> None:
        """Apply operation `op` to the given 0-based outlet indices.

        op: "0" (ON), "1" (OFF) or "2" (ON/OFF cycle).
        Raises PDUSessionError if the PDU does not acknowledge with HTTP 200.
        """
        params = {f"outlet{index}": "1" for index in outlets}
        params["op"] = op
        await self._async_ensure_ok("/control_outlet.htm", params=params)

    async def async_fetch_delays(self) -> dict[int, tuple[int, int]]:
        """Fetch per-outlet ON/OFF delays (seconds) from config_PDU.htm.

        The page is served in GB2312; it is decoded before parsing.
        """
        url = f"{self._base_url}/config_PDU.htm"
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=self._timeout
            ) as response:
                if response.status != 200:
                    raise PDUSessionError(f"HTTP {response.status} from {url}")
                body = await response.read()
        except aiohttp.ClientError as err:
            raise PDUSessionError(f"Cannot reach {url}: {err}") from err
        except TimeoutError as err:
            raise PDUSessionError(f"Timeout reaching {url}") from err
        return parse_delays_html(body.decode("gb2312", errors="replace"))

    async def _async_ensure_ok(self, path: str, params: dict[str, str] | None = None) -> None:
        """GET a path and raise if it is not HTTP 200.

        The body is read but NOT decoded: the device serves the control page
        in GB2312, whose bytes are not valid UTF-8.
        """
        try:
            async with self._session.get(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers,
                timeout=self._timeout,
            ) as response:
                if response.status != 200:
                    raise PDUSessionError(
                        f"HTTP {response.status} from {self._base_url}{path}"
                    )
                await response.read()
        except aiohttp.ClientError as err:
            raise PDUSessionError(f"Cannot reach {self._base_url}{path}: {err}") from err
        except TimeoutError as err:
            raise PDUSessionError(f"Timeout reaching {self._base_url}{path}") from err

    async def _async_get_text(self, path: str, params: dict[str, str] | None = None) -> str:
        try:
            async with self._session.get(
                f"{self._base_url}{path}",
                params=params,
                headers=self._headers,
                timeout=self._timeout,
            ) as response:
                if response.status != 200:
                    raise PDUSessionError(
                        f"HTTP {response.status} from {self._base_url}{path}"
                    )
                return await response.text()
        except aiohttp.ClientError as err:
            raise PDUSessionError(f"Cannot reach {self._base_url}{path}: {err}") from err
        except TimeoutError as err:
            raise PDUSessionError(f"Timeout reaching {self._base_url}{path}") from err

    def _log_command(self, outlets: set[int], op: str) -> None:
        _LOGGER.debug("PDU command: outlets=%s op=%s", sorted(outlets), op)


# Re-export for convenience in the rest of the integration.
__all__ = ["PDUSnapshot", "PDUSessionError", "ValuePDU", "parse_status_xml"]
