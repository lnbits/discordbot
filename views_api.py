from http import HTTPStatus
from typing import Optional

import httpx
from fastapi import Depends, Query, APIRouter
from starlette.exceptions import HTTPException

from lnbits.decorators import WalletTypeInfo, get_key_type, require_admin_key

from . import discordbot_ext
from .bot.client import (
    get_running_bot,
    start_bot,
    stop_bot
)
from .crud import (
    get_discordbot_user,
    get_discordbot_users_wallets,
    get_discordbot_wallet_transactions,
    get_discordbot_wallets,
    get_discordbot_settings,
    get_all_discordbot_settings,
    create_discordbot_settings, delete_discordbot_settings,
)

from ..usermanager.crud import (
    get_usermanager_users
)

from .models import BotSettings, CreateBotSettings, BotInfo, DiscordUser

discordbot_api: APIRouter = APIRouter(prefix="/api/v1", tags=["discordbot"])

http_client: Optional[httpx.AsyncClient] = None


@discordbot_api.on_event('startup')
async def on_startup():
    global http_client
    http_client = httpx.AsyncClient()
    for settings in await get_all_discordbot_settings():
        await start_bot(settings, http_client)


@discordbot_api.on_event('shutdown')
async def on_startup():
    global http_client
    await http_client.aclose()


async def require_bot_settings(wallet_info: WalletTypeInfo = Depends(require_admin_key)):
    settings = await get_discordbot_settings(wallet_info.wallet.user)
    if not settings:
        raise HTTPException(
            status_code=400,
            detail='No bot created'
        )
    return settings


@discordbot_api.delete("", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_extension_delete(usr: str = Query(...)):
    settings = await get_discordbot_settings(usr)
    if settings:
        await stop_bot(settings)
        await delete_discordbot_settings(settings.admin)



# Users


@discordbot_api.get("/bot", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_status(settings: BotSettings = Depends(require_bot_settings)):
    client = get_running_bot(settings.bot_token)
    return BotInfo.from_client(client)


@discordbot_api.post(
    "/bot",
    status_code=HTTPStatus.OK,
    response_model=BotInfo
)
async def api_create_bot(data: CreateBotSettings,
                         wallet_type: WalletTypeInfo = Depends(require_admin_key)):
    await create_discordbot_settings(data, wallet_type.wallet.user)
    client = await start_bot(
        BotSettings(admin=wallet_type.wallet.user, bot_token=data.bot_token),
        http_client
    )
    return BotInfo.from_client(client)


@discordbot_api.delete(
    "/bot",
    status_code=HTTPStatus.OK,
)
async def api_delete_bot(settings: BotSettings = Depends(require_bot_settings)):
    await stop_bot(settings)
    await delete_discordbot_settings(settings.admin)


@discordbot_api.get("/bot/start", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_start(settings: BotSettings = Depends(require_bot_settings)):
    client = await start_bot(settings, http_client)
    return BotInfo.from_client(client)


@discordbot_api.get("/bot/stop", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_stop(settings: BotSettings = Depends(require_bot_settings)):
    client = await stop_bot(settings)
    return BotInfo.from_client(client)


@discordbot_api.get("/users", status_code=HTTPStatus.OK, response_model=list[DiscordUser])
async def api_discordbot_users(settings: BotSettings = Depends(require_bot_settings)):
    users = await get_usermanager_users(settings.admin)
    client = get_running_bot(settings.bot_token)

    results = []
    for user in users:
        discord_id = user.attrs.get('discord_id')
        if discord_id:
            discord_user = client.get_user(int(discord_id))
            if not discord_user:
                discord_user = await client.fetch_user(int(discord_id))

            user_dict = user.dict()
            user_dict['avatar_url'] = (discord_user.avatar or discord_user.default_avatar).url
            user_dict['discord_id'] = discord_id
            results.append(user_dict)

    return results


@discordbot_api.get("/users/{user_id}", status_code=HTTPStatus.OK)
async def api_discordbot_user(user_id, wallet: WalletTypeInfo = Depends(get_key_type)):
    user = await get_discordbot_user(user_id)
    if user:
        return user.dict()


# Wallets


@discordbot_api.get("/wallets")
async def api_discordbot_wallets(
    wallet: WalletTypeInfo = Depends(get_key_type),
):
    admin_id = wallet.wallet.user
    return await get_discordbot_wallets(admin_id)


@discordbot_api.get("/transactions/{wallet_id}")
async def api_discordbot_wallet_transactions(
    wallet_id, wallet: WalletTypeInfo = Depends(get_key_type)
):
    return await get_discordbot_wallet_transactions(wallet_id)


@discordbot_api.get("/wallets/{user_id}")
async def api_discordbot_users_wallets(
    user_id, wallet: WalletTypeInfo = Depends(get_key_type)
):
    return await get_discordbot_users_wallets(user_id)


discordbot_ext.include_router(discordbot_api)
