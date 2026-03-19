import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from googletrans import Translator
"""
This code includes a Discord bot that automatically translates messages to English using the googletrans library and 
also provides a command to translate specific text.
Need for this bot:
google trans library is recommended python version 3.8 to 3.11.
Install the required libraries using pip:
pip install discord.py googletrans==4.0.0-rc1
Make sure your discord bot have permission of MESSAGE CONTENT INTENT enabled in the Discord Developer Portal.
"""

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN") # Securely loads your actual bot token from .env
intents = discord.Intents.default()
intents.message_content = True  # Needed to read messages
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

translator = Translator()

@bot.event
async def on_ready():
    print(f"✅ {bot.user} on Duty to translate messages")



# Command: translate a specific message
#Use the command like this: !translate <text>
@bot.command()
async def translate(ctx, *, text):
    translation = translator.translate(text, dest="en")
    await ctx.send(f"🌍 Translated from {translation.src}: {translation.text}")

bot.run(TOKEN)
