#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# PogoRgbgNEST Bot 

# Copyright (C) 2018  @ChrisM431 (Telegram)

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

## Constants ##
config_name = 'pogonestbot.ini'
## --------- ##

import datetime
import sched, time
import csv
import json
import configparser
import logging
import MySQLdb

from math import cos,sin,asin,sqrt
from uuid import uuid4

from telegram.utils.helpers import escape_markdown
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton,InlineQueryResultArticle, 
						  ParseMode, InputTextMessageContent,InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
						  ConversationHandler, InlineQueryHandler, CallbackQueryHandler)
from telegram.ext.dispatcher import run_async

# Init ConfigParser
config = configparser.ConfigParser()
config.read(config_name)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
					level=logging.INFO,
					filename=config['SYSTEM']['sys_log_dir'])

logger = logging.getLogger(__name__)

# Print Debug Logging
def dbglog(message):
	if int(config['SYSTEM']['sys_enable_debug_log']) == 1:
		logging.info(message)

group_id = config['TELEGRAM']['bot_group_id']

admins = json.loads(config['TELEGRAM']['bot_admins_ids'])

# States for Pokemon Change
POKEMON = range(1)

class DB:
	"""Database operations class"""
	conn = None

	def connect(self):
		"""Connect to the Database using the given credentials"""
		self.conn = MySQLdb.connect(host=config['DATABASE']['db_host'],
						user=config['DATABASE']['db_user'],
						passwd=config['DATABASE']['db_password'],
						db=config['DATABASE']['db_name'],
						use_unicode=True,
						charset="utf8")

	def query(self, sql):
		"""Execute the Query"""
		try:
			cursor = self.conn.cursor()
			cursor.execute(sql)
		except (AttributeError, MySQLdb.OperationalError):
			self.connect()
			cursor = self.conn.cursor()
			cursor.execute(sql)
		return cursor
	
	def commit(self):
		"""Commit the query"""
		try:
			self.conn.commit()
		except (AttributeError, MySQLdb.OperationalError):
			self.connect()
			self.conn.commit()

def start(bot, update):	
	"""/start Command Handler"""
	logging.info('Bot started by ' + str(update.message.from_user.username))
	keyboard = [[InlineKeyboardButton("Neuer Eintrag", callback_data='new'),
				 InlineKeyboardButton("Liste", callback_data='list')],
				 [InlineKeyboardButton("Nestwechsel", callback_data='nest_switch')]]
				 
	reply_markup = InlineKeyboardMarkup(keyboard)

	bot.send_message(text=config['MESSAGE']['message_disclaimer'],
		chat_id=update.message.chat_id,
		parse_mode=ParseMode.HTML,
		reply_markup=reply_markup)	
		
def fileexport():
	"""	Fileexport Handler
		Write Database content to csv file"""
	db = DB()	
	sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon"
	cursor = db.query(sql)
	filename = "{}.csv".format(datetime.datetime.now().strftime("%d-%B-%Y"))
	with open(filename, "w", newline='') as csv_file:
		csv_writer = csv.writer(csv_file)
		csv_writer.writerow([i[0] for i in cursor.description]) # write headers
		csv_writer.writerows(cursor)
	return filename

def export(bot,update):
	"""/export Command Handler"""
	filename = fileexport()
	bot.send_message(text="Nest Übersicht vom : {}".format(datetime.datetime.now().strftime("%d.%B %Y -- %H:%M")),
		chat_id=update.message.chat_id,
		parse_mode=ParseMode.HTML,
		reply_markup=None)
	bot.send_document(chat_id=update.message.chat_id, 
		document=open(filename, 'rb'))	
	
