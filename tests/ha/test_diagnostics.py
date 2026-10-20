"""The diagnostics download (diagnostics.py)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.util import dt as dt_util

from custom_components.texecom.diagnostics import async_get_config_entry_diagnostics

from .common import setup_connect


async def test_diagnostics_hide_codes_and_address(hass, fake):
    # The panel keeps Home Assistant's local time (the test runs HA on US/Pacific).
    fake.clock_offset = dt_util.now().replace(tzinfo=None) - datetime.now()
    entry = await setup_connect(hass, fake, options={"alarm_code": "4321"})
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["udl"] == "**REDACTED**"
    assert diag["entry"]["data"]["host"] == "**REDACTED**"
    assert diag["entry"]["options"]["alarm_code"] == "**REDACTED**"
    assert diag["panel"]["connected"] is True and abs(diag["panel"]["panel_clock_drift_s"]) < 5
    assert len(diag["panel"]["zones"]) == 8
    # For mapping the panel: every area flag by name, and the raw system flags.
    assert diag["panel"]["area_flags"] == {1: ["16 Ready"]}  # disarmed, nothing open
    assert diag["panel"]["system_flags"] == "00 00 00 00 00 00 00 00"
    # The panel's recent messages (capture.py): none unrecognised from the simulated panel.
    assert isinstance(diag["panel"]["recent_messages"], list)
    assert diag["panel"]["unrecognised_messages"] == {}
    assert isinstance(diag["panel"]["message_kinds"], dict)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_hide_keypad_user_names(hass, fake):
    # People's names: users post this file in public issues. Which users have names stays.
    entry = await setup_connect(hass, fake, options={"user_names": {"3": "Sam", "4": "Alex"}})
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["options"]["user_names"] == {"3": "**REDACTED**", "4": "**REDACTED**"}
    assert "Sam" not in str(diag) and "Alex" not in str(diag)
    assert entry.options["user_names"] == {"3": "Sam", "4": "Alex"}  # the stored names are untouched
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_hide_the_address_everywhere(hass, fake):
    # Not only in the settings: the last connection error names it too.
    entry = await setup_connect(hass, fake)
    entry.runtime_data.last_error = (
        f"cannot reach 127.0.0.1:{fake.port} (Connect call failed ('127.0.0.1', {fake.port}))"
    )
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "127.0.0.1" not in str(diag)
    assert diag["panel"]["last_error"].startswith("cannot reach **REDACTED**:")
    assert await hass.config_entries.async_unload(entry.entry_id)
