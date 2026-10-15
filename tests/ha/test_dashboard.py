"""The Alarm dashboard (dashboard.py)."""

from __future__ import annotations

from fake_connect_panel import DEMO_ZONES, FakeConnectPanel

from custom_components.texecom.dashboard import async_create_dashboard, build_config

from .common import setup_connect


async def test_dashboard_layout(hass, fake):
    entry = await setup_connect(hass, fake)
    config = build_config(hass, entry)
    left, right = config["views"][0]["sections"]
    alarm = next(c for c in left["cards"] if c.get("entity") == "alarm_control_panel.texecom_house")
    # Every mode, in button order: Home Assistant shows only the ones the alarm
    # offers, so the buttons follow Configure → Arm buttons without a rebuild.
    assert alarm["features"][0]["modes"] == [
        "armed_away",
        "armed_night",
        "armed_home",
        "armed_vacation",
        "armed_custom_bypass",
        "disarmed",
    ]
    headings = [c["heading"] for c in right["cards"] if c["type"] == "heading"]
    assert headings == ["Doors and windows", "Motion", "Fire and safety"]
    tiles = [c["entity"] for c in right["cards"] if c["type"] == "tile"]
    assert tiles[:2] == ["binary_sensor.texecom_front_door", "binary_sensor.texecom_patio_door"]
    named_tiles = [c.get("name") for c in left["cards"] if c["type"] == "tile" and "name" in c]
    assert named_tiles == ["Ready to arm", "Connection", "Mains", "Faults", "Tamper", "Keypad", "Battery"]
    activity = next(c for c in left["cards"] if c["type"] == "logbook")
    assert activity["target"]["entity_id"] == ["alarm_control_panel.texecom_house"]  # not every door opening
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_dashboard_is_created(hass, fake):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    entry = await setup_connect(hass, fake)
    url = await async_create_dashboard(hass, entry)
    assert url == "texecom-alarm"
    saved = await hass.data["lovelace"].dashboards[url].async_load(False)
    assert saved["views"][0]["title"] == "Alarm"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_each_panel_keeps_its_own_dashboard(hass, fake):
    """With a second panel added, refreshing the first panel's dashboard (made
    when it was the only one) updates it rather than adding another."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    second = FakeConnectPanel(zones=DEMO_ZONES, exit_delay=0.05)
    await second.start()
    try:
        first_entry = await setup_connect(hass, fake)
        assert await async_create_dashboard(hass, first_entry) == "texecom-alarm"
        second_entry = await setup_connect(hass, second)
        second_url = await async_create_dashboard(hass, second_entry)
        assert second_url == f"texecom-alarm-{second_entry.entry_id[-6:].lower()}"
        assert await async_create_dashboard(hass, first_entry) == "texecom-alarm"
        assert await async_create_dashboard(hass, second_entry) == second_url
        assert sorted(url for url in hass.data["lovelace"].dashboards if url) == ["texecom-alarm", second_url]
        for entry in (first_entry, second_entry):
            assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await second.close()


async def test_deleting_a_panel_deletes_its_dashboard(hass, fake):
    """Otherwise an "Alarm" stays in the sidebar with every entity missing."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    second = FakeConnectPanel(zones=DEMO_ZONES, exit_delay=0.05)
    await second.start()
    try:
        first_entry = await setup_connect(hass, fake)
        await async_create_dashboard(hass, first_entry)
        second_entry = await setup_connect(hass, second)
        assert await async_create_dashboard(hass, second_entry) != "texecom-alarm"
        assert await hass.config_entries.async_remove(second_entry.entry_id)
        await hass.async_block_till_done()
        assert sorted(url for url in hass.data["lovelace"].dashboards if url) == ["texecom-alarm"]
        assert await hass.config_entries.async_remove(first_entry.entry_id)
        await hass.async_block_till_done()
        assert [url for url in hass.data["lovelace"].dashboards if url] == []
    finally:
        await second.close()


async def test_upgrading_lets_an_older_dashboards_buttons_follow_arm_buttons(hass, fake):
    """Dashboards made before 0.2.12 listed only the modes the alarm had then.
    Upgrading lists every mode on the alarm's card, and keeps the user's edits."""
    from homeassistant.setup import async_setup_component

    from custom_components.texecom.config_flow import TexecomConfigFlow
    from custom_components.texecom.dashboard import MODES

    assert await async_setup_component(hass, "lovelace", {})
    entry = await setup_connect(hass, fake)
    url = await async_create_dashboard(hass, entry)
    dashboard = hass.data["lovelace"].dashboards[url]
    config = await dashboard.async_load(False)
    left, right = config["views"][0]["sections"]
    alarm = next(c for c in left["cards"] if c.get("entity") == "alarm_control_panel.texecom_house")
    alarm["features"][0]["modes"] = ["armed_away", "armed_night", "disarmed"]  # as 0.2.9 made it
    right["cards"].append({"type": "markdown", "content": "Mine"})  # an edit of the user's
    await dashboard.async_save(config)
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, minor_version=2)

    assert await hass.config_entries.async_setup(entry.entry_id)  # upgrades first
    await hass.async_block_till_done()
    assert entry.minor_version == TexecomConfigFlow.MINOR_VERSION
    left, right = (await dashboard.async_load(False))["views"][0]["sections"]
    alarm = next(c for c in left["cards"] if c.get("entity") == "alarm_control_panel.texecom_house")
    assert alarm["features"][0]["modes"] == MODES
    assert {"type": "markdown", "content": "Mine"} in right["cards"]
    assert await hass.config_entries.async_unload(entry.entry_id)
