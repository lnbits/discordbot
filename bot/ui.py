from __future__ import annotations
import discord

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import LnbitsInteraction

from lnbits.core.models import Wallet as FullWallet
from lnbits.core import api_payments_pay_invoice, get_wallet
from lnbits.requestvars import g
from ..crud import (
    get_discord_wallet,
)
from ...usermanager.models import Wallet as UMWallet


def get_amount_str(sats: int):
    btc = round(sats / 100_000_000, ndigits=8)
    return f'{sats} Satoshis / ฿{btc}'


def get_balance_str(wallet: FullWallet):
    return get_amount_str(wallet.balance_msat / 1000)


async def try_send_payment_notification(interaction: discord.Interaction,
                                        sender: discord.Member,
                                        receiver: discord.Member,
                                        amount: int,
                                        memo: str,
                                        receiver_wallet_id: str):
    receiver_wallet = await get_wallet(receiver_wallet_id)

    embed = discord.Embed(
        title='New Payment',
        color=discord.Color.yellow(),
        description=f'You received **{get_amount_str(amount)}** from {sender.mention}\n\n'
                    f'The payment happened [here]({(await interaction.original_response()).jump_url})'
    ).add_field(
        name='New Balance', value=get_balance_str(receiver_wallet)
    )

    if memo:
        embed.add_field(
            name='Memo', value=f'_{memo}_'
        )
    try:
        await receiver.send(
            embed=embed,
            view=discord.ui.View().add_item(WalletButton(wallet=receiver_wallet))
        )
    except discord.HTTPException:
        return


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

    async def callback(self, interaction: LnbitsInteraction):
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
        await try_send_payment_notification(interaction,
                                            interaction.user,
                                            self.receiver,
                                            self.amount,
                                            self.description,
                                            receiver_wallet_id=self.receiver_wallet.id)


class ClaimButton(discord.ui.Button):
    def __init__(self,
                 lnurl: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label='Claim',
            emoji='💸'
        )
        self.lnurl = lnurl

    async def callback(self, interaction: LnbitsInteraction):
        wallet = await get_discord_wallet(str(interaction.user.id),
                                          interaction.client.admin)

        lnurlParts = await interaction.client.api_request(method='get',
                                                          path=f'/lnurlscan/{self.lnurl}',
                                                          key=wallet.adminkey)

        redeem = await interaction.client.api_request(method='post',
                                                      path='/payments',
                                                      key=wallet.adminkey,
                                                      json={
                                                          "lnurl_callback": lnurlParts['callback'],
                                                          "amount": (lnurlParts['maxWithdrawable']) / 1000,
                                                          "memo": lnurlParts['defaultDescription'],
                                                          "out": False,
                                                          "unit": "sat"
                                                      })

        await interaction.response.edit_message(
            view=discord.ui.View().add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    label=f'Claimed by {interaction.user.display_name}',
                    emoji='💸',
                    disabled=True
                )
            ),
            attachments=[]
        )