def init(bot, update):
	"""	/init Command Handler
		Init the basis functionality such as checking for all messages in the group"""
	query = update.callback_query
	dbglog("Init started...")
	bot.send_message(text="Initialisierung/Update gestartet...",
		chat_id=update.message.chat_id,
		parse_mode=ParseMode.HTML,
		reply_markup=None)
	logging.info('Init started by ' + str(update.message.from_user.username))
	db = DB()	
	sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon"
	cursor = db.query(sql)
	result = cursor.fetchall()
	if len(result) > 0:
		dbglog('Result > 0')
		count_msgs = 0
		for nest_tuple in result:
			nest_data = list(nest_tuple)
			if not nest_data[2]:
				nest_data[2] = '-'
			compare = 'Missigno.'
			if nest_data[2] == compare:
				nest_data[2] = '-'
				
			size_to_string = ''
			# Größe definition
			if nest_data[1] == 1:
				size_to_string = 'Klein'
			elif nest_data[1] == 2:
				size_to_string = 'Mittel'
			else:
				size_to_string = 'Groß'
			
			dbglog('nest_data[2]: ' + nest_data[2])
			final_message = ""
			final_message = final_message + '<b>Ort:</b> <a href="https://maps.google.com/?q=' + "{:.6f}".format(nest_data[3]) + ',' + "{:.6f}".format(nest_data[4]) + '">' + nest_data[0] + '</a>' + "\n"				
			final_message = final_message + '<b>Pokemon:</b> ' + nest_data[2].capitalize() + ('' if (not nest_data[7]) else ' ✨') + "\n"
			final_message = final_message + '<b>Größe:</b> ' + size_to_string + "\n" # + size_to_string + "\n" # + str(nest_data[1]) + "\n"
			final_message = final_message + '<i>Aktualisiert: ' + datetime.datetime.now().strftime("%d.%m.%y %H:%M") + '</i> N-ID: ' + str(nest_data[6]) + "\n"
			final_message = final_message + config['MESSAGE']['message_map_link']
			
			#keyboard = [[InlineKeyboardButton("Ändern", callback_data='change1:'+nest_data[0]),
			#		 InlineKeyboardButton("Bestätigung", callback_data='confirm:'+nest_data[0])]]
			#reply_markup = InlineKeyboardMarkup(keyboard)
			
			if nest_data[5]:
				try:
					bot.edit_message_text(
						final_message,
						group_id,
						nest_data[5],
						parse_mode=ParseMode.HTML,
						disable_web_page_preview=True,
						reply_markup=None)
						#reply_markup=reply_markup)
					count_msgs += 1
					if count_msgs > 15:
						time.sleep(62)
						count_msgs = 0
				except:
					msg = bot.send_message(
						chat_id=group_id,
						text=final_message,				
						message_id=query.message.message_id,
						parse_mode=ParseMode.HTML,
						disable_web_page_preview=True,
						reply_markup=None)
						#reply_markup=reply_markup)
					count_msgs += 1
					if count_msgs > 15:
						time.sleep(62)
						count_msgs = 0
					
					msg_id = msg["message_id"]
					dbglog(msg_id)
					sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
					dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
					cursor = db.query(sql)
					db.commit()
			else:
				msg = bot.send_message(
					chat_id=group_id,
					text=final_message,				
					message_id=query.message.message_id,
					parse_mode=ParseMode.HTML,
					disable_web_page_preview=True,
					reply_markup=None)
					#reply_markup=reply_markup)
				count_msgs += 1
				if count_msgs > 15:
					time.sleep(62)
					count_msgs = 0
				
				msg_id = msg["message_id"]
				dbglog(msg_id)
				sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
				dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
				cursor = db.query(sql)
				db.commit()
	dbglog("Done!")
	bot.send_message(text="Initialisierung/Update abgeschlossen!",
		chat_id=update.message.chat_id,
		parse_mode=ParseMode.HTML,
		reply_markup=None)
	
# Change Pokemon's nesting and shiny state
def pokedex(bot, update):
	# Ask for Pokemon's name
	update.message.reply_text(
		'Welches Pokemon soll verändert werden?',
		reply_markup=None)
	return POKEMON
	
def pokemon(bot,update):
	query = update.callback_query
	pokemon = update.message.text
	dbglog(pokemon)
	sql = "SELECT name,id FROM `pokemon_de` WHERE lower(`name`) like '{}%' or lower(`name`) like '%{}%'".format(pokemon.lower(),pokemon.lower())
	dbglog(sql)
	db = DB()
	cursor = db.query(sql)
	result = cursor.fetchall()
	keyboard = []
	if len(result) > 0:			
		for nest_tuple in result:
			pokemon_data = list(nest_tuple)
			inline_button = []				
			inline_button.append(InlineKeyboardButton("{}".format(pokemon_data[0]).capitalize(), callback_data='pokedex:'+str(pokemon_data[1])))	
			keyboard.append(inline_button)
		
		#inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
		#keyboard.append(inline_cancel_button)
		reply_markup = InlineKeyboardMarkup(keyboard)			
		message_txt = "Welches Pokemon genau?"
		update.message.reply_text(
			message_txt,			
			reply_markup=reply_markup)
		return ConversationHandler.END
	else:
		message_txt = "Kein Pokemon gefunden. Bitte erneut eingeben."
		update.message.reply_text(
			message_txt,			
			reply_markup=None)
		pokedex(bot,update)
	
