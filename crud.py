from typing import Optional

from . import db
from .models import BotSettings, CreateBotSettings, UpdateBotSettings


async def get_discordbot_settings(admin_id: str) -> Optional[BotSettings]:
    row = await db.fetchone(
        "SELECT * FROM discordbot.bots WHERE admin = ?", (admin_id,)
    )
    return BotSettings(**row) if row else None


async def get_all_discordbot_settings() -> list[BotSettings]:
    rows = await db.fetchall("SELECT * FROM discordbot.bots")
    return [BotSettings(**row) for row in rows]


async def create_discordbot_settings(data: CreateBotSettings, admin_id: str):
    await db.execute(
        f"""
        INSERT INTO discordbot.bots (admin, token, standalone) 
        VALUES (?, ?, ?)
        ON CONFLICT (admin) DO 
            UPDATE SET token = '{data.token}' 
        """,
        (admin_id, data.token, data.standalone),
    )
    return await get_discordbot_settings(admin_id)


async def update_discordbot_settings(data: UpdateBotSettings, admin_id: str):
    updates = []
    values = []
    for key, val in data.dict(exclude_unset=True).items():
        updates.append(f"{key} = ?")
        values.append(val)
    values.append(admin_id)
    await db.execute(
        f"""
        UPDATE discordbot.bots 
        SET {", ".join(updates)}
        WHERE admin = ?
        """,
        values,
    )
    return await get_discordbot_settings(admin_id)


async def delete_discordbot_settings(admin_id: str):
    result = await db.execute(
        "DELETE FROM discordbot.bots WHERE admin = ?", (admin_id,)
    )
    assert result.rowcount == 1, "Could not create settings"
