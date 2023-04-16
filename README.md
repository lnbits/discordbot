# Discord Bot

## Provide LNbits wallets for all your Discord users

_This extension depends on the LNbits [User Manager](https://github.com/lnbits/usermanager/blob/main/README.md)_

This extension can be used to run a discord bot which provides lightning functionalities to discord users.
It can be run through the extension or be self-hosted.

The intended usage of this extension is to connect it to a specifically designed [Discord Bot](https://github.com/chrislennon/lnbits-discord-bot) leveraging LNbits as a community based lightning node.

## Setup

### Running on lnbits

Install this extension onto your lnbits node and create a bot configuration.
Make sure the `standalone` option is not checked.

If your token is valid you should see your bot go online.

### Self hosted

Install this extension onto your lnbits node and create a bot configuration.
Make sure the `standalone` option is checked.

Once you have done that, clone this repo.

```shell
git clone https://github.com/jackstar12/discordbot.git
```

You can get your environment variables by expanding the `Setup` section on the extension page of your lnbits instance.
Paste them into an `.env` file or set them manually.

Now you should be able to install and run.
If you don't have poetry installed follow the instructions [here](https://python-poetry.org/docs/#installation)

```shell
poetry install
poetry run standalone
```

After waiting for the bot to start you can refresh the extension page. The profile picture and name of
your bot should show up accordingly.

## Usage

This bot will allow users to interact with it in the following ways [full command list](https://github.com/chrislennon/lnbits-discord-bot#commands):

`/create` Will create a wallet for the Discord user

- (currently limiting 1 Discord user == 1 LNbits user == 1 user wallet)

![create](https://imgur.com/CWdDusE.png)

`/balance` Will show the balance of the users wallet.

![balance](https://imgur.com/tKeReCp.png)

`/tip @user [amount]` Will sent money from one user to another

- If the recieving user does not have a wallet, one will be created for them
- The receiving user will receive a direct message from the bot with a link to their wallet

![tip](https://imgur.com/K3tnChK.png)

`/payme [amount] [description]` Will open an invoice that can be paid by any user

![payme](https://imgur.com/dFvAqL3.png)
