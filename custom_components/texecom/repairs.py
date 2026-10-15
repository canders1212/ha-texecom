"""Repairs: a fix for a wrong panel clock (turns on clock sync)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir

from .const import CONF_TIME_SYNC, DOMAIN


class PanelClockFix(RepairsFlow):
    def __init__(self, entry_id: str, issue_id: str) -> None:
        self.entry_id = entry_id
        self.issue_id = issue_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry:
                # The options change reloads the entry, which sets the clock.
                self.hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_TIME_SYNC: True})
            return self.async_create_entry(data={})
        # The screen says how far out the clock is, as the notice does: without
        # its placeholder, Home Assistant shows none of the screen's text.
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        drift = (issue.translation_placeholders or {}).get("drift", "wrong") if issue else "wrong"
        return self.async_show_form(
            step_id="confirm", data_schema=vol.Schema({}), description_placeholders={"drift": drift}
        )


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    return PanelClockFix((data or {})["entry_id"], issue_id)
