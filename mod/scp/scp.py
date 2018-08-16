import json
import random
import feedparser
import asyncio
import datetime
from time import mktime
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
		while not self.bot.is_closed():
			print(' > lc update')
			await self._update_lc()
			await asyncio.sleep(5*60)

	async def _update_lc(self):
		''' Updates the recently-created list '''
		lc_url = 'http://www.scp-wiki.net/feed/pages/pagename/most-recently-created/category/_default/tags/-admin/rating/%3E%3D-15/order/created_at+desc/limit/30/t/Most+Recently+Created'
		
		new_lc_list = feedparser.parse(lc_url)
		old_lc_links = []

		if self.lc_list:
			for item in self.lc_list['items']:
				old_lc_links.append(item['link'])

		announce = True
		for dex, item in enumerate(new_lc_list['items']):
			print('  >> found item {0}'.format(item['title']))
			if not self.lc_list:
				announce = False
				continue
			if item['link'] in old_lc_links:
				break
			if announce:
				print('  >> Alerting to {0}'.format(item['title']))
				self.lc_list = new_lc_list
				await self._alert_all_scp_channels(dex)
		self.lc_list = new_lc_list

	def _find_between(self, entire, start, end):
		startloc = entire.find(start)
		endloc = entire.find(end)
		if startloc == -1 or endloc == -1:
			return None
		else:
			return entire[startloc+len(start):endloc]
	
	async def _alert_all_scp_channels(self, index):
		''' Alerts all channels which are subscribed to new SCPs '''
		to_alert = {}
		with sql_cur(self.db) as cur:
			res = cur.execute('SELECT guild_id, scp_channel_id FROM guild_settings WHERE scp_channel_id!=-1;').fetchall()
			for result in res:
				print('  > found channel {0} in guild {1}'.format(result[1],result[0]))
				to_alert[result[0]] = result[1]
		print('  > enumerated channels')

		content = self._parse_rss_by_id(index)

		content_raw = self.lc_list['items'][index]['summary']
		crfa_clip_str = '<span class="printuser avatarhover"><a href="http://www.wikidot.com/user:info/'
		crfa_clip_loc = content_raw.find(crfa_clip_str)
		if not crfa_clip_loc:
			author_url = 'https://cdn.discordapp.com/embed/avatars/0.png'
			author_name = '???'
		else:
			content_raw_for_author = content_raw[crfa_clip_loc+len(crfa_clip_str):]

			author_url = self._find_between(content_raw_for_author, '<img class="small" src="', '" alt="')
			author_name = self._find_between(content_raw_for_author, '" alt="', '" style="background-image:url(')

			if not (author_url and author_name):
				author_url = 'https://cdn.discordapp.com/embed/avatars/0.png'
				author_name = '???'
				


		title = '\U0001F514 New Page on the SCP Wiki!'
		embed = discord.Embed(title=title, colour=discord.Colour(self.bot.embed_colour), url="http://www.scp-wiki.net/most-recently-created", timestamp=datetime.datetime.fromtimestamp(mktime(self.lc_list['items'][index]['published_parsed'])))
		embed.set_thumbnail(url="http://scp-wiki.wdfiles.com/local--files/component%3Atheme/logo.png")
		embed.set_footer(icon_url=author_url, text="By {author}".format(author=author_name))
		embed.add_field(name='{title}'.format(title=self.lc_list['items'][index]['title']), value='[{content}]({link})'.format(content=content, link=self.lc_list['items'][index]['link']), inline=False)
		
		print('  > generated embed')
		for guildid, chanid in to_alert.items():
			print('  > sent to channel {0} in guild {1}'.format(chanid, guildid))
			channel = self.bot.get_channel(chanid)
			await channel.send(embed=embed)
	
	def _parse_rss_by_id(self, i):
		if not self.lc_list:
			return 'No content'
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

		return content


	@commands.command()
	@permissions.require(permissions.manage)
	async def lc_here(self, ctx):
		''' Sets the channel for automatic new-scp announcements '''
		with sql_cur(self.db) as cur:
			res = cur.execute('SELECT guild_id FROM guild_settings WHERE guild_id=?;', (ctx.guild.id,)).fetchall()
			if not res:
				cur.execute('INSERT INTO guild_settings (guild_id, scp_channel_id) VALUES (?,?)', (ctx.guild.id, ctx.channel.id))
			else:
				cur.execute('UPDATE guild_settings SET scp_channel_id=? WHERE guild_id=?', (ctx.channel.id, ctx.guild.id))
		await ctx.message.add_reaction('✅')

	@commands.command()
	@permissions.require(permissions.manage)
	async def lc_nowhere(self, ctx):
		''' Removes the set channel for automatic new-scp announcements '''
		with sql_cur(self.db) as cur:
			res = cur.execute('SELECT guild_id FROM guild_settings WHERE guild_id=?;', (ctx.guild.id,)).fetchall()
			if not res:
				cur.execute('INSERT INTO guild_settings (guild_id, scp_channel_id) VALUES (?,?)', (ctx.guild.id, -1))
			else:
				cur.execute('UPDATE guild_settings SET scp_channel_id=? WHERE guild_id=?', (-1, ctx.guild.id))
		await ctx.message.add_reaction('✅')

	
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
			content = self._parse_rss_by_id(i)
			embed.add_field(name='{index:02d}: {title} (pub {pub})'.format(index=i+1,title=self.lc_list['items'][i]['title'], pub=self.lc_list['items'][i]['published'][:-6]), value='[{content}]({link})'.format(content=content[:1000], link=self.lc_list['items'][i]['link']), inline=False)

		msg = await ctx.send(embed=embed)
		await track(msg, ctx.author)

def setup(bot):
	bot.add_cog(SCP(bot, sql_con()))
