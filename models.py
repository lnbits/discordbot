from __future__ import annotations

from sqlite3 import Row
from typing import Optional

from lnbits.db import FilterModel

try:
    import discord
except ImportError:
    discord = None

from pydantic import BaseModel


class DiscordUser(BaseModel):
    id: str
    name: str
    admin: str
    discord_id: str
    avatar_url: Optional[str]


class DiscordFilters(FilterModel):
    __search_fields__ = ["name"]
    id: str
    name: str
    email: Optional[str] = None
    extra: Optional[dict[str, str]]
    discord_id: str


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
    token: str
    name: Optional[str]
    avatar_url: Optional[str]
    standalone: bool


class CreateBotSettings(BaseModel):
    token: str
    standalone: bool


class UpdateBotSettings(BaseModel):
    name: Optional[str]
    avatar_url: Optional[str]
    standalone: Optional[bool]


class BotInfo(BotSettings):
    online: Optional[bool]

    @classmethod
    def from_client(cls, settings: BotSettings, client: discord.Client = None):
        if client:
            online = client.is_ready()
        else:
            online = None
        return cls(online=online, **settings.dict())
