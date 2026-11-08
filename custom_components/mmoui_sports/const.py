from __future__ import annotations

DOMAIN = "mmoui_sports"
NAME = "MMOUi Sports"
ATTRIBUTION = "Data provided by TheSportsDB"
ATTRIBUTION_ESPN = "Data provided by ESPN"

CONF_API_KEY = "api_key"
CONF_COMPETITION = "competition"

# One config entry per competition; the values are also the entity ID prefixes
# of the WEC, the Dakar and the NBA.
COMPETITION_WEC = "fia_wec"
COMPETITION_DAKAR = "dakar_rally"
COMPETITION_SUPERLEGA = "superlega"
COMPETITION_NBA = "nba"
COMPETITIONS = (COMPETITION_WEC, COMPETITION_DAKAR, COMPETITION_SUPERLEGA, COMPETITION_NBA)

# TheSportsDB public test key. Works for everybody but caps the list
# endpoints (5 events per request, 1 next/past event).
FREE_API_KEYS = ("3", "123")
DEFAULT_API_KEY = "3"

API_BASE_URL = "https://www.thesportsdb.com/api/v1/json"

# Free keys are limited to 30 requests per minute, counted over every competition;
# TheSportsDB already answers 429 at about 28 a minute, so stay well below it.
FREE_REQUEST_SPACING = 3.0
PREMIUM_REQUEST_SPACING = 0.3

STORAGE_VERSION = 1
