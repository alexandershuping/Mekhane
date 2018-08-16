import json
import random
import feedparser
import asyncio
import datetime
import re

import discord
from discord.ext import commands

import permissions
from messages import track
from sql.sql import sql_cur, sql_con

class SCP:
	''' Keeps track of new SCP articles through RSS '''
	def __init__(self, bot, db_handle):
		self.bot = bot
		self.db = db_handle
		self.lc_list = {}
		self.bot.loop.create_task(self._update_lc_loop())
	
	async def _update_lc_loop(self):
		''' Automatically update recently-created every 5 minutes '''
		await self.bot.wait_until_ready()
		print(' > lc update')
		await self._update_lc()
		await asyncio.sleep(60*5)

	async def _update_lc(self):
		''' Updates the recently-created list '''
		lc_url = 'http://www.scp-wiki.net/feed/pages/pagename/most-recently-created/category/_default/tags/-admin/rating/%3E%3D-15/order/created_at+desc/limit/30/t/Most+Recently+Created'
		new_lc_list = feedparser.parse(lc_url)
		# TODO: update all channels with new articles
		self.lc_list = new_lc_list
	
	#@commands.command()
	#async def set_channel(self, ctx):
	#	''' Shows what you could become if only you submitted to Mekhane's word. '''
	#	url = 'https://robohash.org/{0}'.format(ctx.message.author.id)
	#	m = await ctx.send('If you allowed yourself to be freed from your fleshy cage, you would look something like this: {0}'.format(url))
	#	await track(m, ctx.author)

	
	@commands.command()
	async def lc(self, ctx, count=3, update=False):
		''' Lists recently-created entries (max 29) '''
		if count >= 30:
			msg = await ctx.send('I will not pull more than 29 entries at once.')
			await track(msg, ctx.author)
			return
		elif count <= 0:
			msg = await ctx.send('{0} is not a valid number of entries.'.format(count))
			await track(msg, ctx.author)
			return
		
		if update:
			await self._update_lc()
		title = '\U0001F514 Recently-Created Pages'
		embed = discord.Embed(title=title, colour=discord.Colour(self.bot.embed_colour), url="http://www.scp-wiki.net/most-recently-created", description="The {count} most recently-created pages on the SCP Wiki".format(count=count), timestamp=datetime.datetime.now())
		embed.set_thumbnail(url="http://scp-wiki.wdfiles.com/local--files/component%3Atheme/logo.png")
		embed.set_footer(text="Requested by {username}".format(username=ctx.author.display_name), icon_url=ctx.author.avatar_url)

		for i in range(0,count):
			content_raw = self.lc_list['items'][i]['summary']

			# Parse the containment procedures (or the first paragraph if that fails)
			content = None
			#print('Parsing raw content "{0}"'.format(content_raw))
			pstart_string = '<p><strong>Special Containment Procedures:</strong>'
			pstart_loc = content_raw.find(pstart_string)
			if pstart_loc == -1:
				#print('  > No SCP indicator found. Searching for paragraphs...')
				pstart_string = '<p>'
				pstart_loc = content_raw.find(pstart_string)
				if pstart_loc == -1:
					#print('  > No paragraphs found. Aborting preview creation.')
					content = None
				else:
					content = content_raw[pstart_loc+len(pstart_string):]
					#print('  > Found paragraph at {0}: |{1}|.'.format(pstart_loc+len(pstart_string), content[:500]))
			else:
				content = content_raw[pstart_loc+len(pstart_string):]
				#print('  > Found SCP indicator at {0}: |{1}|.'.format(pstart_loc+len(pstart_string), content[:500]))
				
			if not content:
				content = 'No preview available.'
			else:
				pend_loc = content.find('</p>')
				content = content[:pend_loc]
				#print('  > Trimming using </p> at {0}: |{1}|.'.format(pend_loc, content[:500]))
				content = re.sub('<.*?>', '', content)
				content = re.sub('&.*?;', '', content)
				#print('  > Scrubbed HTML tags - final: |{0}|.'.format(content[:500]))
			
			trunc_len = 200
			
			if len(content) > trunc_len:
				content = content[:trunc_len] + '...'
			embed.add_field(name='{index:02d}: {title} (pub {pub})'.format(index=i+1,title=self.lc_list['items'][i]['title'], pub=self.lc_list['items'][i]['published'][:-6]), value='[{content}]({link})'.format(content=content[:1000], link=self.lc_list['items'][i]['link']), inline=False)

		msg = await ctx.send(embed=embed)
		await track(msg, ctx.author)

def setup(bot):
	bot.add_cog(SCP(bot, sql_con()))