def button(bot, update):
	query = update.callback_query
	option = query.data	
	msg_id = query.message.message_id
	dbglog(query.message.message_id)
	dbglog("Option: " + option)
	
	# Explicit option=='new' to prevent 'newX' match
	if option == 'new':
		db = DB()
		sql = "select upper(left(name,1)) as first_letter from nester group by left(name,1)"
		cursor = db.query(sql)
		result = [row[0] for row in cursor.fetchall()]
		keyboard = []
		if len(result) > 0:
			x = 0			
			inline_row = []
			length = len(result)
			for i in range(length):
				dbglog(result[i])
				inline_row.append( InlineKeyboardButton("{}".format(result[i]).capitalize(), callback_data='new2:'+str(result[i]) ) )
				x += 1
				if x > 5:
					keyboard.append(inline_row)
					inline_row = []
					x = 0
				
			if x <= 5:
				keyboard.append(inline_row)
			
			inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
			keyboard.append(inline_cancel_button)
			reply_markup = InlineKeyboardMarkup(keyboard)	
			dbglog(query)
			message_txt = "Welches Nest?"
			bot.edit_message_text(
						message_txt,
						query.message.chat.id,
						msg_id,						
						parse_mode=ParseMode.HTML,
						reply_markup=reply_markup)
	
	if 'new2' in option:
		#msg_id = query.message.message_id
		nest_first_letter = option.split(':')[1]
		db = DB()
		sql = "select `name` from nester where `name` like '{}%'".format(nest_first_letter)
		db = DB()
		cursor = db.query(sql)
		result = cursor.fetchall()
		keyboard = []
		
		if len(result) > 0:			
			for nest_tuple in result:
				result_data = list(nest_tuple)
				inline_button = []				
				inline_button.append(InlineKeyboardButton("{}".format(result_data[0]), callback_data='change1:'+str(result_data[0])))	
				keyboard.append(inline_button)
			
			inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
			keyboard.append(inline_cancel_button)
			reply_markup = InlineKeyboardMarkup(keyboard)	
			dbglog(query)
			bot.edit_message_text(
						query.message.text,
						query.message.chat.id,
						msg_id,						
						parse_mode=ParseMode.HTML,
						reply_markup=reply_markup)
		
	if option == 'list':
		db = DB()
		sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.id, nester.msg_id from nester left join pokemon_de on pokemon_de.id=nester.pokemon"
		dbglog(sql)
		cursor = db.query(sql)
		result = cursor.fetchall()
		
		results = [];
		
		if len(result) > 0:
			for nest_tuple in result:
				nest_data = list(nest_tuple)
				dbglog(nest_data)
				if not nest_data[2]:
				#	continue
					nest_data[2] = '-'
				compare = 'Missigno.'
				if nest_data[2] == compare:
					nest_data[2] = '-'
					
				size_to_string = ''
				# Größe definition
				if nest_data[1] == 1:
					size_to_string = 'Klein'
				elif nest_data[1] == 2:
					size_to_string = 'Mittel'
				else:
					size_to_string = 'Groß'
				
				final_message = ""
				final_message = final_message + '<b>Ort:</b> <a href="https://maps.google.com/?q=' + "{:.6f}".format(nest_data[3]) + ',' + "{:.6f}".format(nest_data[4]) + '">' + nest_data[0] + '</a>' + "\n"								
				final_message = final_message + '<b>Pokemon:</b> ' + nest_data[2].capitalize() + "\n"
				final_message = final_message + '<b>Größe:</b> ' + size_to_string + "\n" # + str(nest_data[1]) + "\n"
				final_message = final_message + '<i>Aktualisiert: ' + datetime.datetime.now().strftime("%d.%m.%y %H:%M") + '</i> N-ID: ' + str(nest_data[6]) + "\n"
				final_message = final_message + config['MESSAGE']['message_map_link']
				
				dbglog(final_message)
								
				keyboard2 = [[InlineKeyboardButton("Ändern", callback_data='change1:'+nest_data[0])]]
				reply_markup2 = InlineKeyboardMarkup(keyboard2)

				msg = bot.send_message(
					chat_id=query.message.chat_id,
					text=final_message,				
					message_id=query.message.message_id,
					parse_mode=ParseMode.HTML,
					disable_web_page_preview=True,
					reply_markup=reply_markup2)
					
				dbglog(msg)
				dbglog(msg["message_id"])
	
	if 'change1' in option:		
		place = option.split(':')[1]
		keyboard = []
		
		sql = "SELECT UPPER(LEFT(pokemon_de.name,1)) as first_letter FROM `nesting_pokemon` LEFT JOIN `pokemon_de` ON pokemon_de.id = `nesting_pokemon`.`pokemon` WHERE `is_nesting` = '1' AND pokemon_de.name IS NOT NULL GROUP BY LEFT(pokemon_de.name,1)"
		db = DB()
		cursor = db.query(sql)
		result = [row[0] for row in cursor.fetchall()]
		
		if len(result) > 0:
			x = 0			
			inline_row = []
			length = len(result)
			for i in range(length):
				dbglog(result[i])
				inline_row.append( InlineKeyboardButton("{}".format(result[i]).capitalize(), callback_data='change2:'+str(result[i])+':'+place) )
				x += 1
				if x > 5:
					keyboard.append(inline_row)
					inline_row = []
					x = 0
				
			if x <= 5:
				keyboard.append(inline_row)
			
			inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
			keyboard.append(inline_cancel_button)
			reply_markup = InlineKeyboardMarkup(keyboard)	
			dbglog(query)
			final_text = "Welches Pokemon?"
			bot.edit_message_text(
						final_text,
						query.message.chat.id,
						msg_id,						
						parse_mode=ParseMode.HTML,
						reply_markup=reply_markup)
					
	if	'change2' in option:
		dbglog(option)
		place = option.split(':')[2]
		poke_letter = option.split(':')[1]
		keyboard = []
				
		sql = "SELECT pokemon_de.name, pokemon, is_nesting, is_shiny FROM `nesting_pokemon` left JOIN pokemon_de on pokemon_de.id = pokemon WHERE nesting_pokemon.is_nesting = '1' AND pokemon_de.name LIKE '{}%'".format(poke_letter)
		db = DB()
		cursor = db.query(sql)
		result = cursor.fetchall()
		
		if len(result) > 0:			
			for nest_tuple in result:
				pokemon_data = list(nest_tuple)
				inline_button = []				
				inline_button.append(InlineKeyboardButton("{}".format(pokemon_data[0]).capitalize(), callback_data='pokemon:'+str(pokemon_data[1])+':'+place))	
				keyboard.append(inline_button)
			
			inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
			keyboard.append(inline_cancel_button)
			reply_markup = InlineKeyboardMarkup(keyboard)	
			dbglog(query)
			bot.edit_message_text(
						query.message.text,
						query.message.chat.id,
						msg_id,						
						parse_mode=ParseMode.HTML,
						reply_markup=reply_markup)
						
	if 'pokemon' in option:
		keyboard = []
		new_pokemon = option.split(':')[1]
		place = option.split(':')[2]
		sql = "update nester set pokemon = {} where name = '{}'".format(new_pokemon,place)
		db = DB()
		cursor = db.query(sql)
		db.commit()
		
		sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon where nester.name='{}'".format(place)		
		cursor = db.query(sql)
		cursor.execute(sql)
		nest_tuple = cursor.fetchall()[0]
		
		nest_data = list(nest_tuple)
		if not nest_data[2]:
			nest_data[2] = '-'
		compare = 'Missigno.'
		if nest_data[2] == compare:
			nest_data[2] = '-'
		
		size_to_string = ''
		# Größe definition
		if nest_data[1] == 1:
			size_to_string = 'Klein'
		elif nest_data[1] == 2:
			size_to_string = 'Mittel'
		else:
			size_to_string = 'Groß'
				
		final_message = ""
		final_message = final_message + '<b>Ort:</b> <a href="https://maps.google.com/?q=' + "{:.6f}".format(nest_data[3]) + ',' + "{:.6f}".format(nest_data[4]) + '">' + nest_data[0] + '</a>' + "\n"				
		final_message = final_message + '<b>Pokemon:</b> ' + nest_data[2].capitalize() + ('' if (not nest_data[7]) else ' ✨') + "\n"
		final_message = final_message + '<b>Größe:</b> ' + size_to_string + "\n" # + str(nest_data[1]) + "\n"
		final_message = final_message + '<i>Aktualisiert: ' + datetime.datetime.now().strftime("%d.%m.%y %H:%M") + '</i> N-ID: ' + str(nest_data[6]) + "\n"
		final_message = final_message + config['MESSAGE']['message_map_link']
				
		bot.edit_message_text(
						final_message,
						query.message.chat.id,
						msg_id,						
						parse_mode=ParseMode.HTML,
						disable_web_page_preview=True,
						reply_markup=None)
		bot.answer_callback_query(
			query.id,
			"{} hinzugefügt".format(nest_data[2].capitalize()))
			
		if nest_data[5]:
			try:
				bot.edit_message_text(
					final_message,
					group_id,
					nest_data[5],
					parse_mode=ParseMode.HTML,
					disable_web_page_preview=True,
					reply_markup=None)
			except:
				msg = bot.send_message(
				chat_id=group_id,
				text=final_message,				
				message_id=query.message.message_id,
				parse_mode=ParseMode.HTML,
				disable_web_page_preview=True,
				reply_markup=None)
			
				msg_id = msg["message_id"]
				dbglog(msg_id)
				sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
				dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
				cursor = db.query(sql)
				db.commit()			
		else:
			msg = bot.send_message(
				chat_id=group_id,
				text=final_message,				
				message_id=query.message.message_id,
				parse_mode=ParseMode.HTML,
				disable_web_page_preview=True,
				reply_markup=None)
			
			msg_id = msg["message_id"]
			dbglog(msg_id)
			sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
			dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
			cursor = db.query(sql)
			db.commit()		
		logging.info("Nest {} updated by {}".format(nest_data[0], str(query.from_user.username)) )

	if 'cancel' in option:
		option = option.split('>')[1]
		dbglog("Cancel_Option: " + option)
		if 'new2' in option:
			msg_id = query.message.message_id
			db = DB()
			sql = "select upper(left(name,1)) as first_letter from nester group by left(name,1)"
			cursor = db.query(sql)
			result = [row[0] for row in cursor.fetchall()]
			keyboard = []
			if len(result) > 0:
				x = 0			
				inline_row = []
				length = len(result)
				for i in range(length):
					dbglog(result[i])
					inline_row.append( InlineKeyboardButton("{}".format(result[i]).capitalize(), callback_data='new2:'+str(result[i]) ) )
					x += 1
					if x > 5:
						keyboard.append(inline_row)
						inline_row = []
						x = 0
					
				if x <= 5:
					keyboard.append(inline_row)
				
				inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
				keyboard.append(inline_cancel_button)
				reply_markup = InlineKeyboardMarkup(keyboard)	
				dbglog(query)
				message_txt = "Welches Nest?"
				bot.edit_message_text(
							message_txt,
							query.message.chat.id,
							msg_id,						
							parse_mode=ParseMode.HTML,
							disable_web_page_preview=True,
							reply_markup=reply_markup)
		
		elif 'change1' in option:
			dbglog("Change1: " + option)
			
			msg_id = query.message.message_id
			place = option.split(':')[1]
			keyboard = []
			
			sql = "select upper(left(pokemon_de.name,1)) as first_letter from nesting_pokemon left join pokemon_de on pokemon_de.name = nesting_pokemon.pokemon where nesting_pokemon.is_nesting=1 AND pokemon_de.name is not null group by left(pokemon_de.name,1)"
			db = DB()
			cursor = db.query(sql)
			result = [row[0] for row in cursor.fetchall()]
			
			if len(result) > 0:
				x = 0			
				inline_row = []
				length = len(result)
				for i in range(length):
					dbglog(result[i])
					inline_row.append( InlineKeyboardButton("{}".format(result[i]).capitalize(), callback_data='change2:'+str(result[i])+':'+place) )
					x += 1
					if x > 5:
						keyboard.append(inline_row)
						inline_row = []
						x = 0
					
				if x <= 5:
					keyboard.append(inline_row)
				
				inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
				keyboard.append(inline_cancel_button)
				reply_markup = InlineKeyboardMarkup(keyboard)	
				dbglog(query)
				final_text = "Welches Pokemon?"
				bot.edit_message_text(
							final_text,
							query.message.chat.id,
							msg_id,						
							parse_mode=ParseMode.HTML,
							reply_markup=reply_markup)
			
		
		elif 'change2' in option:
			dbglog("Change2: " + option)
			place = option.split(':')[1]
			keyboard = []
			
			sql = "select upper(left(pokemon_de.name,1)) as first_letter from nesting_pokemon left join pokemon_de on pokemon_de.name = nesting_pokemon.pokemon where nesting_pokemon.is_nesting=1 AND pokemon_de.name is not null group by left(pokemon_de.name,1)"
			db = DB()
			cursor = db.query(sql)
			result = [row[0] for row in cursor.fetchall()]
			
			if len(result) > 0:
				x = 0			
				inline_row = []
				length = len(result)
				for i in range(length):
					dbglog(result[i])
					inline_row.append( InlineKeyboardButton("{}".format(result[i]).capitalize(), callback_data='change2:'+str(result[i])+':'+place) )
					x += 1
					if x > 5:
						keyboard.append(inline_row)
						inline_row = []
						x = 0
					
				if x <= 5:
					keyboard.append(inline_row)
				
				inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
				keyboard.append(inline_cancel_button)
				reply_markup = InlineKeyboardMarkup(keyboard)	
				dbglog(query)
				bot.edit_message_text(
							query.message.text,
							query.message.chat.id,
							msg_id,						
							parse_mode=ParseMode.HTML,
							disable_web_page_preview=True,
							reply_markup=reply_markup)
		
		elif 'pokemon' in option:
			dbglog("Pokemon: " + option)
			place = option.split(':')[2]
			poke_letter = option.split(':')[1]
			keyboard = []
					
			sql = "SELECT pokemon_de.name, pokemon, is_nesting, is_shiny FROM `nesting_pokemon` left JOIN pokemon_de on pokemon_de.id = pokemon WHERE nesting_pokemon.is_nesting = '1' AND pokemon_de.name LIKE '{}%'".format(poke_letter)
			db = DB()
			cursor = db.query(sql)
			result = cursor.fetchall()
			
			if len(result) > 0:			
				for nest_tuple in result:
					pokemon_data = list(nest_tuple)
					inline_button = []				
					inline_button.append(InlineKeyboardButton("{}".format(pokemon_data[0]).capitalize(), callback_data='pokemon:'+str(pokemon_data[1])+':'+place))	
					keyboard.append(inline_button)
				
				inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
				keyboard.append(inline_cancel_button)
				reply_markup = InlineKeyboardMarkup(keyboard)	
				dbglog(query)
				bot.edit_message_text(
							query.message.text,
							query.message.chat.id,
							msg_id,						
							parse_mode=ParseMode.HTML,
							disable_web_page_preview=True,
							reply_markup=reply_markup)		
	
	if 'nest_switch' in option:
		if 'yes' in option:
			db = DB()			
			logging.info("Nest Switch started by {}".format(str(query.from_user.username)) )
			msg = bot.send_message(
					chat_id=query.message.chat.id,
					text='Nestwechsel gestartet...',				
					message_id=query.message.message_id,
					parse_mode=ParseMode.HTML,
					disable_web_page_preview=True,
					reply_markup=None)
			sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny, prop_id, nester.pokemon from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon"
			cursor = db.query(sql)
			result = cursor.fetchall()
			if len(result) > 0:
				dbglog('Result > 0')
				count_msgs = 0
				for nest_tuple in result:
					nest_data = list(nest_tuple)
					
					sql = "INSERT INTO `nester_history`(`name`, `prop_id`, `pokemon` , `poke_name`, `spawns`, `center_lat`, `center_lon`, `nest_id`) VALUES ('{}','{}','{}','{}','{}','{}','{}','{}')".format(nest_data[0],nest_data[8],nest_data[9],nest_data[2],nest_data[1],nest_data[3],nest_data[4],nest_data[6])
					logging.info("nest_switch - sql: {}".format(sql))
					cursor = db.query(sql)
					db.commit()
					
					nest_data[2] = '-'
					
					size_to_string = ''
					# Größe definition
					if nest_data[1] == 1:
						size_to_string = 'Klein'
					elif nest_data[1] == 2:
						size_to_string = 'Mittel'
					else:
						size_to_string = 'Groß'
						
					final_message = ""
					final_message = final_message + '<b>Ort:</b> <a href="https://maps.google.com/?q=' + "{:.6f}".format(nest_data[3]) + ',' + "{:.6f}".format(nest_data[4]) + '">' + nest_data[0] + '</a>' + "\n"				
					final_message = final_message + '<b>Pokemon:</b> ' + nest_data[2].capitalize() + "\n"
					final_message = final_message + '<b>Größe:</b> ' + size_to_string + "\n" # + str(nest_data[1]) + "\n"
					final_message = final_message + '<i>Aktualisiert: ' + datetime.datetime.now().strftime("%d.%m.%y %H:%M") + '</i> N-ID: ' + str(nest_data[6]) + "\n"
					final_message = final_message + config['MESSAGE']['message_map_link']
										
					if nest_data[5]:
						try:
							bot.edit_message_text(
								final_message,
								group_id,
								nest_data[5],
								parse_mode=ParseMode.HTML,
								disable_web_page_preview=True,
								reply_markup=None)
							count_msgs += 1
							if count_msgs > 15:
								time.sleep(62)
								count_msgs = 0
						except:
							msg = bot.send_message(
								chat_id=group_id,
								text=final_message,				
								message_id=query.message.message_id,
								parse_mode=ParseMode.HTML,
								disable_web_page_preview=True,
								reply_markup=None)
							count_msgs += 1
							if count_msgs > 15:
								time.sleep(62)
								count_msgs = 0
							
							msg_id = msg["message_id"]
							dbglog(msg_id)
							sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
							dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
							cursor = db.query(sql)
							db.commit()
						
					else:
						msg = bot.send_message(
							chat_id=group_id,
							text=final_message,				
							message_id=query.message.message_id,
							disable_web_page_preview=True,
							parse_mode=ParseMode.HTML,
							reply_markup=None)
						count_msgs += 1
						if count_msgs > 15:
							time.sleep(62)
							count_msgs = 0
						
						msg_id = msg["message_id"]
						dbglog(msg_id)
						sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
						dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
						cursor = db.query(sql)
						db.commit()
						
			filename = fileexport()
			bot.send_message(text="Nest Übersicht vom : {}".format(datetime.datetime.now().strftime("%d.%B %Y -- %H:%M")),
				chat_id=query.message.chat.id,
				parse_mode=ParseMode.HTML,
				reply_markup=None)
			bot.send_document(query.message.chat.id, 
				document=open(filename, 'rb'))
			sql = "update nester set pokemon = 0 "
			cursor = db.query(sql)
			db.commit()	
			msg = bot.send_message(
					chat_id=query.message.chat.id,
					text='Nestwechsel durchgeführt!',				
					message_id=query.message.message_id,
					parse_mode=ParseMode.HTML,
					disable_web_page_preview=True,
					reply_markup=None)
			
		else:
			keyboard = [[InlineKeyboardButton("Ja", callback_data=option+':yes')]]
			reply_markup = InlineKeyboardMarkup(keyboard)
			message_txt = "Alle Pokemon Einträge entfernen?"
			bot.edit_message_text(
						message_txt,
						query.message.chat.id,
						msg_id,						
						parse_mode=ParseMode.HTML,
						reply_markup=reply_markup)
	
	# /pokedex change option 
	if 'pokedex' in option:
		poke_number = option.split(':')[1]
		sql = "SELECT id,name,is_shiny,is_nesting from nesting_pokemon left join pokemon_de on pokemon_de.id = nesting_pokemon.pokemon where pokemon = '{}'".format(poke_number)
		dbglog(sql)
		db = DB()	
		cursor = db.query(sql)
		result = cursor.fetchall()
		if len(result) > 0:
			poke_data = list(result[0])
			dbglog(poke_data)
			is_shiny = poke_data[2]
			is_nesting = poke_data[3]
			keyboard = [[
				InlineKeyboardButton(('Shiny' if (not is_shiny) else 'Shiny ✅') , callback_data='chng_shiny:' + poke_number),
				InlineKeyboardButton(('Nest' if (not is_nesting) else 'Nest ✅'), callback_data='chng_nest:' + poke_number)
				],
				[InlineKeyboardButton('Beenden 🔚' , callback_data='save')]]				
			reply_markup = InlineKeyboardMarkup(keyboard)
			dbglog(query)
			message_txt = "Daten für " + poke_data[1]
			bot.edit_message_text(
				message_txt,
				query.message.chat.id,
				msg_id,						
				parse_mode=ParseMode.HTML,
				reply_markup=reply_markup)
	
	if 'chng' in option:
		poke_number = option.split(':')[1]
		sql = "SELECT id,name,is_shiny,is_nesting from nesting_pokemon left join pokemon_de on pokemon_de.id = nesting_pokemon.pokemon where pokemon = '{}'".format(poke_number)
		dbglog(sql)
		db = DB()	
		cursor = db.query(sql)
		result = cursor.fetchall()
		if len(result) > 0:
			poke_data = list(result[0])
			if 'shiny' in option:
				is_shiny = not bool(poke_data[2])
				is_nesting = poke_data[3]
				sql = "UPDATE nesting_pokemon SET is_shiny = '{}' where pokemon = '{}'".format(int(is_shiny),poke_number)
				dbglog(sql)
				cursor = db.query(sql)
				db.commit()
				logging.info("Pokemon {} is_shiny updated by {}".format(poke_number, str(query.from_user.username)) )
			
			if 'nest' in option:
				is_shiny = poke_data[2]
				is_nesting = not bool(poke_data[3])
				sql = "UPDATE nesting_pokemon SET is_nesting = '{}' where pokemon = '{}'".format(int(is_nesting),poke_number)
				logging.info("Pokemon {} is_nesting updated by {}".format(poke_number, str(query.from_user.username)) )
				dbglog(sql)
				cursor = db.query(sql)
				db.commit()
			
			keyboard = [[
				InlineKeyboardButton(('Shiny' if (not is_shiny) else 'Shiny ✅') , callback_data='chng_shiny:' + poke_number),
				InlineKeyboardButton(('Nest' if (not is_nesting) else 'Nest ✅'), callback_data='chng_nest:' + poke_number)
				],
				[InlineKeyboardButton('Beenden 🔚' , callback_data='save')]]
			reply_markup = InlineKeyboardMarkup(keyboard)
			dbglog(query)
			message_txt = "Daten für " + poke_data[1]
			bot.edit_message_text(
				message_txt,
				query.message.chat.id,
				msg_id,						
				parse_mode=ParseMode.HTML,
				reply_markup=reply_markup)
				
	if 'save' in option:
		message_txt = "Gespeichert!"
		bot.edit_message_text(
				message_txt,
				query.message.chat.id,
				msg_id,						
				parse_mode=ParseMode.HTML,
				reply_markup=None)
		return ConversationHandler.END
	
