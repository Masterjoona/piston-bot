import discord
from discord import app_commands, Interaction, Attachment
from discord.ext import commands


class CodeModal(discord.ui.Modal, title="Run Code"):
    def __init__(self, get_run_output, log_error):
        super().__init__()
        self.get_run_output = get_run_output
        self.log_error = log_error

    lang = discord.ui.TextInput(
        label="Language",
        placeholder="the language of the code",
        max_length=50,
    )

    code = discord.ui.TextInput(
        label="Code",
        style=discord.TextStyle.long,
        placeholder="the codes",
    )

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
        run_output = await self.get_run_output(
            guild=interaction.guild,
            author=interaction.user,
            content=self.code.value,
            input_lang=self.lang.value,
            output_syntax=None,
            args=None,
            stdin=None,
            mention_author=False,
        )
        await interaction.response.send_message(run_output)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        await interaction.response.send_message(
            "Oops! Something went wrong.", ephemeral=True
        )

        self.log_error(error, error_source="CodeModal")


class UserCommands(commands.Cog, name="UserCommands"):
    def __init__(self, client):
        self.client = client
        self.ctx_menu = app_commands.ContextMenu(
            name="Run Code",
            callback=self.run_code_ctx_menu,
        )
        self.client.tree.add_command(self.ctx_menu)

    @app_commands.command(name="run", description="Open a modal to run code")
    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run(self, interaction: Interaction):
        await interaction.response.send_modal(
            CodeModal(self.client.runner.get_run_output, self.client.log_error)
        )

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
        run_output = await self.client.runner.get_output_with_file(
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

        await interaction.response.send_message(run_output)

    @app_commands.user_install()
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def run_code_ctx_menu(
        self, interaction: Interaction, message: discord.Message
    ):
        run_output = await self.client.runner.get_output_with_codeblock(
            guild=interaction.guild,
            author=interaction.user,
            content=message.content,
            mention_author=False,
            needs_strict_re=False,
        )

        await interaction.response.send_message(run_output)


async def setup(client):
    await client.add_cog(UserCommands(client))
