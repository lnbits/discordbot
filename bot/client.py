import asyncio
import io
import random
from typing import Optional

import discord
import discord.utils
import pyqrcode
from discord import app_commands
from fastapi import HTTPException
from httpx import AsyncClient
from loguru import logger

from lnbits.core import CreateInvoiceData, api_payments_create_invoice
from lnbits.core.crud import get_wallet, update_user_extension
from lnbits.requestvars import g

from ..crud import get_discord_wallet, get_or_create_wallet
from ..models import BotSettings
from ..settings import discord_settings
from .ui import (
    ClaimButton,
    PayButton,
    WalletButton,
    get_amount_str,
    get_balance_str,
    try_send_payment_notification,
)

# discord.utils.setup_logging()


if discord_settings.discord_dev_guild:
    DEV_GUILD = discord.Object(id=discord_settings.discord_dev_guild)
else:
    DEV_GUILD = None


class LnbitsClient(discord.Client):
    def __init__(self, *, admin: str, http: AsyncClient, **options):
        super().__init__(**options)
        self.admin = admin
        self.tree = app_commands.CommandTree(self)
        self.lnbits_http = http

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # This copies the global commands over to your guild.
        self.tree.copy_global_to(guild=DEV_GUILD)
        await self.tree.sync(guild=DEV_GUILD)

    async def api_request(self,
                          method: str,
                          path: str,
                          key: str,
                          extension: str = None,
                          **kwargs):
        self.lnbits_http.headers['X-API-KEY'] = key

        response = await self.lnbits_http.request(
            method,
            url=g().base_url + ('/' + extension if extension else '') + '/api/v1' + path,
            **kwargs
        )

        return response.json()

    async def send_payment(self,
                           sender: discord.Member,
                           receiver: discord.Member,
                           amount: int,
                           memo: str):
        sender_wallet = await get_discord_wallet(str(sender.id),
                                                 self.admin)

        receiver_wallet = await get_or_create_wallet(username=receiver.name,
                                                     discord_id=str(receiver.id),
                                                     admin_id=self.admin)

        invoice = await self.api_request('POST', '/payments',
                                         receiver_wallet.adminkey,
                                         json=dict(
                                             out=False,
                                             amount=amount,
                                             memo=memo,
                                             unit="sat"
                                         ))

        response = await self.api_request('POST', '/payments',
                                          sender_wallet.adminkey,
                                          json={
                                              "out": True,
                                              "bolt11": invoice["payment_request"]
                                          })

        # invoice = await api_payments_create_invoice(
        #    CreateInvoiceData(
        #        out=False,
        #        amount=amount,
        #        memo=memo,
        #        unit="sat"
        #    ),
        #    receiver_wallet
        # )
        # await api_payments_pay_invoice(
        #    invoice["payment_request"],
        #    sender_wallet
        # )

        return receiver_wallet


class LnbitsInteraction(discord.Interaction):

    @property
    def client(self) -> LnbitsClient:
        """:class:`Client`: The client that is handling this interaction.

        Note that :class:`AutoShardedClient`, :class:`~.commands.Bot`, and
        :class:`~.commands.AutoShardedBot` are all subclasses of client.
        """
        return self._client  # type: ignore


intents = discord.Intents.default()
intents.members = True
clients: dict[str, LnbitsClient] = {}


def get_client(token: str) -> Optional[LnbitsClient]:
    return clients.get(token)


async def start_bot(bot_settings: BotSettings, http: AsyncClient):
    token = bot_settings.bot_token
    if token not in clients:
        clients[token] = create_client(bot_settings, http)
    else:
        if clients[token].is_closed():
            clients[token] = create_client(bot_settings, http)
        else:
            return clients[token]

    client = clients[token]
    await client.login(token)
    asyncio.create_task(
        client.connect()
    )
    return client


async def stop_bot(bot_settings: BotSettings):
    token = bot_settings.bot_token
    client = clients.get(token)
    if client:
        await client.close()
    return client


