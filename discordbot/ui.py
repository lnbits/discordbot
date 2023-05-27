from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional

import discord
from httpx import HTTPStatusError

if TYPE_CHECKING:
    from .client import LnbitsInteraction

from .models import Wallet


def get_amount_str(sats: int):
    btc = round(sats / 100_000_000, ndigits=8)
    return f"{sats} Satoshis / ฿{btc}"


class WalletButton(discord.ui.Button):
    def __init__(self, base_url: str, wallet: Wallet):
        walletURL = base_url + f"wallet?usr={wallet.user}&wal={wallet.id}"
        super().__init__(
            label="Go to my wallet",
            emoji="💰",
            style=discord.ButtonStyle.link,
            url=walletURL,
        )


class TipButton(discord.ui.Button):
    def __init__(self, amount: int, receiver: discord.Member):
        super().__init__(style=discord.ButtonStyle.primary, label="Repeat", emoji="💸")
        self.receiver = receiver
        self.amount = amount

    @classmethod
    async def execute(
        cls,
        interaction: LnbitsInteraction,
        member: discord.Member,
        amount: int,
        memo: Optional[str] = None,
    ):
        if interaction.user == member:
            await interaction.response.send_message(
                ephemeral=True, content="You cant pay yourself"
            )
        else:
            try:
                await interaction.client.api.send_payment(
                    interaction.user, member, amount, memo
                )
            except HTTPStatusError as e:
                await interaction.response.send_message(content=e.response.content)
                return

            embed = discord.Embed(
                title="Tip",
                color=discord.Color.yellow(),
                description=f"{interaction.user.mention} just sent **{get_amount_str(amount)}** to {member.mention}",
            )
            if memo:
                embed.add_field(name="Memo", value=memo)

            await interaction.response.send_message(
                embed=embed, view=discord.ui.View().add_item(cls(amount, member))
            )

            await interaction.client.try_send_payment_notification(
                interaction, interaction.user, member, amount, memo
            )

    async def callback(self, interaction: LnbitsInteraction):
        await self.execute(interaction, self.receiver, self.amount)


class PayButton(discord.ui.Button):
    def __init__(
        self,
        payment_request: str,
        receiver: discord.Member,
        receiver_wallet: Wallet,
        amount: int,
        description: str,
    ):
        super().__init__(style=discord.ButtonStyle.primary, label="Pay Now", emoji="💸")
        self.payment_request = payment_request
        self.receiver = receiver
        self.receiver_wallet = receiver_wallet
        self.price = amount
        self.description = description

    async def callback(self, interaction: LnbitsInteraction):
        if interaction.user == self.receiver:
            await interaction.response.send_message(
                ephemeral=True, content="You cant pay yourself"
            )
            return

        wallet = await interaction.client.api.get_user_wallet(interaction.user)

        # await api_payments_pay_invoice(self.payment_request, wallet)
        await interaction.client.api.request(
            "POST",
            "/payments",
            wallet.adminkey,
            json={
                "out": True,
                "bolt11": self.payment_request,
            },
        )

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Pay Me!",
                description=f"Payed by {interaction.user.mention}",
                color=discord.Color.yellow(),
            )
            .add_field(name="Amount", value=get_amount_str(self.price))
            .add_field(name="Description", value=self.description),
            view=None,
            attachments=[],
        )

        await interaction.client.try_send_payment_notification(
            interaction, interaction.user, self.receiver, self.price, self.description
        )


