import re
import json
from .errors import PistonInvalidContentType, PistonInvalidStatus, PistonNoOutput
from discord.ext import commands, tasks
from discord import Guild, User, Member, Attachment
from discord.utils import escape_mentions
from aiohttp import ClientSession, ContentTypeError
from .codeswap import add_boilerplate


class Runner:
    def __init__(self, emkc_key: str, session: ClientSession):
        self.languages = dict()  # Store the supported languages and aliases
        self.versions = dict()  # Store version for each language
        self.emkc_key = emkc_key
        self.base_re = (
            r'(?: +(?P<language>\S*?)\s*|\s*)'
            r'(?:-> *(?P<output_syntax>\S*)\s*|\s*)'
            r'(?:\n(?P<args>(?:[^\n\r\f\v]*\n)*?)\s*|\s*)'
            r'```(?:(?P<syntax>\S+)\n\s*|\s*)(?P<source>.*)```'
            r'(?:\n?(?P<stdin>(?:[^\n\r\f\v]\n?)+)+|)'
        )
        self.run_regex_code = re.compile(self.base_re, re.DOTALL)
        self.run_regex_code_strict = re.compile(
            r'/(?:edit_last_)?run' + self.base_re, re.DOTALL
        )

        self.run_regex_file = re.compile(
            r'/run(?: *(?P<language>\S*)\s*?|\s*?)?'
            r'(?: *-> *(?P<output>\S*)\s*?|\s*?)?'
            r'(?:\n(?P<args>(?:[^\n\r\f\v]+\n?)*)\s*|\s*)?'
            r'(?:\n*(?P<stdin>(?:[^\n\r\f\v]\n*)+)+|)?'
        )

        self.session = session

        self.update_available_languages.start()

    @tasks.loop(count=1)
    async def update_available_languages(self):
        async with self.session.get(
            'https://emkc.org/api/v2/piston/runtimes'
        ) as response:
            runtimes = await response.json()
        for runtime in runtimes:
            language = runtime['language']
            self.languages[language] = language
            self.versions[language] = runtime['version']
            for alias in runtime['aliases']:
                self.languages[alias] = language
                self.versions[alias] = runtime['version']

    def get_languages(self):
        return sorted(set(self.languages.values()))

    async def send_to_log(
        self,
        guild: Guild | None,
        author: User | Member,
        language: str,
        source: str,
    ):
        logging_data = {
            'server': guild.name if guild else 'DMChannel',
            'server_id': f'{guild.id}' if guild else '0',
            'user': f'{author.name}',
            'user_id': f'{author.id}',
            'language': language,
            'source': source,
        }
        headers = {'Authorization': self.emkc_key}

        async with self.session.post(
            'https://emkc.org/api/internal/piston/log',
            headers=headers,
            data=json.dumps(logging_data),
        ) as response:
            if response.status != 200:
                pass
        return True

    async def get_output_with_codeblock(
        self,
        guild: Guild | None,
        author: User | Member,
        content: str,
        mention_author: bool,
        needs_strict_re: bool,
    ):
        if needs_strict_re:
            match = self.run_regex_code_strict.search(content)
        else:
            match = self.run_regex_code.search(content)

        if not match:
            return 'Invalid command format'

        language, output_syntax, args, syntax, source, stdin = match.groups()

        if not language:
            language = syntax

        if language:
            language = language.lower()

        if language not in self.languages:
            return (
                f'Unsupported language: **{str(language)[:1000]}**\n'
                '[Request a new language](https://github.com/engineer-man/piston/issues)'
            )

        return await self.get_run_output(
            guild, author, source, language, output_syntax, args, stdin, mention_author
        )

    async def get_output_with_file(
        self,
        guild: Guild | None,
        author: User | Member,
        file: Attachment,
        input_language: str,
        output_syntax: str,
        args: str,
        stdin: str,
        mention_author: bool,
        content: str,
    ) -> str:
        MAX_BYTES = 65535
        if file.size > MAX_BYTES:
            return f'Source file is too big ({file.size}>{MAX_BYTES})'

        filename_split = file.filename.split('.')
        if len(filename_split) < 2:
            return 'Please provide a source file with a file extension'

        match = self.run_regex_file.search(content)
        if content and not match:
            raise commands.BadArgument('Invalid command format')

        language = input_language or filename_split[-1]
        if match:
            matched_language, output_syntax, args, stdin = match.groups()  # type: ignore
            if matched_language:
                language = matched_language

        language = language.lower()

        if language not in self.languages:
            return (
                f'Unsupported file extension: **{language}**\n'
                '[Request a new language](https://github.com/engineer-man/piston/issues)'
            )

        source = await file.read()
        try:
            source = source.decode('utf-8')
        except UnicodeDecodeError as e:
            return str(e)
        return await self.get_run_output(
            guild,
            author,
            source,
            language,  # type: ignore
            output_syntax,
            args,
            stdin,
            mention_author,
        )

    async def get_run_output(
        self,
        guild: Guild | None,
        author: User | Member,
        content: str,
        input_lang: str,
        output_syntax: str | None,
        args: str | None,
        stdin: str | None,
        mention_author: bool,
    ):
        lang = self.languages.get(input_lang, None)
        if not lang:
            return (
                f'Unsupported language: **{str(input_lang)}**\n'
                '[Request a new language](https://github.com/engineer-man/piston/issues)'
            )

        version = self.versions[lang]

        # Add boilerplate code to supported languages
        source = add_boilerplate(lang, content)

        # Split args at newlines
        argugments = []
        if args:
            argugments = [arg for arg in args.strip().split(',') if arg]

        if not source:
            raise commands.BadArgument('No source code found')

        # Call piston API
        data = {
            'language': lang,
            'version': version,
            'files': [{'content': source}],
            'args': argugments or '',
            'stdin': stdin or '',
            'log': 0,
        }
        headers = {'Authorization': self.emkc_key}
        async with self.session.post(
            'https://emkc.org/api/v2/piston/execute', headers=headers, json=data
        ) as response:
            try:
                r = await response.json()
            except ContentTypeError:
                raise PistonInvalidContentType('invalid content type')
        if not response.status == 200:
            raise PistonInvalidStatus(
                f'status {response.status}: {r.get("message", "")}'
            )

        comp_stderr = r['compile']['stderr'] if 'compile' in r else ''
        run = r['run']

        if run['output'] is None:
            raise PistonNoOutput('no output')

        # Logging
        await self.send_to_log(guild, author, lang, source)

        language_info = f'{lang}({version})'

        mention = author.mention + '' if mention_author else ''

        # Return early if no output was received
        if len(run['output'] + comp_stderr) == 0:
            return f'Your {language_info} code ran without output {mention}'

        # Limit output to 30 lines maximum
        output = '\n'.join((comp_stderr + run['output']).split('\n')[:30])

        # Prevent mentions in the code output
        output = escape_mentions(output)

        # Prevent code block escaping by adding zero width spaces to backticks
        output = output.replace('`', '`\u200b')

        # Truncate output to be below 2000 char discord limit.
        if len(comp_stderr) > 0:
            introduction = f'{mention}I received {language_info} compile errors\n'
        elif len(run['stdout']) == 0 and len(run['stderr']) > 0:
            introduction = f'{mention}I only received {language_info} error output\n'
        else:
            introduction = f'Here is your {language_info} output {mention}\n'
        truncate_indicator = '[...]'
        len_codeblock = 7  # 3 Backticks + newline + 3 Backticks
        available_chars = 2000 - len(introduction) - len_codeblock
        if len(output) > available_chars:
            output = (
                output[: available_chars - len(truncate_indicator)] + truncate_indicator
            )

        # Use an empty string if no output language is selected
        return (
            introduction
            + f'```{output_syntax or ""}\n'
            + output.replace('\0', "")
            + '```'
        )
