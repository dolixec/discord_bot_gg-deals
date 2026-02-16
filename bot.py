"""
GG.deals Discord Price Alert Bot

A Discord bot that monitors game prices via the GG.deals API
and sends alerts when a game's price drops.

Requirements:
    pip install discord.py aiohttp

Setup:
    1. Get a GG.deals API key from https://gg.deals/api/
    2. Create a Discord bot and get its token
    3. Set environment variables (see .env.example)
    4. Run: python bot.py
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GG_DEALS_API_KEY = os.environ["GG_DEALS_API_KEY"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

# How often to check prices (in minutes)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

# Region code for pricing (us, eu, gb, de, fr, pl, etc.)
REGION = os.environ.get("GG_DEALS_REGION", "us")

# File to persist the watchlist and last-known prices
DATA_FILE = Path(os.environ.get("DATA_FILE", "data/watchlist.json"))

GG_DEALS_PRICES_URL = "https://api.gg.deals/v1/prices/by-steam-app-id/"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("gg-deals-bot")

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_data() -> dict:
    '''Load watchlist from disk. Structure:
    {
        "games": {
            "<steam_app_id>": {
                "name": "Half-Life 2",
                "last_retail": "9.99",
                "last_keyshops": "4.50",
                "added_by": "username"
            }
        }
    }
    '''
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"games": {}}


def save_data(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))

# ---------------------------------------------------------------------------
# GG.deals API
# ---------------------------------------------------------------------------

async def fetch_prices(session: aiohttp.ClientSession, app_ids: list[str]) -> dict:
    # Fetch current prices for a list of Steam App IDs.
    if not app_ids:
        return {}

    # API allows up to 100 IDs per request
    params = {
        "key": GG_DEALS_API_KEY,
        "ids": ",".join(app_ids),
        "region": REGION,
    }

    async with session.get(GG_DEALS_PRICES_URL, params=params) as resp:
        if resp.status == 429:
            log.warning("Rate limited by GG.deals API. Will retry next cycle.")
            return {}
        resp.raise_for_status()
        body = await resp.json()

    if not body.get("success"):
        log.error("GG.deals API error: %s", body)
        return {}

    return body.get("data", {})

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@bot.command(name="watch")
async def watch_game(ctx, steam_app_id: str, *, game_name: str = ""):
    '''Add a game to the watchlist.

    Usage: !watch <steam_app_id> [game name]
    Example: !watch 1245620 Elden Ring
    '''
    data = load_data()

    if steam_app_id in data["games"]:
        await ctx.send(f"🎮 **{data['games'][steam_app_id]['name']}** is already on the watchlist.")
        return

    # Fetch the current price to initialise the baseline
    async with aiohttp.ClientSession() as session:
        prices = await fetch_prices(session, [steam_app_id])

    game_data = prices.get(steam_app_id)
    if game_data is None:
        await ctx.send(f"❌ Steam App ID **{steam_app_id}** was not found on GG.deals.")
        return

    title = game_data.get("title", game_name or steam_app_id)
    price_info = game_data.get("prices", {})

    entry = {
        "name": title,
        "last_retail": price_info.get("currentRetail"),
        "last_keyshops": price_info.get("currentKeyshops"),
        "historical_retail": price_info.get("historicalRetail"),
        "historical_keyshops": price_info.get("historicalKeyshops"),
        "currency": price_info.get("currency", "USD"),
        "url": game_data.get("url", f"https://gg.deals/steam/app/{steam_app_id}/"),
        "added_by": str(ctx.author),
    }
    data["games"][steam_app_id] = entry
    save_data(data)

    embed = discord.Embed(
        title=f"✅ Now watching: {title}",
        url=entry["url"],
        color=0x00CC66,
    )
    embed.add_field(name="Retail price", value=f"{entry['last_retail']} {entry['currency']}", inline=True)
    embed.add_field(name="Keyshops price", value=f"{entry['last_keyshops']} {entry['currency']}", inline=True)
    embed.add_field(name="Historical low (retail)", value=f"{entry['historical_retail']} {entry['currency']}", inline=True)
    embed.set_footer(text="Powered by GG.deals • Data provided by gg.deals")

    await ctx.send(embed=embed)


@bot.command(name="unwatch")
async def unwatch_game(ctx, steam_app_id: str):
    """Remove a game from the watchlist.

    Usage: !unwatch <steam_app_id>
    """
    data = load_data()

    if steam_app_id not in data["games"]:
        await ctx.send(f"❌ Steam App ID **{steam_app_id}** is not on the watchlist.")
        return

    name = data["games"][steam_app_id]["name"]
    del data["games"][steam_app_id]
    save_data(data)

    await ctx.send(f"🗑️ **{name}** removed from the watchlist.")


@bot.command(name="watchlist")
async def show_watchlist(ctx):
    """Show all games currently being watched."""
    data = load_data()

    if not data["games"]:
        await ctx.send("📋 The watchlist is empty. Add games with `!watch <steam_app_id> [name]`.")
        return

    embed = discord.Embed(
        title="📋 Watchlist",
        color=0x3498DB,
        timestamp=datetime.now(timezone.utc),
    )

    for app_id, info in data["games"].items():
        currency = info.get("currency", "USD")
        retail = info.get("last_retail", "N/A")
        keyshops = info.get("last_keyshops", "N/A")
        embed.add_field(
            name=f"{info['name']} (ID: {app_id})",
            value=f"Retail: **{retail} {currency}** | Keyshops: **{keyshops} {currency}**\n[View on GG.deals]({info.get('url', '')})",
            inline=False,
        )

    embed.set_footer(text="Powered by GG.deals • Data provided by gg.deals")
    await ctx.send(embed=embed)


@bot.command(name="price")
async def check_price(ctx, steam_app_id: str):
    """Check the current price of a game (does not add to watchlist).

    Usage: !price <steam_app_id>
    """
    async with aiohttp.ClientSession() as session:
        prices = await fetch_prices(session, [steam_app_id])

    game_data = prices.get(steam_app_id)
    if game_data is None:
        await ctx.send(f"❌ Steam App ID **{steam_app_id}** was not found on GG.deals.")
        return

    title = game_data.get("title", steam_app_id)
    p = game_data.get("prices", {})
    currency = p.get("currency", "USD")
    url = game_data.get("url", f"https://gg.deals/steam/app/{steam_app_id}/")

    embed = discord.Embed(
        title=f"💰 {title}",
        url=url,
        color=0xF1C40F,
    )
    embed.add_field(name="Current retail", value=f"{p.get('currentRetail', 'N/A')} {currency}", inline=True)
    embed.add_field(name="Current keyshops", value=f"{p.get('currentKeyshops', 'N/A')} {currency}", inline=True)
    embed.add_field(name="Historical low (retail)", value=f"{p.get('historicalRetail', 'N/A')} {currency}", inline=False)
    embed.add_field(name="Historical low (keyshops)", value=f"{p.get('historicalKeyshops', 'N/A')} {currency}", inline=False)
    embed.set_footer(text="Powered by GG.deals • Data provided by gg.deals")

    await ctx.send(embed=embed)


@bot.command(name="dealhelp")
async def deal_help(ctx):
    """Show available commands."""
    embed = discord.Embed(
        title="🎮 GG.deals Price Bot — Commands",
        color=0x9B59B6,
    )
    embed.add_field(
        name="!watch <steam_app_id> [name]",
        value="Add a game to the watchlist. Find the Steam App ID in the game's Steam store URL.\nExample: `!watch 1245620 Elden Ring`",
        inline=False,
    )
    embed.add_field(name="!unwatch <steam_app_id>", value="Remove a game from the watchlist.", inline=False)
    embed.add_field(name="!watchlist", value="Show all watched games and their last known prices.", inline=False)
    embed.add_field(name="!price <steam_app_id>", value="Check the current price without adding to the watchlist.", inline=False)
    embed.add_field(name="!dealhelp", value="Show this help message.", inline=False)
    embed.set_footer(text="Powered by GG.deals • Data provided by gg.deals")

    await ctx.send(embed=embed)

# ---------------------------------------------------------------------------
# Background price checker
# ---------------------------------------------------------------------------

@tasks.loop(minutes=CHECK_INTERVAL)
async def price_checker():
    """Periodically check prices and send alerts when a price drops."""
    data = load_data()
    if not data["games"]:
        return

    app_ids = list(data["games"].keys())
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        log.error("Could not find channel %s", CHANNEL_ID)
        return

    log.info("Checking prices for %d game(s)…", len(app_ids))

    async with aiohttp.ClientSession() as session:
        # Process in batches of 100 (API limit)
        for i in range(0, len(app_ids), 100):
            batch = app_ids[i : i + 100]
            prices = await fetch_prices(session, batch)

            for app_id in batch:
                game_data = prices.get(app_id)
                if game_data is None:
                    continue

                p = game_data.get("prices", {})
                stored = data["games"][app_id]
                currency = p.get("currency", stored.get("currency", "USD"))

                new_retail = p.get("currentRetail")
                new_keyshops = p.get("currentKeyshops")
                old_retail = stored.get("last_retail")
                old_keyshops = stored.get("last_keyshops")

                alerts = []

                # Compare retail prices
                if new_retail and old_retail:
                    try:
                        if float(new_retail) < float(old_retail):
                            alerts.append(
                                f"🏷️ **Retail**: ~~{old_retail}~~ → **{new_retail} {currency}**"
                            )
                    except ValueError:
                        pass

                # Compare keyshop prices
                if new_keyshops and old_keyshops:
                    try:
                        if float(new_keyshops) < float(old_keyshops):
                            alerts.append(
                                f"🔑 **Keyshops**: ~~{old_keyshops}~~ → **{new_keyshops} {currency}**"
                            )
                    except ValueError:
                        pass

                if alerts:
                    name = stored["name"]
                    url = stored.get("url", game_data.get("url", ""))

                    embed = discord.Embed(
                        title=f"🔔 Price Drop: {name}",
                        url=url,
                        description="\n".join(alerts),
                        color=0xE74C3C,
                        timestamp=datetime.now(timezone.utc),
                    )

                    hist_retail = p.get("historicalRetail", stored.get("historical_retail"))
                    if hist_retail:
                        embed.add_field(
                            name="Historical low (retail)",
                            value=f"{hist_retail} {currency}",
                            inline=True,
                        )

                    embed.set_footer(text="Powered by GG.deals • Data provided by gg.deals")

                    await channel.send(embed=embed)
                    log.info("Price drop alert sent for %s (%s)", name, app_id)

                # Update stored prices (always, so we detect the *next* drop)
                stored["last_retail"] = new_retail
                stored["last_keyshops"] = new_keyshops
                stored["currency"] = currency
                if p.get("historicalRetail"):
                    stored["historical_retail"] = p["historicalRetail"]
                if p.get("historicalKeyshops"):
                    stored["historical_keyshops"] = p["historicalKeyshops"]

            # Small delay between batches to respect rate limits
            if i + 100 < len(app_ids):
                await asyncio.sleep(2)

    save_data(data)


@price_checker.before_loop
async def before_price_checker():
    await bot.wait_until_ready()

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    log.info("Bot is online as %s", bot.user)
    log.info("Monitoring channel: %s", CHANNEL_ID)
    log.info("Check interval: %d minutes", CHECK_INTERVAL)
    price_checker.start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
