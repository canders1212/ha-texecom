"""The "Alarm not set" notification (notifications.py)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components import persistent_notification
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import setup_connect, wait_for


async def test_failed_arm_is_explained(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.send_log(85, 0, 4)  # ARM_FAILED: Kitchen active at the end of the exit time
    fake.send_log(85, 0, 2)  # ...and the Hallway
    await wait_for(lambda: len(_notes(hass)) == 1 and "Hallway" in next(iter(_notes(hass).values()))["message"])
    note = next(iter(_notes(hass).values()))
    assert "Kitchen" in note["message"] and note["title"] == "Alarm not set"
    fake.set_area(3)  # armed on the next try: the notice goes
    await wait_for(lambda: not _notes(hass))
    assert await hass.config_entries.async_unload(entry.entry_id)


def _notes(hass):
    return {
        key: value
        for key, value in persistent_notification._async_get_or_create_notifications(hass).items()
        if key.startswith("texecom_arm_failed")
    }


def _notice(hass, kind: str, entry) -> dict | None:
    return persistent_notification._async_get_or_create_notifications(hass).get(f"texecom_{kind}_{entry.entry_id}")


async def test_mains_notice_while_on_battery(hass, fake):
    entry = await setup_connect(hass, fake)
    assert _notice(hass, "mains", entry) is None
    fake.on_battery = True
    await entry.runtime_data.read_power()
    await entry.runtime_data.read_power()  # two readings in a row: one can be a blip
    await hass.async_block_till_done()
    assert _notice(hass, "mains", entry) is None  # not yet: short power blips aren't worth a notice
    await _minutes_pass(hass, 3)
    note = _notice(hass, "mains", entry)
    assert note is not None and note["title"] == "Alarm panel on battery"
    await entry.runtime_data.read_power()  # still on battery: the same notice, not a new one
    fake.on_battery = False
    await entry.runtime_data.read_power()
    await hass.async_block_till_done()
    assert _notice(hass, "mains", entry) is None  # gone once the mains is back
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_short_power_blip_shows_no_notice(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.on_battery = True
    await entry.runtime_data.read_power()
    await entry.runtime_data.read_power()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.texecom_mains_power").state == "off"  # the sensor still says so at once
    assert _notice(hass, "mains", entry) is None
    fake.on_battery = False  # back within a minute (#51's log: 33 seconds)
    await entry.runtime_data.read_power()
    await hass.async_block_till_done()
    await _minutes_pass(hass, 3)
    assert _notice(hass, "mains", entry) is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def _minutes_pass(hass, minutes: int) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=minutes))
    await hass.async_block_till_done()


async def test_tamper_notice_says_what_to_check(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.send_log(60, 11, 0, areas=0)  # the panel's lid
    fake.send_log(62, 11, 0, areas=0)  # a detector's cover (the shared tamper circuit)
    await wait_for(lambda: "Auxiliary Tamper" in (_notice(hass, "tamper", entry) or {}).get("message", ""))
    note = _notice(hass, "tamper", entry)
    assert note["title"] == "Alarm tamper"
    assert "the panel's lid is open" in note["message"] and "a detector's cover is open" in note["message"]
    fake.send_log(60, 12, 0, areas=0)
    await wait_for(lambda: "Panel Box Tamper" not in _notice(hass, "tamper", entry)["message"])
    fake.send_log(62, 12, 0, areas=0)
    await wait_for(lambda: _notice(hass, "tamper", entry) is None)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_tamper_notice_names_a_tampered_zone(hass, fake):
    """A zone with its own tamper (a wireless detector, or one wired with its
    tamper in the zone) is named, not left to its hidden-away Tamper sensor."""
    entry = await setup_connect(hass, fake)
    fake.set_zone(5, 0x02)
    await wait_for(lambda: _notice(hass, "tamper", entry) is not None)
    assert "**Patio Door**: its detector's cover is open" in _notice(hass, "tamper", entry)["message"]
    fake.set_zone(5, 0x00)
    await wait_for(lambda: _notice(hass, "tamper", entry) is None)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_tamper_the_panel_doesnt_log_is_explained(hass, fake):
    """Seen on a real panel: a detector's cover opened, the internal sounder
    went off, but no tamper was logged. The notice says to look at the keypad."""
    entry = await setup_connect(hass, fake)
    fake.open_tamper(62, logged=False)
    await entry.runtime_data.refresh_areas()  # the next regular read
    await wait_for(lambda: _notice(hass, "tamper", entry) is not None)
    note = _notice(hass, "tamper", entry)
    assert "**Internal Alarm**" in note["message"] and "The keypad shows what it is" in note["message"]
    assert hass.states.get("binary_sensor.texecom_tamper").attributes["sources"] == ["Internal Alarm"]
    fake.send_user(1)  # a code at the keypad silences it
    await wait_for(lambda: _notice(hass, "tamper", entry) is None)
    assert hass.states.get("binary_sensor.texecom_tamper").state == "off"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_notices_can_be_turned_off(hass, fake):
    entry = await setup_connect(hass, fake, options={"notify_mains": False, "notify_tamper": False})
    fake.on_battery = True
    await entry.runtime_data.read_power()
    await entry.runtime_data.read_power()  # two readings in a row: one can be a blip
    fake.send_log(60, 11, 0, areas=0)
    await wait_for(lambda: hass.states.get("binary_sensor.texecom_tamper").state == "on")
    assert hass.states.get("binary_sensor.texecom_mains_power").state == "off"
    assert _notice(hass, "mains", entry) is None and _notice(hass, "tamper", entry) is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_notices_go_when_the_integration_unloads(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.send_log(60, 11, 0, areas=0)
    await wait_for(lambda: _notice(hass, "tamper", entry) is not None)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert _notice(hass, "tamper", entry) is None


async def test_a_failed_arm_isnt_forgotten_because_another_area_is_armed(hass, socket_enabled):
    """With two areas, the garage being armed doesn't remove the notice that
    the house didn't arm; the house arming does."""
    from fake_connect_panel import DEMO_ZONES, TWO_AREAS, FakeConnectPanel, with_garage_area

    fake = FakeConnectPanel(zones=with_garage_area(DEMO_ZONES), areas=TWO_AREAS, exit_delay=0.05)
    await fake.start()
    try:
        entry = await setup_connect(hass, fake)
        fake.set_area(3, area=2)  # the garage is armed
        await wait_for(lambda: hass.states.get("alarm_control_panel.texecom_garage").state == "armed_away")
        fake.send_log(85, 0, 4, areas=1)  # the house didn't arm: Kitchen
        await wait_for(lambda: _notes(hass))
        fake.set_zone(2, 1)  # anything else the panel reports meanwhile
        fake.set_area(1, area=2)  # even the garage arming again
        fake.set_area(3, area=2)
        await hass.async_block_till_done()
        await wait_for(lambda: hass.states.get("binary_sensor.texecom_hallway").state == "on")
        assert _notes(hass)
        fake.set_area(3, area=1)  # the house arms on the next try
        await wait_for(lambda: not _notes(hass))
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await fake.close()
