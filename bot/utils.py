import discord

from lnbits.core.crud import (
    get_wallet
)
from lnbits.core.models import Wallet as FullWallet
from .ui import WalletButton


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
