import asyncio
from argparse import ArgumentParser

import discord.utils
from discordbot.client import create_client
from httpx import AsyncClient

from .settings import StandaloneSettings

parser = ArgumentParser()
parser.add_argument("--lnbits-admin-key", required=False)
parser.add_argument("--lnbits-url", required=False)


async def run():
    args = parser.parse_args()

    settings = StandaloneSettings()
    if args.lnbits_admin_key:
        settings.lnbits_admin_key = args.lnbits_admin_key
    if args.lnbits_url:
        settings.lnbits_url = args.lnbits_url

    assert settings.lnbits_admin_key, "Admin key is required"
    assert settings.lnbits_url, "Lnbits url is required"

    async with AsyncClient() as http:
        if not settings.data_folder.is_dir():
            settings.data_folder.mkdir()
        client = create_client(
            settings.lnbits_admin_key,
            http,
            settings.lnbits_url,
            str(settings.data_folder),
        )
        if not settings.discord_bot_token:
            bot = await client.api.request(
                "GET", "/bot", key=settings.lnbits_admin_key, extension="discordbot"
            )
            settings.discord_bot_token = bot["token"]

        discord.utils.setup_logging()

        async with client:
            await client.start(settings.discord_bot_token)


def start_bot():
    asyncio.run(run())


if __name__ == "__main__":
    start_bot()
