"""Names for keypad users (users.py)."""

from __future__ import annotations

import _paths  # noqa: F401
from fake_connect_panel import FAKE_USERS

from custom_components.texecom.connect import protocol as P
from custom_components.texecom.panel import PanelError
from custom_components.texecom.users import (
    format_user_names,
    panel_user_names,
    parse_user_names,
    user_name,
    with_user_name,
)

from .common import setup_connect, wait_for


def test_reading_names():
    assert parse_user_names("1 = Alex\n\n  User 3: Sam \n10-Pat") == {"1": "Alex", "3": "Sam", "10": "Pat"}
    assert parse_user_names("") == {}
    assert parse_user_names("Sam") is None  # no number
    assert parse_user_names("3 =") is None  # no name


def test_names_shown_for_editing():
    names = {"10": "Pat", "3": "Sam", "1": "Alex"}
    assert format_user_names(names) == "1 = Alex\n3 = Sam\n10 = Pat"
    assert parse_user_names(format_user_names(names)) == names


def test_names_in_changed_by():
    options = {"user_names": {"3": "Sam"}}
    assert with_user_name(options, "User 3") == "Sam"
    assert with_user_name(options, "User 4") == "User 4"
    assert with_user_name(options, "Kitchen") == "Kitchen"  # a zone
    assert with_user_name(options, "Home Assistant") == "Home Assistant"
    assert with_user_name({}, None) is None
    assert user_name(options, 3) == "Sam" and user_name({}, 7) == "User 7"


def test_names_from_the_panel():
    assert panel_user_names({1: "Master", 3: "Sam"}) == {"0": "Engineer", "1": "Master", "3": "Sam"}
    assert panel_user_names({}) == {}  # no engineer on their own


# ─── Filled in from the panel, the first time it connects ──────────────────


async def test_names_filled_in_when_first_connected(hass, fake, caplog):
    caplog.set_level("DEBUG", logger="custom_components.texecom")
    entry = await setup_connect(hass, fake, fill_names=True)
    await wait_for(lambda: "user_names" in entry.options)
    assert entry.options["user_names"] == {"0": "Engineer", "1": "Master", "3": "Sam"}
    assert entry.options["night_part_arm"] == 1  # the other options kept
    for _name, code in FAKE_USERS.values():
        assert code not in caplog.text and code not in str(entry.options)
    # Once only: not read again at the next start.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await wait_for(lambda: entry.runtime_data.connected)
    fake.commands.clear()
    await hass.async_block_till_done()
    assert not [cmd for cmd, _ in fake.commands if cmd == P.CMD_GET_USER]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_names_already_given_are_left_alone(hass, fake):
    entry = await setup_connect(hass, fake, {"user_names": {"3": "Alex"}}, fill_names=True)
    await hass.async_block_till_done()
    assert entry.options["user_names"] == {"3": "Alex"}
    assert not [cmd for cmd, _ in fake.commands if cmd == P.CMD_GET_USER]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_panel_without_named_users(hass, fake):
    fake.users = {}
    entry = await setup_connect(hass, fake, fill_names=True)
    await wait_for(lambda: "user_names" in entry.options)
    assert entry.options["user_names"] == {}  # read, so not again next time
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_names_tried_again_next_start_if_the_panel_wont_give_them(hass, fake, monkeypatch):
    from custom_components.texecom.connect.panel import ConnectPanel

    async def refused(self):
        raise PanelError("couldn't read the users: no reply")

    monkeypatch.setattr(ConnectPanel, "async_read_user_names", refused)
    entry = await setup_connect(hass, fake, fill_names=True)
    await hass.async_block_till_done()
    assert "user_names" not in entry.options
    monkeypatch.undo()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await wait_for(lambda: "user_names" in entry.options)
    assert entry.options["user_names"]["3"] == "Sam"
    assert await hass.config_entries.async_unload(entry.entry_id)
