#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import traceback
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger(__name__)

initial_extensions = (
    'cogs.admin',
    'cogs.guild_log',
    'cogs.map_testing',
    'cogs.meme',
    'cogs.misc',
    'cogs.profile',
    'cogs.records',
    'cogs.teeworlds',
    'cogs.votes',
)


def get_traceback(error: Exception) -> str:
    return ''.join(traceback.format_exception(type(error), error, error.__traceback__))


class DDNet(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(command_prefix='$', fetch_offline_members=True, help_command=commands.MinimalHelpCommand())

        self.config = kwargs.pop('config')
        self.pool = kwargs.pop('pool')
        self.session = kwargs.pop('session')

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
            except Exception:
                log.exception('Failed to load extension %r', extension)
            else:
                log.info('Successfully loaded extension %r', extension)

    async def on_ready(self):
        self.start_time = datetime.utcnow()
        log.info('Logged in as %s (ID: %d)', self.user, self.user.id)

    async def on_resumed(self):
        log.info('Resumed')

    async def close(self):
        log.info('Closing')
        await super().close()
        await self.pool.close()
        await self.session.close()

    async def on_message(self, message: discord.Message):
        await self.wait_until_ready()
        await self.process_commands(message)

    async def on_command(self, ctx: commands.Context):
        if ctx.guild is None:
            destination = 'Private Message'
            guild_id = None
        else:
            destination = f'#{ctx.channel} ({ctx.guild})'
            guild_id = ctx.guild.id

        log.info('%s used command in %s: %s', ctx.author, destination, ctx.message.content)

        query = """INSERT INTO stats_commands (guild_id, channel_id, author_id, timestamp, command)
                   VALUES ($1, $2, $3, $4, $5, $6);
                """
        values = (
            guild_id,
            ctx.channel.id,
            ctx.author.id,
            ctx.message.created_at,
            ctx.command.qualified_name
        )

        await self.pool.execute(query, *values)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        command = ctx.command

        msg = None
        if isinstance(error, commands.MissingRequiredArgument):
            msg = f'{self.command_prefix}{command.qualified_name} {command.signature}'
        elif isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, discord.Forbidden):
                msg = 'I do not have proper permission'
            else:
                trace = get_traceback(error.original)
                log.error('Command %r caused an exception\n%s', command.qualified_name, trace)
                if isinstance(error.original, aiohttp.ClientConnectorError):
                    msg = 'Could not fetch/send data'
                else:
                    msg = 'An internal error occurred'

        if msg is not None:
            try:
                await ctx.send(msg)
            except discord.Forbidden:
                pass

    async def on_error(self, event: str, *args, **kwargs):
        log.exception('Event %r caused an exception', event)