def error(bot, update, error):
	"""Log Errors caused by Updates."""
	logger.warning('Update "%s" caused error "%s"', update, error)

def cancel(bot, update):
	user = update.message.from_user
	logger.info("User %s canceled the conversation.", user.first_name)
	update.message.reply_text('Bye! I hope we can talk again some day.',
							  reply_markup=ReplyKeyboardRemove())

	return ConversationHandler.END

def main():
	# Create the EventHandler and pass it your bot's token.
	updater = Updater(config['TELEGRAM']['bot_api_key'], request_kwargs={'read_timeout': 10, 'connect_timeout': 10})

	# Get the dispatcher to register handlers
	dp = updater.dispatcher

	dp.add_handler(CommandHandler('start', start, Filters.user(admins)))
	dp.add_handler(CallbackQueryHandler(button))
	#dp.add_handler(CommandHandler('help', help))
	dp.add_handler(CommandHandler('init', init, Filters.user(admins)))
	dp.add_handler(CommandHandler('export',export,Filters.user(admins)))
		
	# Add conversation handler with the states POKEMON
	pokedex_handler = ConversationHandler(
		entry_points=[CommandHandler('pokedex', pokedex, Filters.user(admins))],

		states={
			POKEMON: [MessageHandler(Filters.text, pokemon)]
		},

		fallbacks=[CommandHandler('cancel', cancel)],
		allow_reentry=True
	)
	dp.add_handler(pokedex_handler)
	
	dp.add_error_handler(error)
	
	# Start the Bot
	updater.start_polling()
	
	# Run the bot until you press Ctrl-C or the process receives SIGINT,
	# SIGTERM or SIGABRT. This should be used most of the time, since
	# start_polling() is non-blocking and will stop the bot gracefully.
	updater.idle()
		
if __name__ == '__main__':
	main()