class ClaimButton(discord.ui.Button):
    def __init__(self, lnurl: str):
        super().__init__(style=discord.ButtonStyle.primary, label="Claim", emoji="💸")
        self.lnurl = lnurl

    async def callback(self, interaction: LnbitsInteraction):
        wallet = await interaction.client.api.get_user_wallet(interaction.user)

        lnurl_parts = await interaction.client.api.request(
            method="get", path=f"/lnurlscan/{self.lnurl}", key=wallet.adminkey
        )

        await interaction.client.api.request(
            method="post",
            path="/payments",
            json={
                "lnurl_callback": lnurl_parts["callback"],
                "amount": (lnurl_parts["maxWithdrawable"]) / 1000,
                "memo": lnurl_parts["defaultDescription"],
                "out": False,
                "unit": "sat",
            },
        )

        await interaction.response.edit_message(
            view=discord.ui.View().add_item(
                discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    label=f"Claimed by {interaction.user.display_name}",
                    emoji="💸",
                    disabled=True,
                )
            ),
            attachments=[],
        )


class CoinFlipJoinButton(discord.ui.Button):
    view: CoinFlipView

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Join", emoji="💸")

    async def callback(self, interaction: LnbitsInteraction):
        balance = await interaction.client.api.get_user_balance(interaction.user)

        if not balance > self.view.stake(interaction.user) + self.view.price:
            await interaction.response.send_message(
                content="You do not have enough balance", ephemeral=True
            )
        else:
            self.view.entries.append(interaction.user)
            await interaction.response.edit_message(embed=self.view.get_current_embed())


class CoinFlipFinishButton(discord.ui.Button):
    view: CoinFlipView

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Flip", emoji="🪙")

    async def callback(self, interaction: LnbitsInteraction):
        if interaction.user != self.view.initiator:
            await interaction.response.send_message(
                "Only the creator can flip", ephemeral=True
            )
            return

        winner = self.view.winner = random.choice(self.view.entries)
        entries_unique = set(self.view.entries)

        if len(entries_unique) > 1:
            await interaction.response.edit_message(view=None)

            sent = 0
            for entry in entries_unique:
                if entry != winner:
                    try:
                        amount = self.view.stake(entry)
                        winner_wallet = await interaction.client.api.send_payment(
                            entry, winner, amount, self.view.description
                        )
                        sent += amount
                    except HTTPStatusError:
                        continue

            await interaction.followup.send(
                embed=discord.Embed(
                    title=f"And the winner is {winner.display_name}!",
                    color=discord.Color.yellow(),
                )
            )

            winner_wallet = await interaction.client.api.get_user_wallet(winner)
            winner_balance = await interaction.client.api.get_user_balance(winner)

            embed = discord.Embed(
                title="New Payment",
                color=discord.Color.yellow(),
                description=f"You won **{get_amount_str(sent)}** from a coinflip!\n\n"
                f"The flip happened [here]({(await interaction.original_response()).jump_url})",
            ).add_field(name="New Balance", value=get_amount_str(winner_balance))

            try:
                await winner.send(
                    embed=embed,
                    view=discord.ui.View().add_item(
                        WalletButton(
                            interaction.client.lnbits_url, wallet=winner_wallet
                        )
                    ),
                )
            except discord.HTTPException:
                pass

        else:
            await interaction.response.send_message(
                "You are the only participant", ephemeral=True
            )


class CoinFlipView(discord.ui.View):
    def __init__(
        self, initiator: discord.Member | discord.User, entry: int, description: str
    ):
        super().__init__()
        self.add_item(CoinFlipJoinButton())
        self.add_item(CoinFlipFinishButton())
        self.price = entry
        self.initiator = initiator
        self.entries = [initiator]
        self.description = description
        self.winner: Optional[discord.Member] = None

    def stake(self, member: discord.Member):
        return self.entries.count(member) * self.price

    def get_current_embed(self):
        embed = discord.Embed(
            title="Coinflip :coin:",
            color=discord.Color.yellow(),
            description=self.description,
        ).add_field(name="Entry Price", value=get_amount_str(self.price))

        entries_str = ""
        for entry in set(self.entries):
            count = self.entries.count(entry)
            entries_str += entry.display_name
            if count > 1:
                entries_str += f" x {count}"
            entries_str += "\n"
        embed.add_field(name="Entries", value=entries_str)
        return embed
