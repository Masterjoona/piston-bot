import discord
from discord import app_commands, Interaction, Attachment
from discord.ext import commands
from .utils.errors import PistonError
from asyncio import TimeoutError as AsyncTimeoutError


class SourceCodeModal(discord.ui.Modal, title="Run Code"):
    def __init__(self, get_run_output, log_error, language):
        super().__init__()
        self.get_run_output = get_run_output
        self.log_error = log_error
        self.language = language

        self.lang = discord.ui.TextInput(
            label="Language",
            placeholder="The language",
            max_length=50,
            default=self.language or "",
        )

        self.code = discord.ui.TextInput(
            label="Code",
            style=discord.TextStyle.long,
            placeholder="The source code",
            max_length=1900,
        )

        self.add_item(self.lang)
        self.add_item(self.code)

    # It gets pretty crowded with all these fields
    # So im not sure which to keep if any at all

    # output_syntax = discord.ui.TextInput(
    #    label="Output Syntax",
    #    placeholder="the syntax of the output",
    #    required=False,
    # )

    # args = discord.ui.TextInput(
    #    label="Arguments",
    #    placeholder="the arguments - comma separated",
    #    required=False,
    # )

    # stdin = discord.ui.TextInput(
    #    label="Standard Input",
    #    placeholder="the standard input",
    #    required=False,
    # )

    async def on_submit(self, interaction: discord.Interaction):
        [introduction, source, run_output] = await self.get_run_output(
            guild=interaction.guild,
            author=interaction.user,
            content=self.code.value,
            input_lang=self.lang.value,
            output_syntax=None,
            args=None,
            stdin=None,
            mention_author=False,
        )
        await interaction.response.send_message("Here is your input:"+source)
        await interaction.followup.send(introduction+run_output)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            "Oops! Something went wrong.", ephemeral=True
        )

        await self.log_error(error, error_source="CodeModal")

class NoLang(discord.ui.Modal, title="Give lang"):
    def __init__(self, get_output_with_codeblock, log_error, message):
        super().__init__()
        self.get_output_with_codeblock = get_output_with_codeblock
        self.log_error = log_error
        self.message = message

    lang = discord.ui.TextInput(
        label="Language",
        placeholder="The language",
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        [introduction, _, run_output]  = await self.get_output_with_codeblock(
            guild=interaction.guild,
            author=interaction.user,
            content=self.message.content,
            mention_author=False,
            needs_strict_re=False,
            input_lang=self.lang.value,
            jump_url=self.message.jump_url,
        )
        await interaction.response.send_message(introduction+run_output)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            "Oops! Something went wrong.", ephemeral=True
        )

        await self.log_error(error, error_source="CodeModal")


class UserCommands(commands.Cog, name="UserCommands"):
    def __init__(self, client):
        self.client = client
        self.ctx_menu = app_commands.ContextMenu(
            name="Run Code",
            callback=self.run_code_ctx_menu,
        )
        self.client.tree.add_command(self.ctx_menu)

    async def cog_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        if isinstance(error.original, PistonError):
            error_message = str(error.original)
            if error_message:
                error_message = f'`{error_message}` '
            await interaction.response.send_message(f'API Error {error_message}- Please try again later')
            await self.client.log_error(error, Interaction)
            return

        if isinstance(error.original, AsyncTimeoutError):
            await interaction.response.send_message(f'API Timeout - Please try again later')
            await self.client.log_error(error, Interaction)
            return
        await self.client.log_error(error, Interaction)
        await interaction.response.send_message(f"An error occurred: {error}")



    @app_commands.command(name="run_code", description="Open a modal to input code")
    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run_code(self, interaction: Interaction, language: str = None):
        if language not in self.client.runner.get_languages():
            await interaction.response.send_modal(SourceCodeModal(self.client.runner.get_run_output, self.client.log_error, ""))
            return
        await interaction.response.send_modal(SourceCodeModal(self.client.runner.get_run_output, self.client.log_error, language))

    @run_code.autocomplete('language')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        langs = self.client.runner.get_languages()
        if current:
            langs = [lang for lang in langs if lang.startswith(current)]
        return [app_commands.Choice(name=lang, value=lang) for lang in langs[:25]]

    @app_commands.command(name="run_file", description="Run a file")
    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run_file(
        self,
        interaction: Interaction,
        file: Attachment,
        language: str = "",
        output_syntax: str = "None",
        args: str = "",
        stdin: str = "",
    ):
        [introduction, source, run_output]  = await self.client.runner.get_output_with_file(
            guild=interaction.guild,
            author=interaction.user,
            content="",
            file=file,
            input_language=language,
            output_syntax=output_syntax,
            args=args,
            stdin=stdin,
            mention_author=False,
        )

        await interaction.response.send_message(introduction+source)
        await interaction.followup.send(run_output)

    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run_code_ctx_menu(
        self, interaction: Interaction, message: discord.Message
    ):
        if len(message.attachments) > 0:
            [introduction, _, run_output]  = await self.client.runner.get_output_with_file(
                guild=interaction.guild,
                author=interaction.user,
                content=message.content,
                file=message.attachments[0],
                input_language="",
                output_syntax="",
                args="",
                stdin="",
                mention_author=False,
                jump_url=message.jump_url,
            )

            await interaction.response.send_message(introduction+run_output)
            return
        [introduction, _, run_output] = await self.client.runner.get_output_with_codeblock(
            guild=interaction.guild,
            author=interaction.user,
            content=message.content,
            mention_author=False,
            needs_strict_re=False,
            jump_url=message.jump_url,
        )

        if "Unsupported language" in run_output:
            await interaction.response.send_modal(
                NoLang(self.client.runner.get_output_with_codeblock, self.client.log_error, message)
            )
            return

        await interaction.response.send_message(introduction+run_output)


async def setup(client):
    await client.add_cog(UserCommands(client))
