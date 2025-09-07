import os
import discord
from discord.ext import commands
from googletrans import Translator
"""
This code includes a Discord bot that automatically translates messages to English using the googletrans library and 
also provides a command to translate specific text.
Need for this bot:
google trans library is recommended python version 3.8 to 3.11.
Install the required libraries using pip:
pip install discord.py googletrans==4.0.0-rc1
pip install discord.py
Make sure your discord bot have permission of MESSAGE CONTENT INTENT enabled in the Discord Developer Portal.
"""

TOKEN = "DISCORD_BOT_TOKEN" # Replace with your actual bot token
intents = discord.Intents.default()
intents.message_content = True  # Needed to read messages
bot = commands.Bot(command_prefix="!", intents=intents)

translator = Translator()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Auto-translate all messages to English
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # ignore bot’s own messages
    
    try:
        # Detect and translate
        translation = translator.translate(message.content, dest="en")
        if translation.src != "en":  # Only translate if not already English
            await message.channel.send(
                f"🌍 **{message.author.display_name} said (translated from {translation.src}):** {translation.text}"
            )
    except Exception as e:
        print("Translation error:", e)

    await bot.process_commands(message)  # process other commands

# Command: translate a specific message
#Use the command like this: !translate <text>
@bot.command()
async def translate(ctx, *, text):
    translation = translator.translate(text, dest="en")
    await ctx.send(f"🌍 Translated: {translation.text}")

bot.run(TOKEN)
