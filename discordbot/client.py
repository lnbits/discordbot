from __future__ import annotations

import logging
import os.path
import random
from typing import TYPE_CHECKING, Optional, Union

import discord
import discord.utils
import pyqrcode
from discord import app_commands
from httpx import AsyncClient

from .api import LnbitsAPI
from .settings import discord_settings
from .ui import (
    ClaimButton,
    CoinFlipView,
    PayButton,
    TipButton,
    WalletButton,
    get_amount_str,
)

if discord_settings.discord_dev_guild:
    DEV_GUILD = discord.Object(id=discord_settings.discord_dev_guild)
else:
    DEV_GUILD = None

DiscordUser = Union[discord.Member, discord.User]


class LnbitsClient(discord.Client):
    def __init__(
        self,
        *,
        admin_key: str,
        http: AsyncClient,
        lnbits_url: str,
        data_folder: str,
        **options,
    ):
        super().__init__(**options)
        self.admin_key = admin_key
        self.tree = app_commands.CommandTree(self)
        self.lnbits_url = lnbits_url
        self.data_folder = data_folder
        self.api = LnbitsAPI(admin_key=admin_key, http=http, lnbits_url=lnbits_url)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # This copies the global commands over to your guild.
        if DEV_GUILD:
            self.tree.copy_global_to(guild=DEV_GUILD)
        await self.tree.sync(guild=DEV_GUILD)

    async def try_send_payment_notification(
        self,
        interaction: LnbitsInteraction,
        sender: Union[discord.Member, discord.User],
        receiver: Union[discord.Member, discord.User],
        amount: int,
        memo: Optional[str] = None,
    ):
        receiver_wallet = await self.api.get_user_wallet(receiver)
        new_balance = await self.api.get_user_balance(receiver)

        embed = discord.Embed(
            title="New Payment",
            color=discord.Color.yellow(),
            description=f"You received **{get_amount_str(amount)}** from {sender.mention}\n\n"
            f"The payment happened [here]({(await interaction.original_response()).jump_url})",
        ).add_field(name="New Balance", value=get_amount_str(new_balance))

        if memo:
            embed.add_field(name="Memo", value=f"_{memo}_")
        try:
            await receiver.send(
                embed=embed,
                view=discord.ui.View().add_item(
                    WalletButton(self.lnbits_url, wallet=receiver_wallet)
                ),
            )
        except discord.HTTPException:
            return


class LnbitsInteraction(discord.Interaction):
    if TYPE_CHECKING:

        @property
        def client(self) -> LnbitsClient:
            """:class:`Client`: The client that is handling this interaction.

            Note that :class:`AutoShardedClient`, :class:`~.commands.Bot`, and
            :class:`~.commands.AutoShardedBot` are all subclasses of client.
            """
            return self._client  # type: ignore

        @property
        def response(self) -> discord.InteractionResponse:
            """:class:`Client`: The client that is handling this interaction.

            Note that :class:`AutoShardedClient`, :class:`~.commands.Bot`, and
            :class:`~.commands.AutoShardedBot` are all subclasses of client.
            """
            return self.response  # type: ignore


intents = discord.Intents.default()
intents.members = True


