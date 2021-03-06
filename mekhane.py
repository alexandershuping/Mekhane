#!/usr/bin/env python
import sys
import traceback
import math
import json

import discord
from discord.ext import commands

from sql.sql import sql_cur, sql_con
import permissions
from messages import track

settings = None
bot_version = ''
with open('.bot_info.json') as bot_info:
	settings = json.load(bot_info)

with open('version.json') as version:
	bot_version = json.load(version)['version']

bot_url = 'https://discordapp.com/api/oauth2/authorize?client_id={0}&scope=bot&permissions=0'
bot_prefix = settings['command_prefix']
bot_desc = settings['description']
bot_token = settings['token']


class Mekhane_Core:
	''' Basic functionality '''
	def __init__(self, bot, db_hook):
		self.bot = bot
		self.db = db_hook

	
	@commands.command()
	async def zyn(self, ctx):
		''' Marp. '''
		msg = await ctx.send('Marp.')
		await track(msg, ctx.author)

	
	@commands.command()
	async def version(self, ctx):
		''' Returns the current version of Mekhane. '''
		global bot_version
		msg = await ctx.send('Mekhane version {0}'.format(bot_version))
		await track(msg, ctx.author)

	
	def _construct_error_embed(self, command_name, error_name, error_text, full_command_string, full_backtrace=None):
		title = "⚠ An error was encountered while processing the {0} command".format(command_name)
		embed = discord.Embed(title=title, colour=discord.Colour(self.bot.embed_colour), description="**{0}**: ```{1}```".format(error_name, str(error_text)))
		embed.set_footer(text="Report bugs at https://github.com/alexandershuping/mekhane")
		embed.add_field(name="While processing the command:", value="``{0}``".format(full_command_string), inline=False)
		if full_backtrace:
			itr = 1
			total_itrs = math.ceil(len(full_backtrace)/512)
			while len(full_backtrace) > 0:
				if len(full_backtrace) > 512:
					embed.add_field(name="Backtrace ({0} of {1}):".format(itr, total_itrs), value="```{0}```".format(full_backtrace[:512]), inline=False)
					full_backtrace = full_backtrace[512:]
					itr = itr + 1
				else:
					embed.add_field(name="Backtrace ({0} of {1}):".format(itr, total_itrs), value="```{0}```".format(full_backtrace), inline=False)
					break
		else:
			embed.add_field(name='Press \u2733', value='for full error backtrace', inline=False)
		
		return embed
				
	def _construct_unknown_command_embed(self, error_text, full_text):
		title = "❓ Invalid command."
		embed = discord.Embed(title=title, colour=discord.Colour(self.bot.embed_colour), description='```{0}```'.format(error_text))
		embed.set_footer(text="Use {0}help for a list of commands.".format(self.bot.command_prefix))
		embed.add_field(name="While processing the command:", value="``{0}``".format(full_text), inline=False)

		return embed

	async def on_command_error(self, ctx, error):
		if type(error) == discord.ext.commands.MissingPermissions:
			await ctx.message.add_reaction('⛔')
			embed = discord.Embed(title='⛔ Insufficient Permissions', colour=discord.Colour(self.bot.embed_colour), description="You are not permitted to run the command ``{0}``".format(ctx.message.content))
			embed.add_field(name="Reason:", value=str(error))
			msg = await ctx.send(content='', embed=embed)
			await track(msg, ctx.author)
		else:
			embed = None
			if not ctx.command:
				embed = self._construct_unknown_command_embed(str(error), ctx.message.content)
			else:
				embed = self._construct_error_embed(ctx.command.name, str(type(error)), str(error), ctx.message.content)

			await ctx.message.add_reaction('⚠')
			msg = await ctx.send(content='', embed=embed)
			await track(msg, ctx.author)
			if not ctx.command:
				return
			await msg.add_reaction('\u2733')
			with sql_cur(self.db) as cur:
				bt_string = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
				print('Mekhane encountered an error:\n{0}'.format(bt_string))
				cur.execute('INSERT INTO error_messages (message_id, channel_id, command_name, error_name, error_text, full_backtrace, full_command_string) VALUES (?,?,?,?,?,?,?);',(msg.id, msg.channel.id, ctx.command.name, str(type(error)), str(error), bt_string, ctx.message.content))
	
	async def on_message(self, message):
		''' Checks / actions for every message '''
		if message.author.id != self.bot.user.id and self.bot.user in message.mentions:
			chan = message.channel
			my_message = await chan.send('Use ``{0}help`` for a list of commands. (press 🚮 to remove)'.format(bot_prefix))
			await track(my_message, message.author)

	async def on_raw_reaction_add(self, payload):
		if payload.user_id == self.bot.user.id:
			return
		if payload.emoji.name == '🚮':
			is_tracked = False
			sender_uid = None
			with sql_cur(self.db) as cur:
				cur.execute("SELECT messid, sender_uid FROM tracked_messages WHERE messid=?", (payload.message_id,))
				row = cur.fetchone()
				if row:
					is_tracked = True
					sender_uid = row[1]
			
			if is_tracked:
				reacting_member = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
				can_delete = self.bot.get_channel(payload.channel_id).permissions_for(reacting_member).manage_messages
				if payload.user_id == sender_uid or can_delete:
					relevant_message = await self.bot.get_channel(payload.channel_id).get_message(payload.message_id)
					await relevant_message.delete()
		elif payload.emoji.name == '\u2733':
			row = None
			with sql_cur(self.db) as cur:
				cur.execute('SELECT command_name, error_name, error_text, full_command_string, full_backtrace FROM error_messages WHERE message_id=? AND channel_id=?;',(payload.message_id, payload.channel_id))
				row = cur.fetchone()
			if not row:
				return

			to_edit = await self.bot.get_channel(payload.channel_id).get_message(payload.message_id)
			new_embed = self._construct_error_embed(row[0],row[1],row[2],row[3],row[4])
			await to_edit.edit(content='⚠ Command error ⚠',embed=new_embed)
	

	async def on_raw_reaction_remove(self, payload):
		if payload.user_id == self.bot.user.id:
			return
		if payload.emoji.name == '\u2733':
			row = None
			with sql_cur(self.db) as cur:
				cur.execute('SELECT command_name, error_name, error_text, full_command_string, full_backtrace FROM error_messages WHERE message_id=? AND channel_id=?;',(payload.message_id, payload.channel_id))
				row = cur.fetchone()
			if not row:
				return

			to_edit = await self.bot.get_channel(payload.channel_id).get_message(payload.message_id)
			new_embed = self._construct_error_embed(row[0],row[1],row[2],row[3])
			await to_edit.edit(content='⚠ Command error ⚠',embed=new_embed)
	
				

	
	async def on_ready(self):
		global bot_url
		processed_url = bot_url.format(self.bot.user.id)
		print('MEKHANE HAS RISEN! \nUser info: {0}\nInvite URL: {1}'.format(self.bot.user, processed_url))
		await self.bot.change_presence(activity=discord.Game(name='AND BREAK THE FLESH'))
	
	async def on_command_completion(self, ctx):
		if ctx.command.name == 'help':
			async for msg in ctx.history(limit=10):
				if msg.author == self.bot.user:
					await track(msg, ctx.message.author)
					break
				

	@commands.command()
	async def ping(self, ctx):
		''' Pings Mekhane to check your connection. '''
		msg = await ctx.send('Pong, my child.'.format(ctx.author.mention))
		await track(msg, ctx.author)
	
	@commands.command()
	async def invite(self, ctx):
		''' Return a URL to invite Mekhane to your server. '''
		global bot_url
		processed_url = bot_url.format(self.bot.user.id)
		embed = discord.Embed(title="Click here to invite {0} to your server.".format(self.bot.user), colour=discord.Colour(self.bot.embed_colour), url=processed_url)
		embed.set_author(name=str(self.bot.user), url=processed_url, icon_url=self.bot.user.avatar_url)
		embed.set_footer(text=processed_url)

		msg = await ctx.send(content="Invite me to your server!", embed=embed)
		await track(msg, ctx.author)


global_db_hook = sql_con()

mekhane = commands.Bot(command_prefix=bot_prefix, description=bot_desc)
mekhane.embed_colour = 0x9030d0
mekhane.add_cog(Mekhane_Core(mekhane, global_db_hook))
mekhane.load_extension('permissions')
mekhane.load_extension('mod.wan.wan')
mekhane.load_extension('mod.scp.scp')
#mekhane.load_extension('mod.rp.rp')

@mekhane.check
async def global_ensure_interact(ctx):
	return await permissions.has_permission(ctx, permissions.interact)

mekhane.run(bot_token) # Token is loaded from the file '.bot_info.json' - Rename 'bot-info.json.skel' to '.bot-info.json' and put your token there.
