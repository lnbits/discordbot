from __future__ import annotations

import json
from typing import Optional, Union

import discord
import discord.utils
from httpx import AsyncClient, HTTPStatusError

from .models import Wallet
from .settings import discord_settings

# discord.utils.setup_logging()


if discord_settings.discord_dev_guild:
    discord.utils.setup_logging()
    DEV_GUILD = discord.Object(id=discord_settings.discord_dev_guild)
else:
    DEV_GUILD = None

DiscordUser = Union[discord.Member, discord.User]


class LnbitsAPI:
    def __init__(
        self, *, admin_key: str, http: AsyncClient, lnbits_url: str, **options
    ):
        super().__init__(**options)
        self.admin_key = admin_key
        self.lnbits_http = http
        self.lnbits_url = lnbits_url
        self.wallet_cache: dict[DiscordUser, Wallet] = {}

    async def get_lnbits_user(self, discord_user: DiscordUser):
        users = await self.request(
            "GET",
            "/users",
            self.admin_key,
            extension="usermanager",
            params={"extra": json.dumps({"discord_id": str(discord_user.id)})},
        )
        if users:
            user = users[0]
            if (
                user["extra"].get("discord_avatar_url")
                != discord_user.display_avatar.url
            ):
                await self.request(
                    "PATCH",
                    f'/users/{user["id"]}',
                    self.admin_key,
                    extension="usermanager",
                    json={
                        "extra": {
                            "discord_avatar_url": discord_user.display_avatar.url,
                        }
                    },
                )
            return user

    async def get_user_wallet(self, discord_user: DiscordUser) -> Optional[Wallet]:
        wallet = self.wallet_cache.get(discord_user)
        if not wallet:
            user = await self.get_lnbits_user(discord_user)
            if user:
                wallets = await self.request(
                    "GET",
                    f'/wallets/{user["id"]}',
                    self.admin_key,
                    extension="usermanager",
                )
                if not wallets:
                    await self.request(
                        "POST",
                        f'/wallets',
                        self.admin_key,
                        extension="usermanager",
                        json={"wallet_name": f"{discord_user.name}-main"},
                    )

                wallet = Wallet(**wallets[0])
                self.wallet_cache[discord_user] = wallet
        return wallet

    async def get_user_balance(self, discord_user: DiscordUser, _retry=True) -> Optional[int]:
        wallet = await self.get_user_wallet(discord_user)
        try:
            wallet = await self.request("GET", "/wallet", wallet.adminkey)
            if wallet:
                return int(wallet["balance"] / 1000)
        except HTTPStatusError:
            # Try again after clearing cache
            if _retry and discord_user in self.wallet_cache.pop(discord_user, None):
                return await self.get_user_balance(discord_user, _retry=False)
            else:
                raise

    async def get_or_create_wallet(self, user: DiscordUser) -> Wallet:
        wallet = await self.get_user_wallet(user)
        if not wallet:
            new_user = await self.request(
                "POST",
                "/users",
                self.admin_key,
                extension="usermanager",
                json=dict(
                    user_name=user.name,
                    wallet_name=f"{user.name}-main",
                    extra={
                        "discord_id": str(user.id),
                        "discord_avatar_url": user.display_avatar.url,
                    },
                ),
            )
            wallet = Wallet(**new_user["wallets"][0])
            self.wallet_cache[user] = wallet
        return wallet

    async def request(
        self, method: str, path: str, key: str = None, extension: str = None, **kwargs
    ) -> dict:
        if key:
            self.lnbits_http.headers["X-API-KEY"] = key

        response = await self.lnbits_http.request(
            method,
            url=self.lnbits_url
                + (extension + "/" if extension else "")
                + "api/v1"
                + path,
            **kwargs,
        )

        response.raise_for_status()

        return response.json()

    async def send_payment(
        self,
        sender: DiscordUser,
        receiver: DiscordUser,
        amount: int,
        memo: Optional[str] = None,
    ):
        sender_wallet = await self.get_user_wallet(sender)

        receiver_wallet = await self.get_or_create_wallet(receiver)

        invoice = await self.request(
            "POST",
            "/payments",
            receiver_wallet.adminkey,
            json={"out": False, "amount": amount, "memo": memo, "unit": "sat"},
        )

        await self.request(
            "POST",
            "/payments",
            sender_wallet.adminkey,
            json={"out": True, "bolt11": invoice["payment_request"]},
        )

        return receiver_wallet
