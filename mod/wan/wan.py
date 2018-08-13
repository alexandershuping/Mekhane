import json
import random

import discord
from discord.ext import commands

import permissions
from messages import track
from sql.sql import sql_cur, sql_con

class WAN:
	''' Miscellaneous fun things '''
	def __init__(self, bot, db_handle):
		self.bot = bot
		self.db = db_handle
		with open('data/cakes.json') as cakefile:
			self.cakes = json.load(cakefile)
	
	@commands.command()
	async def assimilate(self, ctx):
		''' Shows what you could become if only you submitted to Mekhane's word. '''
		url = 'https://robohash.org/{0}'.format(ctx.message.author.id)
		m = await ctx.send('If you allowed yourself to be freed from your fleshy cage, you would look something like this: {0}'.format(url))
		await track(m, ctx.author)

	
	@commands.command()
	async def bake(self, ctx, dex=None):
		''' Bakes a delicious cake '''
		cake = random.choice(self.cakes)
		if dex:
			cake = self.cakes[int(dex)]
		m = await ctx.send(str(cake))
		await track(m, ctx.author)

def setup(bot):
	bot.add_cog(WAN(bot, sql_con()))
