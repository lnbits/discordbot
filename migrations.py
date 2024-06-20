import json

from lnbits.db import Database


async def m001_initial(db):
    """
    Initial users table.
    """
    await db.execute(
        """
        CREATE TABLE discordbot.users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            admin TEXT NOT NULL,
            discord_id TEXT
        );
    """
    )

    """
    Initial wallets table.
    """
    await db.execute(
        """
        CREATE TABLE discordbot.wallets (
            id TEXT PRIMARY KEY,
            admin TEXT NOT NULL,
            name TEXT NOT NULL,
            "user" TEXT NOT NULL,
            adminkey TEXT NOT NULL,
            inkey TEXT NOT NULL
        )
    """
    )


async def m002_major_overhaul(db: Database):
    # Initial settings table
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS discordbot.bots (
            admin TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            standalone BOOLEAN NOT NULL DEFAULT TRUE,
            name TEXT NULL,
            avatar_url TEXT NULL,
            CONSTRAINT admin_account_id 
            FOREIGN KEY(admin)
            REFERENCES accounts(id)
            ON DELETE cascade
        );
        """
    )
