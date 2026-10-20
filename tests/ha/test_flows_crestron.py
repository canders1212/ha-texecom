"""The Crestron setup screens, network and serial (flows/crestron.py)."""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.texecom.flows import validation

from .common import UDL, start


@pytest.fixture
async def crestron_port(socket_enabled):
    """Answers ASTATUS like a panel's Crestron port ("N: area 1 not armed"),
    or hangs up after it, as a bridge with its one client slot taken can."""
    state = {"answer": True, "hang_up": False}

    async def client(reader, writer):
        try:
            while data := await reader.read(256):
                if b"ASTATUS" in data and state["hang_up"]:
                    return
                if b"ASTATUS" in data and state["answer"]:
                    writer.write(b'"N\r\n')
        finally:
            writer.close()

    server = await asyncio.start_server(client, "127.0.0.1", 0)
    yield server.sockets[0].getsockname()[1], state
    server.close()


async def test_crestron_network(hass, crestron_port, no_setup):
    port, _state = crestron_port
    result = await start(hass, "crestron", "crestron_network")
    assert result["step_id"] == "crestron_network"
    udl = next(key for key in result["data_schema"].schema if key == "udl")
    assert not udl.description["suggested_value"]  # empty: sensors only, unless a code is typed
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": port, "zone_count": 5, "area_count": 1}
    )
    assert result["step_id"] == "arm_modes_crestron"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"night_part_arm": "1", "home_part_arm": "0", "keypad_arm_mode": "away", "create_dashboard": False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["udl"] is None and result["data"]["zone_count"] == 5
    assert result["options"]["keypad_arm_mode"] == "away"


async def test_crestron_no_reply(hass, crestron_port, no_setup, monkeypatch):
    port, state = crestron_port
    state["answer"] = False
    monkeypatch.setattr(validation, "CRESTRON_REPLY_TIMEOUT", 0.2)
    result = await start(hass, "crestron", "crestron_network")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": port, "zone_count": 5, "area_count": 1}
    )
    assert result["errors"] == {"base": "no_reply"}


async def test_crestron_hang_up_is_no_reply_at_once(hass, crestron_port, no_setup):
    """Something that hangs up instead of answering is "no reply" straight
    away. (Waiting on a closed connection used to spin, holding up Home
    Assistant for the whole 5 s.)"""
    port, state = crestron_port
    state["hang_up"] = True
    result = await start(hass, "crestron", "crestron_network")
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": port, "zone_count": 5, "area_count": 1}
    )
    assert result["errors"] == {"base": "no_reply"}
    assert loop.time() - started < 1


async def test_crestron_address_typo(hass, socket_enabled, no_setup):
    """A typo in the address (what Python raises for one; the tests can't
    look addresses up) is "couldn't connect", not "unknown error"."""
    result = await start(hass, "crestron", "crestron_network")
    with patch(
        "asyncio.open_connection", side_effect=UnicodeEncodeError("idna", "192.168.1..5", 10, 11, "label empty")
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.1..5", "port": 23, "zone_count": 5, "area_count": 1}
        )
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.fixture
def fake_serial():
    """serial_asyncio_fast stand-in: opens fine unless told otherwise."""
    module = types.ModuleType("serial_asyncio_fast")
    writer = MagicMock()
    module.open_serial_connection = AsyncMock(return_value=(MagicMock(), writer))
    with patch.dict(sys.modules, {"serial_asyncio_fast": module}):
        yield module


async def test_crestron_serial(hass, fake_serial, no_setup):
    result = await start(hass, "crestron", "crestron_serial")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"serial_device": "/dev/ttyUSB0", "baud_rate": "19200", "udl": UDL, "zone_count": 8, "area_count": 1},
    )
    assert result["step_id"] == "arm_modes_crestron"
    fake_serial.open_serial_connection.assert_awaited_once_with(url="/dev/ttyUSB0", baudrate=19200)


async def test_crestron_serial_cannot_open(hass, fake_serial, no_setup):
    fake_serial.open_serial_connection.side_effect = OSError("no such device")
    result = await start(hass, "crestron", "crestron_serial")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"serial_device": "/dev/ttyUSB9", "baud_rate": "19200", "zone_count": 8, "area_count": 1},
    )
    assert result["errors"] == {"base": "cannot_open_serial"}


async def test_crestron_serial_unexpected_error(hass, fake_serial, no_setup):
    fake_serial.open_serial_connection.side_effect = RuntimeError("surprise")
    result = await start(hass, "crestron", "crestron_serial")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"serial_device": "/dev/ttyUSB0", "baud_rate": "19200", "zone_count": 8, "area_count": 1},
    )
    assert result["errors"] == {"base": "unknown"}
