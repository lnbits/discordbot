from http import HTTPStatus

from fastapi import APIRouter, Depends, Query
from starlette.exceptions import HTTPException

from lnbits.db import Filter, Filters, Operator
from lnbits.decorators import WalletTypeInfo, get_key_type, require_admin_key
from lnbits.extensions.usermanager.crud import get_usermanager_users

from . import discordbot_ext
from .crud import (
    create_discordbot_settings,
    delete_discordbot_settings,
    get_discordbot_settings,
    get_discordbot_user,
    get_discordbot_users_wallets,
    get_discordbot_wallet_transactions,
    get_discordbot_wallets,
    update_discordbot_settings,
)
from .models import (
    BotInfo,
    BotSettings,
    CreateBotSettings,
    DiscordUser,
    UpdateBotSettings,
)

try:
    from tasks import get_client, start_bot, stop_bot
    can_run_bot = True
except ImportError:
    def get_client(token: str):
        return None

    async def start_bot(bot_settings: BotSettings):
        return None

    async def stop_bot(bot_settings: BotSettings):
        return None

    can_run_bot = False


discordbot_api: APIRouter = APIRouter(prefix="/api/v1", tags=["discordbot"])


async def require_bot_settings(wallet_info: WalletTypeInfo = Depends(require_admin_key)):
    settings = await get_discordbot_settings(wallet_info.wallet.user)
    if not settings:
        raise HTTPException(
            status_code=400,
            detail='No bot created'
        )
    if not settings.standalone and not can_run_bot:
        raise HTTPException(
            status_code=400,
            detail='Can not run discord bots on this instance'
        )
    return settings


@discordbot_api.delete("", status_code=HTTPStatus.OK)
async def api_extension_delete(usr: str = Query(...)):
    settings = await get_discordbot_settings(usr)
    if settings:
        await stop_bot(settings)
        await delete_discordbot_settings(settings.admin)


# Users


@discordbot_api.get(
    "/bot",
    description="Get the current status of your registered bot",
    status_code=HTTPStatus.OK,
    response_model=BotInfo
)
async def api_bot_status(bot_settings: BotSettings = Depends(require_bot_settings)):
    client = get_client(bot_settings.token)
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.post(
    "/bot",
    description="Create and start a new bot (only one per user)",
    status_code=HTTPStatus.OK,
    response_model=BotInfo
)
async def api_create_bot(data: CreateBotSettings,
                         wallet_type: WalletTypeInfo = Depends(require_admin_key)):
    bot_settings = await create_discordbot_settings(data, wallet_type.wallet.user)
    if not bot_settings.standalone:
        client = await start_bot(bot_settings)
    else:
        client = None
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.delete(
    "/bot",
    status_code=HTTPStatus.OK,
)
async def api_delete_bot(bot_settings: BotSettings = Depends(require_bot_settings)):
    if not bot_settings.standalone:
        await stop_bot(bot_settings)
    await delete_discordbot_settings(bot_settings.admin)


@discordbot_api.patch(
    "/bot",
    status_code=HTTPStatus.OK,
)
async def api_update_bot(data: UpdateBotSettings, bot_settings: BotSettings = Depends(require_bot_settings)):
    bot_settings = await update_discordbot_settings(data, bot_settings.admin)
    if not bot_settings.standalone:
        await start_bot(bot_settings)


@discordbot_api.get("/bot/start", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_start(bot_settings: BotSettings = Depends(require_bot_settings)):
    if bot_settings.standalone:
        raise HTTPException(status_code=400, detail='Standalone bot cannot be started')
    client = await start_bot(bot_settings)
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.get("/bot/stop", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_stop(bot_settings: BotSettings = Depends(require_bot_settings)):
    if bot_settings.standalone:
        raise HTTPException(status_code=400, detail='Standalone bot cannot be stopped')
    client = await stop_bot(bot_settings)
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.get("/users", status_code=HTTPStatus.OK, response_model=list[DiscordUser])
async def api_discordbot_users(bot_settings: BotSettings = Depends(require_bot_settings)):
    filters = Filters(
        filters=[Filter(field='extra', nested=['discord_id'], values=['null'], op=Operator.NE)]
    )
    users = await get_usermanager_users(bot_settings.admin,
                                        filters=filters)
    results = []
    for user in users:
        discord_id = user.extra['discord_id']
        user_dict = user.dict()
        user_dict['avatar_url'] = user.extra.get('discord_avatar_url')
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
