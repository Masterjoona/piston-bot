"""PistonBot

"""
import json
import sys
import traceback
from datetime import datetime, timezone
from os import path, listdir
from discord.ext.commands import AutoShardedBot, Context
from discord import Activity, AllowedMentions, Intents, Interaction
from aiohttp import ClientSession, ClientTimeout
from discord.ext.commands.bot import when_mentioned_or
from cogs.utils.runner import Runner

class PistonBot(AutoShardedBot):
    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.session = None
        with open('../state/config.json') as conffile:
            self.config = json.load(conffile)
        self.last_errors = []
        self.recent_guilds_joined = []
        self.recent_guilds_left = []
        self.default_activity = Activity(name='emkc.org/run | ./run', type=0)
        self.error_activity = Activity(name='!emkc.org/run | ./run', type=0)
        self.maintenance_activity = Activity(name='undergoing maintenance', type=0)
        self.error_string = 'Sorry, something went wrong. We will look into it.'
        self.maintenance_mode = False

    async def start(self, *args, **kwargs):
        self.session = ClientSession(timeout=ClientTimeout(total=15))
        self.runner = Runner(self.config['emkc_key'], self.session)
        await super().start(*args, **kwargs)

    async def close(self):
        await self.session.close()
        await super().close()

    async def setup_hook(self):
        print('Loading Extensions:')
        STARTUP_EXTENSIONS = []
        for file in listdir(path.join(path.dirname(__file__), 'cogs/')):
            filename, ext = path.splitext(file)
            if '.py' in ext:
                STARTUP_EXTENSIONS.append(f'cogs.{filename}')

        for extension in reversed(STARTUP_EXTENSIONS):
            try:
                print('loading', extension)
                await self.load_extension(f'{extension}')
            except Exception as e:
                await self.log_error(e, 'Cog INIT')
                exc = f'{type(e).__name__}: {e}'
                print(f'Failed to load extension {extension}\n{exc}')

    def user_is_admin(self, user):
        return user.id in self.config['admins']

    async def log_error(self, error, error_source=None):
        is_context = isinstance(error_source, Context)
        has_attachment = bool(error_source.message.attachments) if is_context else False
        self.last_errors.append((
            error,
            datetime.now(tz=timezone.utc),
            error_source,
            error_source.message.content if is_context else None,
            error_source.message.attachments[0] if has_attachment else None,
        ))
        await self.change_presence(activity=self.error_activity)


intents = Intents.default()
intents.message_content = True

client = PistonBot(
    command_prefix=when_mentioned_or('./', '/'),
    description='Hello, I can run code!',
    max_messages=15000,
    allowed_mentions=AllowedMentions(everyone=False, users=True, roles=False),
    intents=intents
)
client.remove_command('help')


@client.event
async def on_ready():
    print('PistonBot started successfully')
    return True


@client.event
async def on_message(msg):
    prefixes = await client.get_prefix(msg)
    for prefix in prefixes:
        if msg.content.lower().startswith(f'{prefix}run'):
            msg.content = msg.content.replace(f'{prefix}run', f'/run', 1)
            break
    await client.process_commands(msg)


@client.event
async def on_error(event_method, *args, **kwargs):
    """|coro|

    The default error handler provided by the client.

    By default this prints to :data:`sys.stderr` however it could be
    overridden to have a different implementation.
    Check :func:`~discord.on_error` for more details.
    """
    print('Default Handler: Ignoring exception in {}'.format(event_method), file=sys.stderr)
    traceback.print_exc()
    # --------------- custom code below -------------------------------
    # Saving the error to be inspected later
    await client.log_error(sys.exc_info()[1], 'DEFAULT HANDLER:' + event_method)


client.run(client.config["bot_key"])
print('PistonBot has exited')
