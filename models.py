from sqlite3 import Row
from typing import Optional

import discord
from pydantic import BaseModel


class DiscordUser(BaseModel):
    id: str
    name: str
    admin: str
    discord_id: str
    avatar_url: str


class Wallets(BaseModel):
    id: str
    admin: str
    name: str
    user: str
    adminkey: str
    inkey: str

    @classmethod
    def from_row(cls, row: Row) -> "Wallets":
        return cls(**dict(row))

class BotSettings(BaseModel):
    admin: str
    bot_token: str = None


class CreateBotSettings(BaseModel):
    bot_token: str

class UpdateBotSettings(BotSettings):
    bot_token: str

class BotInfo(BaseModel):
    online: bool
    name: Optional[str]
    avatar_url: Optional[str]

    @classmethod
    def from_client(cls, client: discord.Client = None):
        if client:
            return cls(
                online=client.is_ready(),
                name=client.user.name if client.user else None,
                avatar_url=(client.user.avatar or client.user.default_avatar).url if client.user else None,
            )
        else:
            return cls(
                online=False
            )
