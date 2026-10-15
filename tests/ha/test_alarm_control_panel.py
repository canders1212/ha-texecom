"""The alarm (alarm_control_panel.py): arming, disarming, codes and who
changed it. A Crestron entry's alarm is covered in test_init.py."""

from __future__ import annotations

import pytest
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_track_state_change_event

from custom_components.texecom.connect import protocol as P

from .common import ALARM, setup_connect, state, wait_for


async def call(hass, service: str, code: str | None = None) -> None:
    data = {"entity_id": ALARM}
    if code is not None:
        data["code"] = code
    await hass.services.async_call("alarm_control_panel", service, data, blocking=True)


async def test_vacation_and_custom_bypass_use_their_part_arms(hass, fake):
    """Issue #32: each of the three part arms can have its own button."""
    options = {"night_part_arm": 1, "home_part_arm": 0, "vacation_part_arm": 2, "custom_bypass_part_arm": 3}
    entry = await setup_connect(hass, fake, options=options)
    assert hass.states.get(ALARM).attributes["supported_features"] == 2 | 4 | 16 | 32
    await call(hass, "alarm_arm_vacation")
    assert (P.CMD_ARM_AREA, bytes([2, 1])) in fake.commands  # Part Arm 2, area 1
    await wait_for(lambda: state(hass) == "armed_vacation")
    await call(hass, "alarm_disarm")
    await wait_for(lambda: state(hass) == "disarmed")
    await call(hass, "alarm_arm_custom_bypass")
    assert (P.CMD_ARM_AREA, bytes([3, 1])) in fake.commands  # Part Arm 3
    await wait_for(lambda: state(hass) == "armed_custom_bypass")
    assert hass.states.get(ALARM).attributes["part_arm"] == 3
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_arming_says_what_its_arming_to(hass, fake):
    """Discussion #38: for automations, while arming."""
    from fake_connect_panel import run_command

    entry = await setup_connect(hass, fake)
    assert hass.states.get(ALARM).attributes["arming_to"] is None
    run_command(fake, "area exit part 1")
    await wait_for(lambda: state(hass) == "arming")
    await wait_for(lambda: hass.states.get(ALARM).attributes["arming_to"] == "armed_night")
    run_command(fake, "area part 1")
    await wait_for(lambda: state(hass) == "armed_night")
    assert hass.states.get(ALARM).attributes["arming_to"] is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_arm_night_away_and_disarm(hass, fake):
    entry = await setup_connect(hass, fake)
    await call(hass, "alarm_arm_night")
    assert (P.CMD_ARM_AREA, bytes([1, 1])) in fake.commands  # Part Arm 1, area 1
    await wait_for(lambda: state(hass) == "armed_night")
    attrs = hass.states.get(ALARM).attributes
    assert attrs["part_arm"] == 1 and attrs["changed_by"] == "Home Assistant"

    seen: list[str] = []

    @callback
    def record(event):
        seen.append(event.data["new_state"].state)

    unsub = async_track_state_change_event(hass, [ALARM], record)
    await call(hass, "alarm_arm_away")
    await wait_for(lambda: state(hass) == "armed_away")
    unsub()
    assert "disarmed" not in seen, seen  # a mode switch never flashes Disarmed

    await call(hass, "alarm_disarm")
    await wait_for(lambda: state(hass) == "disarmed")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_home_is_hidden_when_not_used(hass, fake):
    entry = await setup_connect(hass, fake)
    with pytest.raises(HomeAssistantError):
        await call(hass, "alarm_arm_home")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_alarm_code(hass, fake):
    entry = await setup_connect(hass, fake, options={"alarm_code": "4321", "code_arm_required": False})
    await call(hass, "alarm_arm_away")  # arming doesn't need the code
    await wait_for(lambda: state(hass) == "armed_away")
    with pytest.raises(ServiceValidationError):
        await call(hass, "alarm_disarm")
    with pytest.raises(ServiceValidationError):
        await call(hass, "alarm_disarm", code="1111")
    await call(hass, "alarm_disarm", code="4321")
    await wait_for(lambda: state(hass) == "disarmed")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_alarm_code_for_arming_too(hass, fake):
    entry = await setup_connect(hass, fake, options={"alarm_code": "4321", "code_arm_required": True})
    with pytest.raises(ServiceValidationError):
        await call(hass, "alarm_arm_away")
    await call(hass, "alarm_arm_away", code="4321")
    await wait_for(lambda: state(hass) == "armed_away")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_keypad_arm_shows_the_user_and_alarm_names_the_zone(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.send_user(3)
    fake.set_area(3)  # keypad full arm
    await wait_for(lambda: state(hass) == "armed_away")
    assert hass.states.get(ALARM).attributes["changed_by"] == "User 3"

    fake.set_area(5)  # alarm...
    fake.set_zone(4, 0x11)  # ...set off by Kitchen (active + alarmed)
    await wait_for(lambda: state(hass) == "triggered")
    await wait_for(lambda: hass.states.get(ALARM).attributes["changed_by"] == "Kitchen")

    fake.set_area(0)  # disarmed, by nobody we know of (e.g. a fob)
    await wait_for(lambda: state(hass) == "disarmed")
    assert hass.states.get(ALARM).attributes["changed_by"] is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_alarm_memory_doesnt_blame_a_zone_for_a_later_alarm(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.set_zone(4, 0x11)  # Kitchen active, alarm memory still set, while disarmed
    await wait_for(lambda: hass.states.get("binary_sensor.texecom_kitchen").state == "on")
    fake.set_area(3)
    await wait_for(lambda: state(hass) == "armed_away")
    fake.set_area(5)
    fake.set_zone(2, 0x11)  # the Hallway sets it off
    await wait_for(lambda: hass.states.get(ALARM).attributes["changed_by"] == "Hallway")
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unavailable_until_the_panel_says_its_state(hass, fake):
    """Connected, but the area's state not read yet (a moment after each
    start): unavailable, so the activity list never shows "Unknown"."""
    entry = await setup_connect(hass, fake)
    panel = entry.runtime_data
    panel.areas[1].known = False
    panel.notify()
    assert state(hass) == "unavailable"
    panel.areas[1].known = True
    panel.notify()
    assert state(hass) == "disarmed"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_arming_while_not_connected_says_so(hass, fake):
    entry = await setup_connect(hass, fake)
    entry.runtime_data.set_connected(False)  # e.g. while the SmartCom reports an alarm
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "alarm_arm_away")
    assert err.value.translation_key == "not_connected"
    entry.runtime_data.set_connected(True)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_refusal_says_so(hass, fake):
    entry = await setup_connect(hass, fake)
    fake.nak_next[P.CMD_ARM_AREA] = 1  # the panel says no
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "alarm_arm_away")
    assert err.value.translation_key == "refused"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_changed_by_uses_keypad_user_names(hass, fake):
    entry = await setup_connect(hass, fake, options={"user_names": {"3": "Sam"}})
    fake.send_user(3)
    fake.set_area(3)
    await wait_for(lambda: state(hass) == "armed_away")
    assert hass.states.get(ALARM).attributes["changed_by"] == "Sam"
    fake.send_user(4)  # no name given: stays "User 4"
    fake.set_area(0)
    await wait_for(lambda: hass.states.get(ALARM).attributes["changed_by"] == "User 4")
    assert await hass.config_entries.async_unload(entry.entry_id)
