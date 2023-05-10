import asyncio
from typing import Optional

import httpx

from lnbits.core import get_user
from lnbits.extensions.discordbot.crud import get_all_discordbot_settings
from lnbits.extensions.discordbot.discordbot.client import LnbitsClient, create_client
from lnbits.extensions.discordbot.models import BotSettings
from lnbits.settings import settings

from . import discordbot_ext

http_client: Optional[httpx.AsyncClient] = None

clients: dict[str, LnbitsClient] = {}


def get_client(token: str) -> Optional[LnbitsClient]:
    return clients.get(token)


async def start_bot(bot_settings: BotSettings):
    token = bot_settings.token

    admin_user = await get_user(bot_settings.admin)
    admin_key = admin_user.wallets[0].adminkey

    client = clients.get(token)

    if not client or client.is_closed:
        client = create_client(
            admin_key, http_client, settings.lnbits_baseurl, settings.lnbits_data_folder
        )
        clients[token] = client
    else:
        return client

    await client.login(token)

    async def runner():
        async with client:
            await client.connect()

    asyncio.create_task(runner())

    # Wait a bit for client to connect
    waiting = 0
    while not client.is_ready() and waiting < 5:
        await asyncio.sleep(0.25)
        waiting += 0.25
    return client


async def stop_bot(bot_settings: BotSettings):
    token = bot_settings.token
    client = clients.get(token)
    if client:
        await client.close()
    return client


async def launch_all():
    await asyncio.sleep(1)
    for settings in await get_all_discordbot_settings():
        if not settings.standalone:
            await start_bot(settings)


@discordbot_ext.on_event("startup")
async def on_startup():
    global http_client
    http_client = httpx.AsyncClient()
    asyncio.create_task(launch_all())


@discordbot_ext.on_event("shutdown")
async def on_shutdown():
    global http_client
    for client in clients.values():
        await client.close()
    await http_client.aclose()
