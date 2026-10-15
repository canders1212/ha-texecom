"""Repairs notices: the panel clock is wrong (fixable, see repairs.py), the
panel has been unreachable for a while, and the panel sent messages the
integration doesn't recognise (an invitation to share them)."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval

from .const import CLOCK_DRIFT_LIMIT, CONF_SERIAL_DEVICE, DOMAIN, HELP_OFFLINE, SHARE_DATA_URL
from .panel import TexecomPanel

OFFLINE_ISSUE_AFTER = 15 * 60  # seconds without a connection before Repairs says so
UNRECOGNISED_CHECK = timedelta(minutes=10)


def describe_drift(drift: int | None) -> str:
    """E.g. "about 3 years behind", "12 minutes ahead"; None: an impossible date."""
    if drift is None:
        return "not set (it holds an impossible date)"
    seconds = abs(drift)
    for unit, size in (("year", 365 * 86400), ("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = round(seconds / size)
            amount = f"{count} {unit}{'s' if count != 1 else ''}"
            break
    else:
        amount = f"{seconds} seconds"
    return f"about {amount} {'ahead' if drift > 0 else 'behind'}"


def clock_drift_reporter(hass: HomeAssistant, entry: ConfigEntry) -> Callable[[int | None], None]:
    """The Connect panel's on_clock_drift (used while clock sync is off): a
    notice while the clock is more than CLOCK_DRIFT_LIMIT out, cleared once
    it's right."""

    @callback
    def clock_drift(drift: int | None) -> None:
        issue_id = f"panel_clock_{entry.entry_id}"
        if drift is not None and abs(drift) <= CLOCK_DRIFT_LIMIT:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="panel_clock_wrong",
            translation_placeholders={"drift": describe_drift(drift)},
            data={"entry_id": entry.entry_id},
        )

    return clock_drift


def clear_clock_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clock sync is on: it sets the clock, so no notice is needed."""
    ir.async_delete_issue(hass, DOMAIN, f"panel_clock_{entry.entry_id}")


# The usual reasons a connection fails, in plain words for the notice (the
# full error is in the log and the diagnostics). First match wins.
PLAIN_REASONS = (
    ("UDL code", None),  # already plain
    ("Connect call failed", "something at that address turned the connection away"),
    ("refused", "something at that address turned the connection away"),
    ("()", "nothing answers at that address"),  # timed out
    ("timed out", "nothing answers at that address"),
    ("No route to host", "nothing answers at that address"),
    ("unreachable", "nothing answers at that address"),
    ("Host is down", "nothing answers at that address"),
    ("not known", "that name isn't known on the network"),
    ("nodename nor servname", "that name isn't known on the network"),
)


def plain_reason(error: str | None) -> str:
    """Why the panel can't be reached, in plain words where the error is a usual one."""
    if not error:
        return "no reply"
    for words, plain in PLAIN_REASONS:
        if words in error:
            return plain or error
    return error


def watch_connection(hass: HomeAssistant, entry: ConfigEntry, panel: TexecomPanel):
    """Raises a Repairs notice when the panel has been unreachable for a while
    (e.g. the SmartCom's address changed), and clears it once connected."""
    issue_id = f"panel_offline_{entry.entry_id}"
    address = entry.data.get(CONF_SERIAL_DEVICE) or f"{entry.data.get(CONF_HOST)}:{entry.data.get(CONF_PORT)}"

    @callback
    def check(_now=None) -> None:
        since = panel.disconnected_since
        if panel.connected or since is None:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            return
        minutes = (time.monotonic() - since) / 60
        if minutes * 60 < OFFLINE_ISSUE_AFTER:
            return
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="panel_offline",
            translation_placeholders={
                "name": entry.title,
                "address": address,
                "minutes": str(round(minutes)),
                "error": plain_reason(getattr(panel, "last_error", None)),
                "help": HELP_OFFLINE,
            },
        )

    remove_timer = async_track_time_interval(hass, check, timedelta(minutes=1))
    remove_listener = panel.add_listener(lambda: panel.connected and check())

    def remove() -> None:
        remove_timer()
        remove_listener()
        ir.async_delete_issue(hass, DOMAIN, issue_id)

    return remove


def watch_unrecognised(hass: HomeAssistant, entry: ConfigEntry, panel: TexecomPanel):
    """Asks once, in Repairs, for the diagnostics when the panel has sent
    messages the integration doesn't recognise (connect/capture.py): usually
    a detector, module or firmware nobody has been able to test. Never
    deleted while running, so a notice the user ignores stays ignored; after
    a restart it only comes back if such messages arrive again."""
    capture = getattr(panel, "capture", None)
    if capture is None:  # Crestron: its few line formats are all known
        return lambda: None
    issue_id = f"unrecognised_messages_{entry.entry_id}"

    @callback
    def check(_now=None) -> None:
        if not capture.unrecognised:
            return
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=SHARE_DATA_URL,
            translation_key="unrecognised_messages",
            translation_placeholders={
                "name": entry.title,
                "count": str(len(capture.unrecognised)),
                "example": next(iter(capture.unrecognised)),
            },
        )

    return async_track_time_interval(hass, check, UNRECOGNISED_CHECK)
