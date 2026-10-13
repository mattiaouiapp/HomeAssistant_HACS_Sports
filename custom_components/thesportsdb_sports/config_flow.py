from __future__ import annotations
from collections.abc import Mapping
from typing import Any
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode
from .api import SportsApiClient, SportsApiError, SportsAuthError
from .competitions import COMPETITIONS, competition_of
from .const import CONF_API_KEY, CONF_COMPETITION, DEFAULT_API_KEY, DOMAIN


async def _validate_key(hass: HomeAssistant, api_key: str, competition: str) -> str | None:
    """Return an error key, or None when the key can read the competition's league."""
    client = SportsApiClient(async_get_clientsession(hass), api_key, COMPETITIONS[competition].LEAGUE_ID)
    try:
        await client.async_get_league()
    except SportsAuthError:
        return "invalid_api_key"
    except SportsApiError:
        return "cannot_connect"
    return None


class SportsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        configured = {e.data.get(CONF_COMPETITION) for e in self._async_current_entries()}
        available = [key for key in COMPETITIONS if key not in configured]
        if not available:
            return self.async_abort(reason="all_configured")

        errors: dict[str, str] = {}
        if user_input is not None:
            competition = user_input[CONF_COMPETITION]
            await self.async_set_unique_id(competition)
            self._abort_if_unique_id_configured()
            api_key = user_input.get(CONF_API_KEY, "").strip() or DEFAULT_API_KEY
            if not (error := await _validate_key(self.hass, api_key, competition)):
                return self.async_create_entry(
                    title=COMPETITIONS[competition].NAME,
                    data={CONF_COMPETITION: competition, CONF_API_KEY: api_key},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COMPETITION, default=available[0]): SelectSelector(
                        SelectSelectorConfig(
                            options=available,
                            translation_key=CONF_COMPETITION,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(CONF_API_KEY, default=DEFAULT_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip() or DEFAULT_API_KEY
            if not (error := await _validate_key(self.hass, api_key, entry.data[CONF_COMPETITION])):
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_API_KEY: api_key},
                    options={k: v for k, v in entry.options.items() if k != CONF_API_KEY},
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY, default=DEFAULT_API_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SportsOptionsFlow()


class SportsOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        competition = competition_of(entry)
        current_key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY) or DEFAULT_API_KEY
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip() or DEFAULT_API_KEY
            if api_key == current_key or not (
                error := await _validate_key(self.hass, api_key, entry.data[CONF_COMPETITION])
            ):
                options = {**user_input, CONF_API_KEY: api_key}
                if clean := getattr(competition, "clean_options", None):
                    options = clean(options)
                return self.async_create_entry(data=options)
            errors["base"] = error

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    **competition.options_schema(entry),
                    vol.Optional(CONF_API_KEY, default=current_key): str,
                }
            ),
            errors=errors,
        )
