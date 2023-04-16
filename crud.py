from typing import List, Optional

from lnbits.core import Filters
from lnbits.core.crud import delete_wallet, get_payments
from lnbits.core.models import Payment
from lnbits.db import Filter
from lnbits.extensions.usermanager.crud import (
    create_usermanager_user,
    get_usermanager_users,
    get_usermanager_users_wallets,
)
from lnbits.extensions.usermanager.models import CreateUserData

from . import db
from .models import (
    BotSettings,
    CreateBotSettings,
    DiscordUser,
    UpdateBotSettings,
    Wallets,
)

### Settings


async def get_discordbot_settings(admin_id: str) -> Optional[BotSettings]:
    row = await db.fetchone("SELECT * FROM discordbot.bots WHERE admin = ?", (admin_id,))
    return BotSettings(**row) if row else None


async def get_all_discordbot_settings() -> list[BotSettings]:
    rows = await db.fetchall("SELECT * FROM discordbot.bots")
    return [BotSettings(**row) for row in rows]


async def create_discordbot_settings(data: CreateBotSettings, admin_id: str):
    result = await db.execute(
        f"""
        INSERT INTO discordbot.bots (admin, token) 
        VALUES (?, ?)
        ON CONFLICT (admin) DO 
            UPDATE SET token = '{data.token}' 
        """,
        (admin_id, data.token)
    )
    return await get_discordbot_settings(admin_id)


async def update_discordbot_settings(data: UpdateBotSettings, admin_id: str):
    updates = []
    values = []
    for key, val in data.dict(exclude_unset=True).items():
        updates.append(f"{key} = ?")
        values.append(val)
    values.append(admin_id)
    result = await db.execute(
        f"""
        UPDATE discordbot.bots 
        SET {", ".join(updates)}
        WHERE admin = ?
        """,
        values
    )
    return await get_discordbot_settings(admin_id)


async def delete_discordbot_settings(admin_id: str):
    result = await db.execute("DELETE FROM discordbot.bots WHERE admin = ?", (admin_id,))
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
            extra={
                'discord_id': discord_id
            }
        ))
        wallet = user.wallets[0]

    return wallet


async def get_discord_wallet(discord_id: str, admin_id: str = None):
    user = await get_usermanager_users(
        admin_id,
        Filters(
            filters=[Filter(field='extra', nested=['discord_id'], values=[discord_id])]
        )
    )

    if user:
        wallets = await get_usermanager_users_wallets(user.id)
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
