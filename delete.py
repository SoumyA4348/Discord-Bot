"""
SIMPLE MESSAGE DELETION COMMAND

This bot is designed to help manage Discord Server channels.
I felt its use while testing the other bot commands, it was annoying to have to manually delete the command messages after testing, and to keep channels clean.

Features:
- Connects to Discord using Intents to read message content
-!clear <number of messages>: A command to bulk delete messages from a channel.
- Only users with "Manage Messages" permission can use the command.
- Error handling for missing permissions or missing numbers.

Setup:
1. 'Message Content Intent' enabled in Discord Developer Portal.
2. Invite the bot, give Admin or Manage Messages permissions.
3. Replace 'BOT_TOKEN'.

"""
# main library to interact with Discord's API
import os
import discord
# 'commands' extension, allows to create commands like !clear
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Creates a default set of permissions for the bot
intents = discord.Intents.default()
#Enables the Message Content intent so bot can read the text of messages from users
intents.message_content = True


# prefix '!' and intents for bot
bot = commands.Bot(command_prefix="!", intents=intents)

# A decorator that registers the function below as an event listener
@bot.event
# Defines an asynchronous function that triggers specifically when the bot has successfully connected to Discord
async def on_ready():
    # Login confirmation message
    print(f'✅  {bot.user.name} on Duty')

# A decorator that registers the function below as an accessible command via the command prefix
@bot.command()
#A check decorator
@commands.has_permissions(manage_messages=True) # Only allow users who can manage messages

async def clear(ctx, amount: int):
    # If the user provides 0 or a negative number, send an error and stop
    if amount <= 0:
        await ctx.send("Please specify a positive number of messages to delete. Example: `!clear 5`", delete_after=10)
        return

    # 'purge' returns a list of the messages it deleted
    # We delete (amount + 1) messages (limit=amount + 1) to remove the user's command + the target messages.
    deleted = await ctx.channel.purge(limit=amount + 1)
    
    # Calculate how many messages were ACTUALLY deleted, excluding the user's command message
    actual_deleted = len(deleted) - 1
    if actual_deleted < 0:
        actual_deleted = 0
    
    # Send a confirmation that auto-deletes after 10 seconds
    if actual_deleted == 1:
        word = "message"
    else:
        word = "messages"
    await ctx.send(f"🧹 Deleted {actual_deleted} {word}.", delete_after=10)

# Error handling for the clear command
@clear.error
async def clear_error(ctx, error):
    # Check if the user ismissing permissions
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ I dont listen to noobs")
    # Check if the User typed "!clear" without a number
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please specify the number of messages to clear. Example: `!clear 5`")
    # Check if the user passed a non-number (e.g. "!clear abc")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Please provide a valid number. Example: `!clear 5`")

# SECURE RUN: Uses the token from .env
bot.run(os.getenv('DISCORD_TOKEN'))