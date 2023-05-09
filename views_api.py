from http import HTTPStatus

from fastapi import APIRouter, Depends, Query
from starlette.exceptions import HTTPException

from lnbits.db import Filter, Filters, Operator
from lnbits.decorators import WalletTypeInfo, parse_filters, require_admin_key
from lnbits.extensions.usermanager.crud import get_usermanager_users
from lnbits.helpers import generate_filter_params_openapi
from lnbits.settings import settings

from . import discordbot_ext
from .crud import (
    create_discordbot_settings,
    delete_discordbot_settings,
    get_discordbot_settings,
    update_discordbot_settings,
)
from .models import (
    BotInfo,
    BotSettings,
    CreateBotSettings,
    DiscordFilters,
    DiscordUser,
    UpdateBotSettings,
)

try:
    from .tasks import get_client, start_bot, stop_bot

    can_run_bot = True
except ImportError as e:

    def get_client(token: str):
        return None

    async def start_bot(bot_settings: BotSettings):
        return None

    async def stop_bot(bot_settings: BotSettings):
        return None

    can_run_bot = False

discordbot_api: APIRouter = APIRouter(prefix="/api/v1", tags=["discordbot"])


async def require_bot_settings(
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
):
    settings = await get_discordbot_settings(wallet_info.wallet.user)
    if not settings:
        raise HTTPException(status_code=400, detail="No bot created")
    if not settings.standalone and not can_run_bot:
        raise HTTPException(
            status_code=400, detail="Can not run discord bots on this instance"
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
    response_model=BotInfo,
)
async def api_bot_status(bot_settings: BotSettings = Depends(require_bot_settings)):
    client = get_client(bot_settings.token)
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.post(
    "/bot",
    description="Create and start a new bot (only one per user)",
    status_code=HTTPStatus.OK,
    response_model=BotInfo,
)
async def api_create_bot(
    data: CreateBotSettings, wallet_type: WalletTypeInfo = Depends(require_admin_key)
):
    bot_settings = await create_discordbot_settings(data, wallet_type.wallet.user)
    if not bot_settings.standalone:
        if wallet_type.wallet.id == settings.super_user:
            client = await start_bot(bot_settings)
        else:
            raise HTTPException(
                status_code=400,
                detail="Only the super user can host directly on the instance",
            )
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
async def api_update_bot(
    data: UpdateBotSettings, bot_settings: BotSettings = Depends(require_bot_settings)
):
    bot_settings = await update_discordbot_settings(data, bot_settings.admin)
    if not bot_settings.standalone:
        await start_bot(bot_settings)


@discordbot_api.get("/bot/start", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_start(bot_settings: BotSettings = Depends(require_bot_settings)):
    if bot_settings.standalone:
        raise HTTPException(status_code=400, detail="Standalone bot cannot be started")
    client = await start_bot(bot_settings)
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.get("/bot/stop", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_stop(bot_settings: BotSettings = Depends(require_bot_settings)):
    if bot_settings.standalone:
        raise HTTPException(status_code=400, detail="Standalone bot cannot be stopped")
    client = await stop_bot(bot_settings)
    return BotInfo.from_client(bot_settings, client)


@discordbot_api.get(
    "/users",
    description="Get a list of users registered for your bot",
    status_code=HTTPStatus.OK,
    response_model=list[DiscordUser],
    openapi_extra=generate_filter_params_openapi(DiscordFilters),
)
async def api_discordbot_users(
    bot_settings: BotSettings = Depends(require_bot_settings),
    filters: Filters = Depends(parse_filters(DiscordFilters)),
):
    for filter in filters.filters:
        if filter.field == "discord_id":
            filter.field = "extra"
            filter.nested = ["discord_id"]
    filters.filters.append(
        Filter(field="extra", nested=["discord_id"], values=["null"], op=Operator.NE)
    )
    users = await get_usermanager_users(bot_settings.admin, filters=filters)
    results = []
    for user in users:
        user_dict = user.dict()
        user_dict["discord_id"] = user.extra["discord_id"]
        user_dict["avatar_url"] = user.extra.get("discord_avatar_url")
        results.append(user_dict)
    return results


discordbot_ext.include_router(discordbot_api)
