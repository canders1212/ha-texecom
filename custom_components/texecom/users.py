"""Names for keypad users: the option that maps user numbers to names
("3 = Sam"), filling it in from the panel the first time Home Assistant
connects to it, and showing a name wherever the panel says "User 3"."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import CONF_PROTOCOL, CONF_USER_NAMES, PROTOCOL_CONNECT
from .panel import PanelError, TexecomPanel

_LOGGER = logging.getLogger(__name__)

# The engineer code shows as user 0 in keypad events, but has no user record
# to read (the panel refuses user 0), so it's named here.
ENGINEER_USER, ENGINEER_NAME = "0", "Engineer"

# "3 = Sam", "3: Sam", "User 3 = Sam"...
_LINE = re.compile(r"^\s*(?:user\s*)?(\d{1,4})\s*[=:,-]\s*(\S.*?)\s*$", re.IGNORECASE)
# How the panel drivers name a keypad user in "changed by".
_LABEL = re.compile(r"^User (\d+)$")


def parse_user_names(text: str) -> dict[str, str] | None:
    """{"3": "Sam"} from one "number = name" per line; None if a line
    doesn't fit that."""
    names: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if not (match := _LINE.match(line)):
            return None
        names[str(int(match.group(1)))] = match.group(2)
    return names


def panel_user_names(from_panel: Mapping[int, str]) -> dict[str, str]:
    """The option's form of the names read from the panel ({3: "Sam"} ->
    {"3": "Sam"}), with the engineer named; empty if the panel had none."""
    if not from_panel:
        return {}
    return {ENGINEER_USER: ENGINEER_NAME, **{str(n): name for n, name in from_panel.items()}}


def fill_in_names_once(hass: HomeAssistant, entry: ConfigEntry, panel: TexecomPanel) -> Callable[[], None]:
    """The first time Home Assistant connects to a panel over Texecom Connect,
    fills in the option from the names stored in the panel (the codes that
    come with them are dropped by the driver). Only while the option has never
    been saved: names typed in, or a list emptied on purpose, are left alone.
    If the panel won't give them, they're asked for again at the next start.
    Returns the function that stops it."""
    if CONF_USER_NAMES in entry.options or entry.data.get(CONF_PROTOCOL) != PROTOCOL_CONNECT:
        return lambda: None

    async def fill_in() -> None:
        try:
            from_panel = await panel.async_read_user_names()
        except PanelError as err:
            _LOGGER.debug("Couldn't fill in the keypad users' names from the panel: %s", err)
            return
        if CONF_USER_NAMES not in entry.options:  # unless saved in the options meanwhile
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_USER_NAMES: panel_user_names(from_panel)}
            )

    @callback
    def when_connected() -> None:
        if panel.connected:
            stop()
            entry.async_create_background_task(hass, fill_in(), "texecom keypad user names")

    stop = panel.add_listener(when_connected)
    return stop


def format_user_names(names: Mapping[str, str]) -> str:
    """The option as it's shown for editing: one "3 = Sam" per line."""
    return "\n".join(f"{number} = {name}" for number, name in sorted(names.items(), key=lambda kv: int(kv[0])))


def user_name(options: Mapping[str, Any], number: int) -> str:
    """User 3's name, or "User 3"."""
    return options.get(CONF_USER_NAMES, {}).get(str(number), f"User {number}")


def with_user_name(options: Mapping[str, Any], label: str | None) -> str | None:
    """A driver's "changed by" with the user's name: "User 3" -> "Sam".
    Anything else (a zone, "Home Assistant") is left as it is."""
    if label and (match := _LABEL.match(label)):
        return user_name(options, int(match.group(1)))
    return label