def create_client(bot_settings: BotSettings, http: AsyncClient):
    client = LnbitsClient(intents=intents, admin=bot_settings.admin, http=http)

    @client.event
    async def on_ready():
        print(f'Logged in as {client.user} (ID: {client.user.id})')
        print('------')

    @client.event
    async def on_command_error(ctx, error):
        logger.error(error)

    @client.tree.command(
        name="create",
        description="Create a wallet for your user"
    )
    async def create(interaction: LnbitsInteraction):
        wallet = await get_or_create_wallet(interaction.user.name,
                                            str(interaction.user.id),
                                            interaction.client.admin)

        await interaction.response.send_message(
            content='You have a wallet!',
            view=discord.ui.View().add_item(WalletButton(wallet=wallet)),
            ephemeral=True
        )

    @client.tree.command(
        name="balance",
        description="Check the balance of your wallet"
    )
    async def balance(interaction: LnbitsInteraction):
        # await interaction.response.defer(ephemeral=True)

        wallet = await get_discord_wallet(str(interaction.user.id),
                                          interaction.client.admin)

        detailed_wallet = await get_wallet(wallet.id)

        await interaction.response.send_message(
            ephemeral=True,
            content=f'Your balance: **{get_balance_str(detailed_wallet)}**',
            view=discord.ui.View().add_item(WalletButton(wallet=wallet))
        )

    @client.tree.command(
        name="tip",
        description="Check the balance of your wallet"
    )
    @app_commands.describe(
        member='Who do you want to tip?',
        amount='Amount of sats to tip',
        memo="Memo to append"
    )
    @app_commands.guild_only()
    async def tip(interaction: LnbitsInteraction, member: discord.Member, amount: int, memo: str):
        # await interaction.response.defer(ephemeral=True)

        try:
            receiver_wallet = await interaction.client.send_payment(interaction.user, member, amount, memo)
        except HTTPException as e:
            await interaction.response.send_message(content=e.detail)
            return

        embed = discord.Embed(
            title='Tip',
            color=discord.Color.yellow(),
            description=f'{interaction.user.mention} just sent **{get_amount_str(amount)}** to {member.mention}'
        )
        if memo:
            embed.add_field(name='Memo', value=memo)

        await interaction.response.send_message(embed=embed)

        await try_send_payment_notification(interaction, interaction.user, member, amount, memo, receiver_wallet.id)

    @client.tree.command(
        name="donate",
        description="Create an open invoice for anyone to claim."
    )
    @app_commands.describe(
        amount='The amount of satoshis payable in the invoice',
        description='Memo of the donation'
    )
    @app_commands.guild_only()
    async def donate(interaction: LnbitsInteraction, amount: int, description: str):

        wallet = await get_discord_wallet(discord_id=str(interaction.user.id),
                                          admin_id=interaction.client.admin)

        await update_user_extension(user_id=wallet.user, extension='withdraw', active=True)

        resp = await interaction.client.api_request(method='post',
                                                    path='/links',
                                                    extension='withdraw',
                                                    key=wallet.adminkey,
                                                    json={
                                                        "title": description,
                                                        "min_withdrawable": amount,
                                                        "max_withdrawable": amount,
                                                        "uses": 1,
                                                        "wait_time": 1,
                                                        "is_unique": True
                                                    })

        await interaction.response.send_message(
            embed=discord.Embed(
                title='Donation',
                description=f'{interaction.user.mention} is donating **{get_amount_str(amount)}**',
                color=discord.Color.yellow()
            ).add_field(
                name='Description',
                value=description
            ).add_field(
                name='LNURL',
                value=resp['lnurl'],
                inline=False
            ),
            view=discord.ui.View().add_item(
                ClaimButton(lnurl=resp['lnurl'])
            )
        )

    @client.tree.command(
        description='Creates an invoice for the users wallet'
    )
    @app_commands.describe(
        amount='The amount of satoshis payable in the invoice',
        description='Memo of the donation'
    )
    @app_commands.guild_only()
    async def payme(interaction: LnbitsInteraction, amount: int, description: str):

        wallet = await get_discord_wallet(discord_id=str(interaction.user.id),
                                          admin_id=interaction.client.admin)

        invoice = await api_payments_create_invoice(
            CreateInvoiceData(
                out=False,
                amount=amount,
                memo=description
            ),
            wallet
        )

        qr_code = pyqrcode.create(invoice['payment_request'])

        qr_code.png(file='image.png', scale=5)

        await interaction.response.send_message(
            embed=discord.Embed(
                title='Pay Me!',
                color=discord.Color.yellow()
            ).add_field(
                name='Amount',
                value=get_amount_str(amount)
            ).add_field(
                name='Description',
                value=description
            ).set_image(
                url='attachment://image.png'
            ).add_field(
                name='Payment Request',
                value=invoice['payment_request'],
                inline=False
            ),
            file=discord.File('image.png'),
            view=discord.ui.View().add_item(
                PayButton(
                    payment_request=invoice['payment_request'],
                    receiver=interaction.user,
                    receiver_wallet=wallet,
                    amount=amount,
                    description=description,
                )
            )
        )

    @client.tree.command(
        description='Creates an invoice for the users wallet'
    )
    @app_commands.describe(
        amount='The amount of sats to give to each use',
        description='What to send along',
        users='To how many users do you want to give sats?',
        roles='Limit selection to certain roles'
    )
    @app_commands.guild_only()
    async def rain(interaction: LnbitsInteraction, amount: int, description: str, users: int, roles: str = None):

        parsedRoles = []
        if roles:
            split = roles.split(' ')
            for member in split:
                if len(member) > 4:
                    # '<@&937457548427141151>'
                    id = int(member[3:-1])
                    result = interaction.guild.get_role(id)
                    # if not result:
                    #    result = await interaction.guild.fetch_roles(id)

                    if result:
                        parsedRoles.append(result)

        validMembers = []
        if users:
            # interaction.guild.query_members()
            # await interaction.guild.fetch_members()

            validMembers = [
                member for member in interaction.channel.members
                if (
                    (any(role in member.roles for role in parsedRoles) or not parsedRoles)
                    and not member.bot
                    and member != interaction.user
                )
            ]

        wallet = await get_discord_wallet(discord_id=str(interaction.user.id),
                                          admin_id=interaction.client.admin)

        details = await get_wallet(wallet.id)

        if details.balance_msat < amount * users:
            await interaction.response.send_message(content='You do not have enough balance', ephemeral=True)

        await interaction.response.defer()

        membersSent = []

        while users > 0 and len(validMembers) > 0:
            idx = random.randint(0, len(validMembers) - 1)

            member = validMembers.pop(idx)
            if member:
                wallet = await interaction.client.send_payment(interaction.user,
                                                               member,
                                                               amount,
                                                               description)

                membersSent.append(member)
                users -= 1

        await interaction.followup.send(
            embed=discord.Embed(
                color=discord.Color.yellow(),
                title=f'💸 Rain by {interaction.user.display_name} 💸',
                description=f"Sent **{get_amount_str(amount)}** to\n" + "\n".join(
                    member.mention for member in membersSent
                )
            )
        )

        for member in membersSent:
            await try_send_payment_notification(interaction,
                                                interaction.user,
                                                member,
                                                amount,
                                                description,
                                                receiver_wallet_id=wallet.id)

    return client
