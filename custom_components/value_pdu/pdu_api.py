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
        self._headers = {
            "Authorization": f"Basic {aiohttp.encode_basic_auth(username, password)}"
        }
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
        await self._async_get_text("/control_outlet.htm", params=params)

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
