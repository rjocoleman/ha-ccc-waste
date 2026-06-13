"""Config flow for CCC kerbside collection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import CCCApiClient
from .const import CONF_ADDRESS, CONF_RATING_UNIT_ID, DOMAIN
from .exceptions import CCCAddressNotFound, CCCError

if TYPE_CHECKING:
    from .models import CCCAddress

_USER_SCHEMA = vol.Schema({vol.Required(CONF_ADDRESS): str})


class CCCConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the address lookup config flow."""

    def __init__(self) -> None:
        """Start with no pending suggestions."""
        self._suggestions: list[CCCAddress] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take a partial address and look it up."""
        return await self._async_lookup_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the configured address without removing the entry."""
        return await self._async_lookup_step("reconfigure", user_input)

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one address when the lookup returns several."""
        if user_input is not None:
            chosen = next(
                (
                    address
                    for address in self._suggestions
                    if str(address.rating_unit_id) == user_input[CONF_ADDRESS]
                ),
                None,
            )
            if chosen is None:
                return self.async_abort(reason="unknown")
            return await self._async_finish(chosen)

        options = [
            SelectOptionDict(value=str(a.rating_unit_id), label=a.full_address)
            for a in self._suggestions
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(step_id="select", data_schema=schema)

    async def _async_lookup_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._suggestions = await self._async_suggest(user_input[CONF_ADDRESS])
            except CCCAddressNotFound:
                errors["base"] = "address_not_found"
            except CCCError:
                errors["base"] = "cannot_connect"
            else:
                if len(self._suggestions) == 1:
                    return await self._async_finish(self._suggestions[0])
                return await self.async_step_select()
        return self.async_show_form(
            step_id=step_id, data_schema=_USER_SCHEMA, errors=errors
        )

    async def _async_suggest(self, query: str) -> list[CCCAddress]:
        client = CCCApiClient(async_get_clientsession(self.hass))
        return await client.async_suggest_addresses(query)

    async def _async_finish(self, address: CCCAddress) -> ConfigFlowResult:
        await self.async_set_unique_id(str(address.rating_unit_id))
        data = {
            CONF_ADDRESS: address.full_address,
            CONF_RATING_UNIT_ID: address.rating_unit_id,
        }
        if self.source == SOURCE_RECONFIGURE:
            reconfigure_entry = self._get_reconfigure_entry()
            if any(
                entry.entry_id != reconfigure_entry.entry_id
                and entry.unique_id == str(address.rating_unit_id)
                for entry in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            return self.async_update_reload_and_abort(
                reconfigure_entry,
                title=address.full_address,
                data=data,
                unique_id=str(address.rating_unit_id),
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=address.full_address, data=data)
