from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Extra, HttpUrl


class DiscordSettings(BaseSettings):
    discord_dev_guild: Optional[int] = None

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = Extra.ignore


class StandaloneSettings(DiscordSettings):
    lnbits_url: Optional[HttpUrl] = None
    lnbits_admin_key: Optional[str] = None
    discord_bot_token: Optional[str] = None
    data_folder: Optional[Path] = "./data"


discord_settings = DiscordSettings()
