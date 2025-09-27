import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

# === Flask Keep-Alive Server ===
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# Start keep-alive server
keep_alive()
# ===============================

load_dotenv()
token = os.getenv('DISCORD_TOKEN')



handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")

@bot.command()
async def yo(ctx):
    await ctx.send(f"yo {ctx.author.mention}!")

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import re

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Store timers per user:
# {user_id: [{"id": int, "task": asyncio.Task, "end_time": datetime, ...}, ...]}
active_timers = {}

# Track last timer ID per user to assign incremental IDs
timer_id_counters = {}


@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s). Bot is ready as {bot.user}.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


def parse_time_string(time_str):
    time_str = time_str.replace(" ", "").lower()
    pattern = r'(?:(\d+)h)?(?:(\d+)m)?'
    match = re.fullmatch(pattern, time_str)

    if not match:
        raise ValueError("Invalid time format. Use like '1h30m', '45m', or '2h'.")

    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0

    total_seconds = hours * 3600 + minutes * 60
    return total_seconds, f"{hours}h {minutes}m"


async def run_hop(interaction, user_id, timer_id, hop_num, duration, region, link_md):
    try:
        end_time = datetime.utcnow() + timedelta(seconds=duration)
        # Update timer end_time so /timers shows updated remaining
        for t in active_timers[user_id]:
            if t["id"] == timer_id and t["hop"] == hop_num:
                t["end_time"] = end_time

        if duration > 300:
            await asyncio.sleep(duration - 300)
            # Calculate remaining spawns (hops)
            remaining_spawns = sum(1 for t in active_timers[user_id] if t["id"] == timer_id and t["hop"] > hop_num)

            await interaction.followup.send(
                f"⚠️ **Timer #{timer_id}** - Bosses in 5 minutes, Region: *{region}*, SPAWNS LEFT: {remaining_spawns}\n🔗 {link_md}"
            )


            await asyncio.sleep(300)
        else:
            await asyncio.sleep(duration)




        # After last hop, remove timer completely
        if hop_num == max(t["hop"] for t in active_timers[user_id] if t["id"] == timer_id):
            active_timers[user_id] = [t for t in active_timers[user_id] if t["id"] != timer_id]

    except asyncio.CancelledError:
        # Timer cancelled
        await interaction.followup.send(f"❌ **Timer #{timer_id}** was cancelled.")
        # Remove timer immediately
        active_timers[user_id] = [t for t in active_timers[user_id] if t["id"] != timer_id]


@bot.tree.command(name="timer", description="Start a repeating timer with hops.")
@app_commands.describe(
    time="Initial time (e.g. 1h30m)",
    hops="Number of hops (default 1)",
    region="Region (default 'Unknown')",
    link="Invite link (optional)"
)
async def timer(
    interaction: discord.Interaction,
    time: str,
    hops: int = 1,
    region: str = "Unknown",
    link: str = ""
):
    try:
        total_seconds, duration_str = parse_time_string(time)
        if total_seconds <= 0:
            await interaction.response.send_message("❌ Time must be greater than 0.", ephemeral=True)
            return

        if hops < 1:
            hops = 1  # fallback to 1 hop minimum

        user_id = interaction.user.id
        link_md = f"[Join Server]({link})" if link else ""

        # Assign unique timer ID
        timer_id_counters[user_id] = timer_id_counters.get(user_id, 0) + 1
        timer_id = timer_id_counters[user_id]

        # REPLY exactly as requested (lowercase, two lines)
        await interaction.response.send_message(
            f"timer #{timer_id} has been activated\nregion: {region}"
        )

        # Create timer tasks for each hop
        if user_id not in active_timers:
            active_timers[user_id] = []

        for hop in range(hops):
            hop_num = hop + 1
            duration = total_seconds if hop == 0 else 2 * 3600  # first hop input, others 2h
            end_time = datetime.utcnow() + timedelta(seconds=duration)

            # Create async task to run the hop timer
            task = asyncio.create_task(run_hop(interaction, user_id, timer_id, hop_num, duration, region, link_md))

            active_timers[user_id].append({
                "id": timer_id,
                "hop": hop_num,
                "task": task,
                "end_time": end_time,
                "region": region,
                "link_md": link_md,
                "duration": duration
            })

    except ValueError as ve:
        await interaction.response.send_message(f"❌ {str(ve)}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Unexpected error: {str(e)}", ephemeral=True)


@bot.tree.command(name="timers", description="List your active timers.")
async def timers(interaction: discord.Interaction):
    user_id = interaction.user.id

    if user_id not in active_timers or not active_timers[user_id]:
        await interaction.response.send_message("📭 You have no active timers.", ephemeral=True)
        return

    now = datetime.utcnow()
    msg = "⏱ **Your Active Timers:**\n\n"

    # Group timers by timer_id to show as one grouped timer with hops
    timers_grouped = {}
    for t in active_timers[user_id]:
        timers_grouped.setdefault(t["id"], []).append(t)

    for tid, timer_hops in timers_grouped.items():
        # Sort hops ascending
        timer_hops.sort(key=lambda x: x["hop"])
        msg += f"**Timer #{tid}** with {len(timer_hops)} hop(s):\n"
        for t in timer_hops:
            remaining = int((t["end_time"] - now).total_seconds())
            if remaining <= 0:
                continue
            mins, secs = divmod(remaining, 60)
            hrs, mins = divmod(mins, 60)
            time_left = f"{hrs}h {mins}m"
            msg += (
                f"  • Hop {t['hop']} in `{t['region']}` — **{time_left} left**\n"
                f"    🔗 {t['link_md']}\n"
            )
        msg += "\n"

    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="remove", description="Remove/cancel a timer by its number.")
@app_commands.describe(timer_number="Number of the timer to cancel")
async def remove(interaction: discord.Interaction, timer_number: int):
    user_id = interaction.user.id

    if user_id not in active_timers or not active_timers[user_id]:
        await interaction.response.send_message("❌ You have no active timers.", ephemeral=True)
        return

    timers_grouped = {}
    for t in active_timers[user_id]:
        timers_grouped.setdefault(t["id"], []).append(t)

    if timer_number not in timers_grouped:
        await interaction.response.send_message(f"❌ No timer with number {timer_number} found.", ephemeral=True)
        return

    # Cancel all tasks for this timer
    for t in timers_grouped[timer_number]:
        t["task"].cancel()

    # They will be removed automatically by the cancellation handler

    await interaction.response.send_message(f"🛑 Timer #{timer_number} cancelled successfully.", ephemeral=True)


import discord
from discord.ext import commands
from discord import app_commands
import asyncio

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user}! Commands synced.')

@bot.tree.command(name="reminder", description="Set a keyword-based reminder.")
@app_commands.describe(message="One of: Super, Boss, Raids")
async def reminder(interaction: discord.Interaction, message: str):
    keyword = message.lower()

    if keyword == "super":
        wait_time = 60 * 60  # 60 minutes
    elif keyword == "boss":
        wait_time = 60 * 60  # 60 minutes
    elif keyword == "raids":
        wait_time = 120 * 60  # 120 minutes
    else:
        await interaction.response.send_message(
            "❌ Invalid reminder type. Use: Super, Boss, or Raids.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"{interaction.user.mention} your reminder for **{message.capitalize()}** has been activated"
    )

    await asyncio.sleep(wait_time)

    await interaction.followup.send(
        f"{interaction.user.mention}, it's your **{message.capitalize()}** reminder!"
    )






bot.run(token, log_handler=handler, log_level=logging.DEBUG)
