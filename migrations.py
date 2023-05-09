import json

from lnbits.db import Database, POSTGRES, SQLITE


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
        CREATE TABLE IF NOT EXISTS discordbot.settings (
            admin TEXT PRIMARY KEY,
            bot_token TEXT NOT NULL UNIQUE,
            CONSTRAINT admin_account_id 
            FOREIGN KEY(admin)
            REFERENCES accounts(id)
            ON DELETE cascade
        );
    """
    )
    # Migrate old data
    if db.type == SQLITE:
        um_db = Database("ext_usermanager")
        rows = await db.fetchall("SELECT * FROM users")
        for row in rows:
            await um_db.execute(
                """
                INSERT INTO users (id, name, admin, extra) 
                VALUES (?, ?, ?, ?)
                """,
                (row["id"], row["name"], row["admin"], json.dumps({"discord_id": row["discord_id"]})),
            )
        rows = await db.fetchall("SELECT * FROM wallets")
        for row in rows:
            await um_db.execute(
                """
                INSERT INTO wallets (id, admin, name, "user", adminkey, inkey) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["id"], row["admin"], row["name"], row["user"], row["adminkey"], row["inkey"]),
            )
    else:
        await db.execute(
            """
            INSERT INTO usermanager.users (id, name, admin, extra) 
            SELECT id, name, admin, json_build_object('discord_id', discord_id) FROM discordbot.users
            """
        )
        await db.execute(
            """
            INSERT INTO usermanager.wallets (id, admin, name, "user", adminkey, inkey)  
            SELECT * FROM discordbot.wallets
            """
        )

    # Drop old tables
    await db.execute("DROP TABLE discordbot.users")
    await db.execute("DROP TABLE discordbot.wallets")


async def m003_add_start_to_settings(db: Database):
    await db.execute(
        """
        ALTER TABLE discordbot.settings
        ADD COLUMN standalone BOOLEAN NOT NULL DEFAULT TRUE
    """
    )
    await db.execute(
        """
        ALTER TABLE discordbot.settings
        ADD COLUMN name TEXT NULL
    """
    )
    await db.execute(
        """
        ALTER TABLE discordbot.settings
        ADD COLUMN avatar_url TEXT NULL
        """
    )
    await db.execute(
        """
        ALTER TABLE discordbot.settings
        RENAME COLUMN bot_token TO token
        """
    )
    # rename settings to bots
    await db.execute(
        """
        ALTER TABLE discordbot.settings RENAME TO bots;
        """
    )
