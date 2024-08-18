import discord
from discord import app_commands, Interaction, Attachment
from discord.ext import commands
from .utils.errors import PistonError
from asyncio import TimeoutError as AsyncTimeoutError
from io import BytesIO

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

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        output, errored = await self.get_run_output(
            guild=interaction.guild,
            author=interaction.user,
            content=self.code.value,
            input_lang=self.lang.value,
            output_syntax=None,
            args=None,
            stdin=None,
            mention_author=False,
        )
        if errored:
            await interaction.followup.send(output, ephemeral=True)
            return

        if len(self.code.value) > 1000:
            file = discord.File(filename=f"source_code.{self.lang.value}", fp=BytesIO(self.code.value.encode('utf-8')))
            await interaction.followup.send("Here is your input:", file=file)
            await interaction.followup.send(output)
            return
        formatted_src = f"```{self.lang.value}\n{self.code.value}\n```"
        await interaction.followup.send("Here is your input:" + formatted_src)
        await interaction.followup.send(output)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.followup.send(
            "Oops! Something went wrong.", ephemeral=True
        )

        await self.log_error(error, error_source="CodeModal")

class NoLang(discord.ui.Modal, title="Give language"):
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
        await interaction.response.defer()
        output, errored = await self.get_output_with_codeblock(
            guild=interaction.guild,
            author=interaction.user,
            content=self.message.content,
            mention_author=False,
            needs_strict_re=False,
            input_lang=self.lang.value,
            jump_url=self.message.jump_url,
        )
        if errored:
            await interaction.followup.send(output, ephemeral=True)
            return
        await interaction.followup.send(output)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.followup.send(
            "Oops! Something went wrong.", ephemeral=True
        )

        await self.log_error(error, error_source="NoLangModal")


class UserCommands(commands.Cog, name="UserCommands"):
    def __init__(self, client):
        self.client = client
        self.ctx_menu = app_commands.ContextMenu(
            name="Run Code",
            callback=self.run_code_ctx_menu,
        )
        #self.ctx_menu.error(self.run_code_ctx_menu_error)
        self.client.tree.add_command(self.ctx_menu)

    async def cog_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError):
        if isinstance(error.original, PistonError):
            error_message = str(error.original)
            if error_message:
                error_message = f'`{error_message}` '
            await interaction.followup.send(f'API Error {error_message}- Please try again later', ephemeral=True)
            await self.client.log_error(error, Interaction)
            return

        if isinstance(error.original, AsyncTimeoutError):
            await interaction.followup.send(f'API Timeout - Please try again later', ephemeral=True)
            await self.client.log_error(error, Interaction)
            return
        await self.client.log_error(error, Interaction)
        await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

    @app_commands.command(name="run_code", description="Open a modal to input code")
    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run_code(self, interaction: Interaction, language: str = None):
        if language not in self.client.runner.get_languages(inlude_aliases=True):
            await interaction.response.send_modal(
                SourceCodeModal(
                    self.client.runner.get_run_output,
                    self.client.log_error,
                    "",
                )
            )
            return
        await interaction.response.send_modal(
            SourceCodeModal(
                self.client.runner.get_run_output,
                self.client.log_error,
                language,
            )
        )

    @run_code.autocomplete('language')
    async def autocomplete_callback(self, _: discord.Interaction, current: str):
        langs = self.client.runner.get_languages(inlude_aliases=True)
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
        output, errored = await self.client.runner.get_output_with_file(
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
        if errored:
            if "Unsupported language" in output:
                await interaction.response.send_modal(
                    NoLang(self.client.runner.get_output_with_file, self.client.log_error, interaction.message)
                )
                return
            await interaction.followup.send(output, ephemeral=True)
            return
        file_contents = await file.read()
        if len(file_contents) > 1000:
            output_file = discord.File(filename=file.filename, fp=BytesIO(file_contents))
            await interaction.followup.send("Here is your input:", file=output_file)
            await interaction.followup.send(output)
            return

        formatted_src = f"```{language}\n{file_contents.decode()}\n```"
        await interaction.followup.send("Here is your input:" + formatted_src)
        await interaction.followup.send(output)

    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run_code_ctx_menu(self, interaction: Interaction, message: discord.Message):
        if len(message.attachments) > 0:
            output, errored = await self.client.runner.get_output_with_file(
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
            if errored:
                if "Unsupported language" in output:
                    await interaction.response.send_modal(
                        NoLang(self.client.runner.get_output_with_codeblock, self.client.log_error, message)
                    )
                    return
                await interaction.followup.send(output, ephemeral=True)
                return
            await interaction.followup.send(output)
            return
        output, errored = await self.client.runner.get_output_with_codeblock(
            guild=interaction.guild,
            author=interaction.user,
            content=message.content,
            mention_author=False,
            needs_strict_re=False,
            jump_url=message.jump_url,
        )
        if errored:
            if "Unsupported language" in output:
                await interaction.response.send_modal(
                    NoLang(self.client.runner.get_output_with_codeblock, self.client.log_error, message)
                )
                return
            await interaction.followup.send(output, ephemeral=True)
            return
        await interaction.followup.send(output)

    async def run_code_ctx_menu_error(self, interaction: discord.Interaction, error: Exception):
        await self.client.log_error(error, interaction)
        print(error)
        if isinstance(error, commands.BadArgument):
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.followup.send("Oops! Something went wrong.", ephemeral=True)


async def setup(client):
    await client.add_cog(UserCommands(client))
