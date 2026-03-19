import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} on Duty to list commands")


@bot.command()
async def help(ctx):
    """Displays all available bot commands."""
    embed = discord.Embed(
        title="Bot Commands",
        description="Here is a list of all available commands you can use:",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="`!translate <text>`", value="Translates the specified text into English.", inline=False)
    embed.add_field(name="`!clear <number>`", value="Deletes the specified number of messages (requires 'Manage Messages' permission).", inline=False)
    embed.add_field(name="`!help`", value="Shows this list of commands.", inline=False)
    
    embed.set_footer(text="Requested by " + ctx.author.display_name)
    
    await ctx.send(embed=embed)


if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_BOT_TOKEN'))
