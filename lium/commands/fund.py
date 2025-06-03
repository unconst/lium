"""Fund account command for Lium CLI."""

import click
import time
import sys
from typing import Optional

from ..config import get_or_set_api_key
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="fund")
@click.option("--wallet", required=False, help="Bittensor funding wallet")
@click.option("--tao", help="Amount of tao to fund.")
def fund_command(wallet: str = None, tao: str = None):
    if wallet is None:
        wallet = Prompt.ask(
            styled(f"Enter your wallet anme", "key"),
            default="default",
            console=console
        ).strip().lower()
    if tao is None:
        tao = Prompt.ask(
            styled(f"Enter tao amount", "key"),
            console=console
        ).strip().lower()
    import bittensor as bt
    api_key = get_or_set_api_key()
    client = LiumAPIClient(api_key)
    funding_wallet = bt.wallet(wallet)
    coldkey_ss58 = funding_wallet.coldkeypub.ss58_address
    all_funding_wallets = client.get_funding_wallets()
    all_keys = [fwalls['wallet_hash'] for fwalls in all_funding_wallets]
    if coldkey_ss58 not in all_keys:
        console.print(styled(f"Linking: {coldkey_ss58} with your account ...", 'info'))
        client.add_wallet(funding_wallet)
    all_funding_wallets = client.get_funding_wallets()
    
    # Wait for update or fail.
    time.sleep(2)
    if coldkey_ss58 not in all_keys:
        console.print(styled(f"Error adding your wallet. Try again later", 'info'))
        sys.exit()
            
    user_info = client.get_users_me()
    old_balance = user_info['balance']
    amount_tao = bt.Balance.from_tao(float(tao))
    console.print(styled(f"Current balance: {user_info['balance']}", 'info'))
    confirm_funding = Prompt.ask(
        styled(f"Do you want to fund your account with {amount_tao}? (yes/no)", "key"),
        default="no",
        console=console
    ).strip().lower()
    if confirm_funding.startswith("y"):
        bt.subtensor().transfer(
            wallet=bt.wallet(wallet),
            dest='5FqACMtcegZxxopgu1g7TgyrnyD8skurr9QDPLPhxNQzsThe',
            amount=amount_tao,
        )
        while True:
            new_user_info = client.get_users_me()
            new_balance = new_user_info['balance']
            if new_balance > old_balance:
                break
            else:
                time.sleep(1)
        console.print(styled(f"Your new funding balance is: {new_balance}", 'info'))
    else:
        console.print(styled("Funding operation canceled.", "info")) 