import asyncio
from asyncio.subprocess import Process
from typing import Optional
from loguru import logger

import httpx

from lnbits.core import get_user
from lnbits.settings import settings

from . import discordbot_ext
from .crud import get_all_discordbot_settings
from .models import BotSettings

http_client: Optional[httpx.AsyncClient] = None

running: dict[str, asyncio.Task] = {}


async def run_process(*args, on_line=None, **kwargs):
    """
    Call a subprocess, waiting for it to finish. If it exits with a non-zero code, an exception is thrown.
    """
    kwargs["stdout"] = kwargs["stderr"] = asyncio.subprocess.PIPE
    process = await asyncio.create_subprocess_shell(*args, **kwargs)

    try:
        await asyncio.gather(
            _read_stream(process.stdout, on_line=on_line),
            _read_stream(process.stderr, on_line=on_line),
        )

        code = process.returncode
        if code != 0:
            raise ValueError(f"Non-zero exit code by {process}")
    except asyncio.CancelledError:
        process.kill()
        raise


async def _read_stream(stream, on_line=None):
    while True:
        raw = await stream.readline()
        if raw:
            line = raw.decode().strip("\n").strip()

            if "ERROR" in line or "WARNING" in line or "INFO" in line:
                msg = "DISCORD: " + line.split("]")[2]
            else:
                msg = line

            if "ERROR" in line:
                logger.error(msg)
            elif "WARNING" in line:
                logger.warning(msg)
            elif "INFO" in line:
                logger.info(msg)
            else:
                print(msg)

            if on_line:
                on_line(line)
        else:
            break


def is_running(token: str) -> bool:
    task = running.get(token)
    return bool(task and not task.done())


async def start_bot(bot_settings: BotSettings, restart=True):
    token = bot_settings.token

    if is_running(token):
        return

    admin_user = await get_user(bot_settings.admin)
    admin_key = admin_user.wallets[0].adminkey

    fut = asyncio.get_running_loop().create_future()

    def on_line(msg):
        if "connected" in msg and not fut.done():
            fut.set_result(True)

    async def runner():
        try:
            task = asyncio.create_task(
                run_process(
                    f"""
                    cd {settings.lnbits_path}/extensions/discordbot && 
                    poetry install --no-root && 
                    poetry run bot --lnbits-admin-key {admin_key} --lnbits-url {settings.lnbits_baseurl}
                    """,
                    on_line=on_line,
                )
            )
            running[token] = task
            await task
        except ValueError:
            if restart:
                logger.info(f"Restarting bot by {bot_settings.admin}")
                await start_bot(bot_settings, restart=False)

    asyncio.create_task(runner())

    # Wait for bot to come online
    return await asyncio.wait_for(fut, timeout=30)


async def stop_bot(bot_settings: BotSettings):
    task = running.pop(bot_settings.token)
    if task:
        task.cancel()


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
    for task in running.values():
        task.cancel()
    if http_client:
        await http_client.aclose()
