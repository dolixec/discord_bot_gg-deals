# GG.deals Discord Price Alert Bot
A Python bot that allows you to track the games that you want to buy with the help of GG.deals API

## Features

- **Watchlist management**: add/remove games by Steam App ID
- **Automatic price monitoring**: checks prices on a configurable interval
- **Price drop alerts**: sends rich Discord embeds when retail or keyshop prices decrease
- **On-demand price checks**: look up any game's current prices instantly
- **Persistent storage**: watchlist survives bot restarts (JSON file)

## Prerequisites
- Python 3.10+
- Discord Bot Token - https://discord.com/developers/applications
- GG.deals API - https://gg.deals/api/

## Setup

1. Rename the `.env.example` file into `.env`
2. Configure the `.env` file
3. Run ```pip install -r requirements.txt```
4. Start the bot with ```python bot.py```

## Discord Commands
| Command | Description |
|---|---|
| `!watch <steam_app_id>` | Add a game to the watchlist |
| `!unwatch <steam_app_id>` | Remove a game from the watchlist |
| `!watchlist` | Show all watched games and their prices |
| `!price <steam_app_id>` | Check current price (without watching) |
| `!dealhelp` | Show all available commands |

## How It Works

1. You add games to the watchlist with `!watch`
2. The bot records the current price as a baseline
3. Every `CHECK_INTERVAL` minutes, it fetches fresh prices from GG.deals
4. If any price is lower than the last known price, it posts an alert embed to your channel
5. Prices are updated after each check so the next alert only fires on a *further* drop

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | — | Your Discord bot token |
| `GG_DEALS_API_KEY` | Yes | — | Your GG.deals API key |
| `DISCORD_CHANNEL_ID` | Yes | — | Channel for price drop alerts |
| `CHECK_INTERVAL` | No | `60` | Price check interval in minutes |
| `GG_DEALS_REGION` | No | `us` | Region code (us, eu, gb, de, fr, pl, etc.) |
| `DATA_FILE` | No | `data/watchlist.json` | Path to watchlist storage 
