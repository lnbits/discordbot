import asyncio

from bot.client import create_client
from httpx import AsyncClient

from .settings import StandaloneSettings

settings = StandaloneSettings()


async def run():
    async with AsyncClient() as http:
        if not settings.data_folder.is_dir():
            settings.data_folder.mkdir()
        client = create_client(
            settings.lnbits_admin_key,
            http,
            settings.lnbits_url,
            str(settings.data_folder)
        )
        if not settings.discord_bot_token:
            bot = await client.api.request('GET', '/bot',
                                           key=settings.lnbits_admin_key,
                                           extension='discordbot')
            settings.discord_bot_token = bot['token']

        async with client:
            await client.start(settings.discord_bot_token)


def start_bot():
    asyncio.run(run())


if __name__ == '__main__':
    start_bot()
