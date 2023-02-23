from typing import List, Optional

from lnbits.core.crud import (
    create_wallet,
    delete_wallet,
    get_payments,
    get_wallet
)
from lnbits.core.models import Payment

from . import db
from .models import DiscordUser, Wallets, BotSettings, CreateBotSettings

from ..usermanager.crud import (
    get_usermanager_user_by,
    create_usermanager_user,
)

from ..usermanager.models import CreateUserData
from ..usermanager import crud as um_crud


### Settings


async def get_discordbot_settings(admin_id: str) -> Optional[BotSettings]:
    row = await db.fetchone("SELECT * FROM discordbot.settings WHERE admin = ?", (admin_id,))
    return BotSettings(**row) if row else None


async def get_all_discordbot_settings() -> list[BotSettings]:
    rows = await db.fetchall("SELECT * FROM discordbot.settings")
    return [BotSettings(**row) for row in rows]


async def create_discordbot_settings(data: CreateBotSettings, admin_id: str):
    result = await db.execute(
        f"""
        INSERT INTO discordbot.settings (admin, bot_token) 
        VALUES (?, ?)
        ON CONFLICT (admin) DO 
            UPDATE SET bot_token = '{data.bot_token}' 
        """,
        (admin_id, data.bot_token)
    )
    assert result.rowcount == 1, "Could not create settings"


async def delete_discordbot_settings(admin_id: str):
    result = await db.execute("DELETE FROM discordbot.settings WHERE admin = ?", (admin_id,))
    assert result.rowcount == 1, "Could not create settings"



### Users

async def get_discordbot_user(user_id: str) -> Optional[DiscordUser]:
    row = await db.fetchone("SELECT * FROM discordbot.users WHERE id = ?", (user_id,))
    return DiscordUser(**row) if row else None


# async def get_discordbot_users(user_id: str) -> List[DiscordUser]:
#     users = await get_usermanager_users(user_id)
#
#
#     return [DiscordUser(avatar_url=,**user.dict()) for user in users]


async def delete_discordbot_user(user_id: str) -> None:
    wallets = await get_discordbot_wallets(user_id)
    for wallet in wallets:
        await delete_wallet(user_id=user_id, wallet_id=wallet.id)

    await db.execute("DELETE FROM discordbot.users WHERE id = ?", (user_id,))
    await db.execute("""DELETE FROM discordbot.wallets WHERE "user" = ?""", (user_id,))


### Wallets


async def get_or_create_wallet(username: str, discord_id: str, admin_id: str = None):
    wallet = await get_discord_wallet(discord_id, admin_id)
    if not wallet:
        user = await create_usermanager_user(CreateUserData(
            user_name=username,
            wallet_name=f"{username}-main",
            admin_id=admin_id,
            attrs={
                'discord_id': discord_id
            }
        ))
        wallets = await um_crud.get_usermanager_users_wallets(user.id)
        wallet = wallets[0]


    return wallet


async def get_discord_wallet(discord_id: str, admin_id: str = None):
    user = await get_usermanager_user_by(
        admin=admin_id,
        attrs={
            'discord_id': discord_id
        },
    )

    if user:
        wallets = await um_crud.get_usermanager_users_wallets(user.id)
        return wallets[0]


async def get_discordbot_wallet(wallet_id: str) -> Optional[Wallets]:
    row = await db.fetchone(
        "SELECT * FROM discordbot.wallets WHERE id = ?", (wallet_id,)
    )
    return Wallets(**row) if row else None


async def get_discordbot_wallets(admin_id: str) -> List[Wallets]:
    rows = await db.fetchall(
        "SELECT * FROM discordbot.wallets WHERE admin = ?", (admin_id,)
    )
    return [Wallets(**row) for row in rows]


async def get_discordbot_users_wallets(user_id: str) -> List[Wallets]:
    rows = await db.fetchall(
        """SELECT * FROM discordbot.wallets WHERE "user" = ?""", (user_id,)
    )
    return [Wallets(**row) for row in rows]


async def get_discordbot_wallet_transactions(wallet_id: str) -> List[Payment]:
    return await get_payments(
        wallet_id=wallet_id, complete=True, pending=False, outgoing=True, incoming=True
    )


async def delete_discordbot_wallet(wallet_id: str, user_id: str) -> None:
    await delete_wallet(user_id=user_id, wallet_id=wallet_id)
    await db.execute("DELETE FROM discordbot.wallets WHERE id = ?", (wallet_id,))