def create_client(admin_key: str, http: AsyncClient, lnbits_url: str, data_folder: str):
    client = LnbitsClient(
        intents=intents,
        admin_key=admin_key,
        http=http,
        lnbits_url=lnbits_url,
        data_folder=data_folder,
    )

    @client.event
    async def on_ready():
        logging.info(f"Logged in as {client.user} (ID: {client.user.id})")
        await client.api.request(
            "PATCH",
            "/bot",
            client.admin_key,
            extension="discordbot",
            json={
                "name": client.user.name,
                "avatar_url": client.user.display_avatar.url,
            },
        )

    @client.tree.command(name="create", description="Create a wallet for your user")
    async def create(interaction: LnbitsInteraction):
        wallet = await client.api.get_or_create_wallet(interaction.user)

        await interaction.response.send_message(
            content="You have a wallet!",
            view=discord.ui.View().add_item(
                WalletButton(interaction.client.lnbits_url, wallet=wallet)
            ),
            ephemeral=True,
        )

    @client.tree.command(name="balance", description="Check the balance of your wallet")
    async def balance(interaction: LnbitsInteraction):
        await interaction.response.defer(ephemeral=True)

        wallet = await client.api.get_or_create_wallet(interaction.user)
        balance = await client.api.get_user_balance(interaction.user)

        await interaction.followup.send(
            ephemeral=True,
            content=f"Your balance: **{get_amount_str(balance)}**",
            view=discord.ui.View().add_item(
                WalletButton(interaction.client.lnbits_url, wallet=wallet)
            ),
        )

    @client.tree.command(name="tip", description="Send some sats to another user")
    @app_commands.describe(
        member="Who do you want to tip?",
        amount="Amount of sats to tip",
        memo="Memo to append",
    )
    @app_commands.guild_only()
    async def tip(
        interaction: LnbitsInteraction,
        member: discord.Member,
        amount: int,
        memo: Optional[str] = None,
    ):
        await TipButton.execute(interaction, member, amount, memo)

    @client.tree.command(
        name="donate", description="Create an open invoice for anyone to claim."
    )
    @app_commands.describe(
        amount="The amount of satoshis payable in the invoice",
        description="Memo of the donation",
    )
    @app_commands.guild_only()
    async def donate(interaction: LnbitsInteraction, amount: int, description: str):
        wallet = await client.api.get_user_wallet(interaction.user)

        await client.api.request(
            "POST",
            "/extensions",
            extension="usermanager",
            params={"userid": wallet.user, "extension": "withdraw", "active": True},
        )

        resp = await client.api.request(
            method="post",
            path="/links",
            extension="withdraw",
            key=wallet.adminkey,
            json={
                "title": description,
                "min_withdrawable": amount,
                "max_withdrawable": amount,
                "uses": 1,
                "wait_time": 1,
                "is_unique": True,
            },
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="Donation",
                description=f"{interaction.user.mention} is donating **{get_amount_str(amount)}**",
                color=discord.Color.yellow(),
            )
            .add_field(name="Description", value=description)
            .add_field(name="LNURL", value=resp["lnurl"], inline=False),
            view=discord.ui.View().add_item(ClaimButton(lnurl=resp["lnurl"])),
        )

    @client.tree.command(description="Creates an invoice for the users wallet")
    @app_commands.describe(
        amount="The amount of satoshis payable in the invoice",
        description="Memo of the donation",
    )
    @app_commands.guild_only()
    async def payme(interaction: LnbitsInteraction, amount: int, description: str):
        wallet = await client.api.get_user_wallet(interaction.user)

        # invoice = await api_payments_create_invoice(
        #    CreateInvoiceData(
        #        out=False,
        #        amount=amount,
        #        memo=description
        #    ),
        #    wallet
        # )

        invoice = await client.api.request(
            "POST",
            "/payments",
            wallet.adminkey,
            json={"out": False, "amount": amount, "memo": description, "unit": "sat"},
        )

        qr_code = pyqrcode.create(invoice["payment_request"])

        temp_path = os.path.join(client.data_folder, "temp.png")
        qr_code.png(file=temp_path, scale=5)

        await interaction.response.send_message(
            embed=discord.Embed(title="Pay Me!", color=discord.Color.yellow())
            .add_field(name="Amount", value=get_amount_str(amount))
            .add_field(name="Description", value=description)
            .set_image(url="attachment://qr.png")
            .add_field(
                name="Payment Request", value=invoice["payment_request"], inline=False
            ),
            file=discord.File(temp_path, "qr.png"),
            view=discord.ui.View().add_item(
                PayButton(
                    payment_request=invoice["payment_request"],
                    receiver=interaction.user,
                    receiver_wallet=wallet,
                    amount=amount,
                    description=description,
                )
            ),
        )

    @client.tree.command(description="Creates an invoice for the users wallet")
    @app_commands.describe(
        amount="The amount of sats to give to each use",
        description="What to send along",
        users="To how many users do you want to give sats?",
        roles="Limit selection to certain roles",
    )
    @app_commands.guild_only()
    async def rain(
        interaction: LnbitsInteraction,
        amount: int,
        description: str,
        users: int,
        roles: str = None,
    ):
        parsedRoles = []
        if roles:
            split = roles.split(" ")
            for raw_member in split:
                if len(raw_member) > 4:
                    # '<@&937457548427141151>'
                    id = int(raw_member[3:-1])
                    result = interaction.guild.get_role(id)
                    # if not result:
                    #    result = await interaction.guild.fetch_roles(id)

                    if result:
                        parsedRoles.append(result)

        validMembers = []
        if users:
            # interaction.guild.query_members()
            # await interaction.guild.fetch_members()

            validMembers: list[discord.Member] = [
                member
                for member in interaction.channel.members
                if (
                    (
                        any(role in member.roles for role in parsedRoles)
                        or not parsedRoles
                    )
                    and not member.bot
                    and member != interaction.user
                )
            ]

        balance = await client.api.get_user_balance(interaction.user)

        if balance < amount:
            return await interaction.response.send_message(
                content="You do not have enough balance", ephemeral=True
            )

        await interaction.response.defer()

        membersSent = []

        while users > 0 and len(validMembers) > 0:
            idx = random.randint(0, len(validMembers) - 1)

            member = validMembers.pop(idx)
            if member:
                wallet = await client.api.send_payment(
                    interaction.user, member, amount, description
                )

                membersSent.append(member)
                users -= 1

        await interaction.followup.send(
            embed=discord.Embed(
                color=discord.Color.yellow(),
                title=f"💸 Rain by {interaction.user.display_name} 💸",
                description=f"Sent **{get_amount_str(amount)}** to\n"
                + "\n".join(member.mention for member in membersSent),
            )
        )

        for member in membersSent:
            await client.try_send_payment_notification(
                interaction, interaction.user, member, amount, description
            )

    @client.tree.command(description="Creates an coinflip everyone can join")
    @app_commands.describe(
        entry="The entry price",
        description="Whats it about?",
    )
    @app_commands.guild_only()
    async def coinflip(interaction: LnbitsInteraction, entry: int, description: str):
        view = CoinFlipView(
            initiator=interaction.user, entry=entry, description=description
        )

        await interaction.response.send_message(
            embed=view.get_current_embed(), view=view
        )

    return client
