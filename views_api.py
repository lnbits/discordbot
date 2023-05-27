from http import HTTPStatus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.datastructures import MultiDict

from lnbits.decorators import WalletTypeInfo, require_admin_key
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

from .tasks import start_bot, stop_bot, is_running


discordbot_api: APIRouter = APIRouter(prefix="/api/v1", tags=["discordbot"])


async def require_bot_settings(
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
):
    settings = await get_discordbot_settings(wallet_info.wallet.user)
    if not settings:
        raise HTTPException(status_code=400, detail="No bot created")
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
    return BotInfo(**bot_settings.dict(), online=is_running(bot_settings.token))


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
    if bot_settings:
        if not bot_settings.standalone:
            if wallet_type.wallet.id == settings.super_user:
                online = await start_bot(bot_settings)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Only the super user can host directly on the instance",
                )
        else:
            online = None
        return BotInfo(**bot_settings.dict(), online=online)
    else:
        raise HTTPException(status_code=500)


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
    return await update_discordbot_settings(data, bot_settings.admin)


@discordbot_api.get("/bot/start", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_start(bot_settings: BotSettings = Depends(require_bot_settings)):
    if bot_settings.standalone:
        raise HTTPException(status_code=400, detail="Standalone bot cannot be started")
    online = await start_bot(bot_settings)
    return BotInfo(**bot_settings.dict(), online=online)


@discordbot_api.get("/bot/stop", status_code=HTTPStatus.OK, response_model=BotInfo)
async def api_bot_stop(bot_settings: BotSettings = Depends(require_bot_settings)):
    if bot_settings.standalone:
        raise HTTPException(status_code=400, detail="Standalone bot cannot be stopped")
    await stop_bot(bot_settings)
    return BotInfo(**bot_settings.dict(), online=False)


@discordbot_api.get(
    "/users",
    description="Get a list of users registered for your bot",
    status_code=HTTPStatus.OK,
    response_model=list[DiscordUser],
    openapi_extra=generate_filter_params_openapi(DiscordFilters),
    dependencies=[Depends(require_bot_settings)],
)
async def api_discordbot_users(
    request: Request,
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
):
    # the params are simply forwared to the usermanager endpoint.
    # any filters with discord_id are prefixed with extra
    # functionality for this should probably provided by the `Filters` class
    params = MultiDict()
    params["extra.discord_id[ne]"] = None
    for key, val in request.query_params.items():
        if key.startswith("discord_id"):
            params[f"extra.{key}"] = val
        else:
            params[key] = val
    params["api-key"] = wallet_info.wallet.adminkey
    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.lnbits_baseurl + "usermanager/api/v1/users", params=params
        )
        response.raise_for_status()
        users = response.json()
    results = []
    for user in users:
        user["discord_id"] = user["extra"]["discord_id"]
        user["avatar_url"] = user["extra"].get("discord_avatar_url")
        results.append(user)
    return results


discordbot_ext.include_router(discordbot_api)
