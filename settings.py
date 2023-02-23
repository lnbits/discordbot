from typing import Optional

from lnbits.settings import LNbitsSettings

class DiscordSettings(LNbitsSettings):
    discord_dev_guild: Optional[int] = None

discord_settings = DiscordSettings()