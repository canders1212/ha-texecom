"""Repairs notices (issues.py): the panel clock, the panel being
unreachable, and messages the integration doesn't recognise."""

from __future__ import annotations

import time
from datetime import timedelta

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.texecom.diagnostics import async_get_config_entry_diagnostics

from .common import setup_connect, wait_for


async def test_a_clock_with_an_impossible_date(hass, fake):
    fake.clock_raw = bytes([0, 0, 0, 0, 0, 0])  # day 0, month 0
    entry = await setup_connect(hass, fake)
    issue = ir.async_get(hass).async_get_issue("texecom", f"panel_clock_{entry.entry_id}")
    assert issue is not None and issue.translation_placeholders["drift"].startswith("not set")
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["panel"]["panel_clock"].startswith("unreadable")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_offline_repair_notice(hass, fake):
    entry = await setup_connect(hass, fake)
    panel = entry.runtime_data
    await fake.close()
    await wait_for(lambda: not panel.connected)
    panel.disconnected_since = time.monotonic() - 16 * 60
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue("texecom", f"panel_offline_{entry.entry_id}")
    assert issue is not None and issue.translation_placeholders["minutes"] == "16"
    panel.set_connected(True)  # back again
    assert ir.async_get(hass).async_get_issue("texecom", f"panel_offline_{entry.entry_id}") is None
    panel.set_connected(False)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unrecognised_messages_ask_to_share_once(hass, fake):
    entry = await setup_connect(hass, fake)
    panel = entry.runtime_data
    issue_id = f"unrecognised_messages_{entry.entry_id}"
    registry = ir.async_get(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert registry.async_get_issue("texecom", issue_id) is None  # nothing new: no notice

    fake.send_log(250, 1, 7)  # a log type nobody has named
    fake.send(bytes([9, 1, 2, 3]))  # a message kind nobody knows
    await wait_for(lambda: len(panel.capture.unrecognised) == 2)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=22))
    await hass.async_block_till_done()
    issue = registry.async_get_issue("texecom", issue_id)
    assert issue is not None and issue.severity == ir.IssueSeverity.WARNING and not issue.is_fixable
    assert issue.translation_placeholders["count"] == "2"
    assert issue.learn_more_url.endswith("template=3-data.yml")

    # Ignored once, it stays ignored: more unknown messages, a reload of the entry.
    ir.async_ignore_issue(hass, "texecom", issue_id, True)
    fake.send_log(251, 1, 7)
    await wait_for(lambda: len(panel.capture.unrecognised) == 3)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=33))
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    issue = registry.async_get_issue("texecom", issue_id)
    assert issue is not None and issue.dismissed_version is not None
