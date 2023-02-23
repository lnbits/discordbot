import discord

from lnbits.core import api_payments_pay_invoice
from lnbits.requestvars import g
from ..crud import (
    get_discord_wallet,
)
from ...usermanager.models import Wallet as UMWallet

MY_GUILD = discord.Object(id=715507174167806042)  # replace with your guild id


class WalletButton(discord.ui.Button):
    def __init__(self, wallet: UMWallet):
        walletURL = g().base_url + f'/wallet?usr={wallet.user}&wal={wallet.id}'
        super().__init__(
            label="Go to my wallet",
            emoji="💰",
            style=discord.ButtonStyle.link,
            url=walletURL
        )


class PayButton(discord.ui.Button):
    def __init__(self,
                 payment_request: str,
                 receiver: discord.Member,
                 receiver_wallet: UMWallet,
                 amount: int,
                 description: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label='Pay Now',
            emoji='💸'
        )
        self.payment_request = payment_request
        self.receiver = receiver
        self.receiver_wallet = receiver_wallet
        self.amount = amount
        self.description = description

    async def callback(self, interaction: discord.Interaction):

        if interaction.user == self.receiver:
            await interaction.response.send_message(
                ephemeral=True,
                content='You cant pay yourself'
            )
            return

        wallet = await get_discord_wallet(str(interaction.user.id),
                                          interaction.client.admin)

        await api_payments_pay_invoice(self.payment_request, wallet)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title='Pay Me!',
                description=f'Payed by {interaction.user.mention}',
                color=discord.Color.yellow()
            ).add_field(
                name='Amount',
                value=get_amount_str(self.amount)
            ).add_field(
                name='Description',
                value=self.description
            ),
            view=None,
            attachments=[]
        )

        await send_payment_notification(interaction,
                                        interaction.user,
                                        self.receiver,
                                        self.amount,
                                        self.description,
                                        receiver_wallet_id=self.receiver_wallet.id)
