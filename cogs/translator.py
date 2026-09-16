import discord
from discord.ext import commands
from googletrans import Translator

LANGUAGE_ALIASES: dict[str, str] = {
    "arabic":     "ar",
    "chinese":    "zh-cn",
    "danish":     "da",
    "dutch":      "nl",
    "english":    "en",
    "finnish":    "fi",
    "french":     "fr",
    "german":     "de",
    "greek":      "el",
    "hindi":      "hi",
    "italian":    "it",
    "japanese":   "ja",
    "korean":     "ko",
    "norwegian":  "no",
    "polish":     "pl",
    "portuguese": "pt",
    "russian":    "ru",
    "spanish":    "es",
    "swedish":    "sv",
    "turkish":    "tr",
}


def _resolve_lang(lang: str) -> str:
    return LANGUAGE_ALIASES.get(lang.strip().lower(), lang.strip().lower())


class TranslatorCog(commands.Cog, name="Translator"):
    """Auto-translate non-English messages and provide manual translation commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._translator = Translator()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content.strip():
            return
        prefix = self.bot.command_prefix
        if isinstance(prefix, str) and message.content.startswith(prefix):
            return
        try:
            detected = self._translator.detect(message.content)
            if detected and detected.lang and detected.lang != "en":
                result = self._translator.translate(message.content, dest="en")
                if result and result.text:
                    await message.reply(
                        f"🌍 **Auto-translated from `{detected.lang}`:** {result.text}",
                        mention_author=False,
                    )
        except Exception:
            pass

    @commands.command()
    async def translate(self, ctx: commands.Context, *args: str) -> None:
        """Translate text to English or to a specific language.

        Usage:
          `!translate <text>`
          `!translate to <language> <text>`
        """
        if not args:
            return await ctx.send(
                "Usage: `!translate <text>` or `!translate to <lang> <text>`"
            )

        dest = "en"
        text = " ".join(args)

        if args[0].lower() == "to":
            if len(args) < 3:
                return await ctx.send(
                    "Usage: `!translate to <lang> <text>`  e.g. `!translate to french Hello`"
                )
            dest = _resolve_lang(args[1])
            text = " ".join(args[2:])

        if not text.strip():
            return await ctx.send("Please provide some text to translate.")

        try:
            result = self._translator.translate(text, dest=dest)
            if not result or not result.text:
                return await ctx.send("Translation returned an empty result. Please try again.")
            src = result.src or "unknown"
            await ctx.send(f"🌍 **Translated `{src}` → `{dest}`:** {result.text}")
        except Exception as exc:
            await ctx.send(f"❌ Translation failed: {exc}")

    @commands.command(name="languages")
    async def languages_command(self, ctx: commands.Context) -> None:
        """List all supported language names you can use with `!translate to`."""
        codes = "\n".join(
            f"`{name}` → `{code}`" for name, code in sorted(LANGUAGE_ALIASES.items())
        )
        embed = discord.Embed(
            title="🌍 Supported Languages",
            description=f"Pass any name below to `!translate to <language>`:\n\n{codes}",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TranslatorCog(bot))
