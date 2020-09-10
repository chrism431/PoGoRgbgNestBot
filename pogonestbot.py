#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PogoRgbgNEST Bot

Copyright (C) 2020  @ChrisM431 (Telegram)
"""
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

# pylint: disable=line-too-long,bad-continuation,global-statement

## Imports
import datetime
import sched
import time
import threading
import csv
import json
import configparser
import logging
import MySQLdb

from math import cos, sin, asin, sqrt
from uuid import uuid4

from telegram.utils.helpers import escape_markdown
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup,
                          ParseMode, InlineKeyboardButton)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler, InlineQueryHandler, CallbackQueryHandler)
from telegram.ext.dispatcher import run_async

from telegram.error import (TelegramError, Unauthorized, BadRequest,
                            TimedOut, ChatMigrated, NetworkError)

## Constants ##
CONFIG_NAME = 'pogonestbot.ini'
## --------- ##

# Init ConfigParser
config = configparser.ConfigParser()
config.read(CONFIG_NAME)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    filename=config['SYSTEM']['sys_log_dir'])

logger = logging.getLogger(__name__)

"""Print Debug Logging"""
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
    logging.info('Bot started by %s', str(update.message.from_user.username))
    keyboard = [[InlineKeyboardButton("Neuer Eintrag", callback_data='new'),
                 InlineKeyboardButton("Liste", callback_data='list')],
                 [InlineKeyboardButton("Nestwechsel", callback_data='nest_switch')]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    bot.send_message(text=config['MESSAGE']['message_disclaimer'],
        chat_id=update.message.chat_id,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup)

def fileexport():
    """    Fileexport Handler
        Write Database content to csv file"""
    db = DB()
    sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon"
    cursor = db.query(sql)
    filename = "{}{}.csv".format(config['SYSTEM']['sys_export_dir'], datetime.datetime.now().strftime("%d-%B-%Y"))
    with open(filename, "w", newline='') as csv_file:
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([i[0] for i in cursor.description]) # write headers
        csv_writer.writerows(cursor)
    return filename

def export(bot, update):
    """/export Command Handler"""
    filename = fileexport()
    bot.send_message(text="Nest Übersicht vom : {}".format(datetime.datetime.now().strftime("%d.%B %Y -- %H:%M")),
        chat_id=update.message.chat_id,
        parse_mode=ParseMode.HTML,
        reply_markup=None)
    bot.send_document(chat_id=update.message.chat_id,
        document=open(filename, 'rb'))

def migration_message(bot, args):
    """Post migration overview to end of group"""
    if not args:
        db = DB()
        sql = "SELECT * FROM `nest_migration` order by id desc limit 1"
        cursor = db.query(sql)
        result = cursor.fetchall()[0]
        if len(result) > 0:
            nest_migration_id = result[0]
            nest_migration = str(result[1])
            nest_link = result[2]
            nest_migration_date = result[3]
            old_msg_id = result[4]

            # Pokemon to add Hashtags
            sql = "select pokemon_de.name from nester left join pokemon_de on pokemon_de.id=nester.pokemon where nester.pokemon > 0 group by pokemon"
            cursor = db.query(sql)
            result = cursor.fetchall()
            hashtag_string = ""
            for pokemon in result:
                hashtag_string = hashtag_string + '#' + pokemon[0] + '  '

            final_message = ""
            final_message = final_message + '<b>Nächster Nestwechsel (#' + nest_migration + ') :</b> ' + nest_migration_date.strftime("%d.%m.%y %H:%M") + " Uhr" + "\n"
            final_message = final_message + '<a href="' + nest_link + '">&#8204;</a>' + "\n"
            final_message = final_message + '<b>Gemeldete Pokemon:</b> ' + "\n"
            final_message = final_message + hashtag_string + "\n\n"
            final_message = final_message + '<i>Aktualisiert: ' + datetime.datetime.now().strftime("%d.%m.%y %H:%M") + '</i>' + "\n"
            final_message = final_message + config['MESSAGE']['message_map_link']
            #logging.info(final_message)

            msg_id = None
            if old_msg_id:
                logging.info('Old Message_Id: %s', str(old_msg_id))
                try:
                    bot.delete_message(
                        chat_id=group_id,
                        message_id=old_msg_id)

                    msg = bot.send_message(
                        chat_id=group_id,
                        text=final_message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                        reply_markup=None)

                    msg_id = msg["message_id"]
                    #dbglog(msg_id)
                    sql = "update `nest_migration` set msg_id = {} where id = '{}'".format(msg_id,nest_migration_id)
                    logging.info(sql)
                    cursor = db.query(sql)
                    db.commit()

                except TelegramError as error:
                    logging.info(error)
                    msg = bot.send_message(
                        chat_id=group_id,
                        text=final_message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                        reply_markup=None)

                    msg_id = msg["message_id"]
                    #dbglog(msg_id)
                    sql = "update `nest_migration` set msg_id = {} where id = '{}'".format(msg_id,nest_migration_id)
                    logging.info(sql)
                    cursor = db.query(sql)
                    db.commit()
            else:
                msg = bot.send_message(
                    # chat_id=update.message.chat_id,
                    chat_id=group_id,
                    text=final_message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                    reply_markup=None)

                msg_id = msg["message_id"]
                #dbglog(msg_id)
                sql = "update `nest_migration` set msg_id = {} where id = '{}'".format(msg_id,nest_migration_id)
                logging.info(sql)
                cursor = db.query(sql)
                db.commit()

            logging.info('Message_Id to pin: %s', str(msg_id))
            bot.pin_chat_message(
                chat_id=group_id,
                message_id=msg_id,
                disable_notification=None,
                timeout=None)
            #logging.info('migration message posted')
    else:
        db = DB()
        logging.info(args)
        migration_id = args[0]
        link = args[1]
        next_date = "{} {}".format(args[2],args[3])
        # Get old nest_message to grab msg_id
        sql = "SELECT * FROM `nest_migration` order by id desc limit 1"
        cursor = db.query(sql)
        result = cursor.fetchall()[0]
        old_msg_id = None
        if len(result) > 0:
            old_msg_id = result[4]

        sql = "INSERT INTO `nest_migration`(`nest_migration`, `nest_overview_link`, `next_migration`, `msg_id`) VALUES ('{}','{}','{}','{}')".format(migration_id, link, next_date,old_msg_id)
        cursor = db.query(sql)
        db.commit()
        migration_message(bot, None)

def remove_service_pin_message(bot, update):
    update.message.delete()

def build_nest_message(lat, lon, name, pokemon, is_shiny, nest_id, nest_size):
    # Nest size
    if nest_size == 1:
        size_to_string = 'Klein'
    elif nest_size == 2:
        size_to_string = 'Mittel'
    else:
        size_to_string = 'Groß'

    final_message = ""
    final_message = final_message + '<b>Ort:</b> <a href="https://maps.google.com/?q=' + "{:.6f}".format(lat) + ',' + "{:.6f}".format(lon) + '">' + name + '</a>' + "\n"
    final_message = final_message + '<b>Pokemon:</b> ' + pokemon.capitalize() + ('' if (not is_shiny) else ' ✨') + "\n"
    final_message = final_message + '<b>Größe:</b> ' + size_to_string + "\n" # + size_to_string + "\n" # + str(nest_data[1]) + "\n"
    final_message = final_message + '<i>Aktualisiert: ' + datetime.datetime.now().strftime("%d.%m.%y %H:%M") + '</i> N-ID: ' + str(nest_id) + "\n"
    final_message = final_message + config['MESSAGE']['message_map_link'] + "\n"
    final_message = final_message + '#' + pokemon.capitalize()
    return final_message


"""Perform nest switch"""
def do_nest_switch(bot, from_user, query):
    db = DB()
    if from_user:
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
        count_msgs = 0
        for nest_tuple in result:
            nest_data = list(nest_tuple)

            sql = "INSERT INTO `nester_history`(`name`, `prop_id`, `pokemon` , `poke_name`, `spawns`, `center_lat`, `center_lon`, `nest_id`) VALUES ('{}','{}','{}','{}','{}','{}','{}','{}')".format(nest_data[0],nest_data[8],nest_data[9],nest_data[2],nest_data[1],nest_data[3],nest_data[4],nest_data[6])
            logging.info("nest_switch - sql: {}".format(sql))
            cursor = db.query(sql)
            db.commit()

            nest_data[2] = '-'

            final_message = build_nest_message(nest_data[3],nest_data[4],nest_data[0],nest_data[2],nest_data[7],nest_data[6],nest_data[1])

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
                    if count_msgs > 18:
                        time.sleep(62)
                        count_msgs = 0
                except TelegramError:
                    msg = bot.send_message(
                        chat_id=group_id,
                        text=final_message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=None)
                    count_msgs += 1
                    if count_msgs > 18:
                        time.sleep(62)
                        count_msgs = 0

                    msg_id = msg["message_id"]
                    sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
                    cursor = db.query(sql)
                    db.commit()

            else:
                msg = bot.send_message(
                    chat_id=group_id,
                    text=final_message,
                    disable_web_page_preview=True,
                    parse_mode=ParseMode.HTML,
                    reply_markup=None)
                count_msgs += 1
                if count_msgs > 18:
                    time.sleep(62)
                    count_msgs = 0

                msg_id = msg["message_id"]
                sql = "update nester set msg_id = {} where name = '{}'".format(msg_id,nest_data[0])
                cursor = db.query(sql)
                db.commit()
    if from_user:
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

    migration_message(bot, None)
    if from_user:
        msg = bot.bot.send_message(
                chat_id=query.message.chat.id,
                text='Nestwechsel durchgeführt!',
                message_id=query.message.message_id,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=None)

def init(bot, update):
    """    /init Command Handler
        Init the basis functionality such as checking for all messages in the group"""
    query = update.callback_query
    #dbglog("Init started...")
    bot.send_message(text="Initialisierung/Update gestartet...",
        chat_id=update.message.chat_id,
        parse_mode=ParseMode.HTML,
        reply_markup=None)
    logging.info('Init started by %s', str(update.message.from_user.username))
    db = DB()
    sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon"
    cursor = db.query(sql)
    result = cursor.fetchall()
    if len(result) > 0:
        #dbglog('Result > 0')
        count_msgs = 0
        for nest_tuple in result:
            nest_data = list(nest_tuple)
            if not nest_data[2]:
                nest_data[2] = '-'
            compare = 'Missigno.'
            if nest_data[2] == compare:
                nest_data[2] = '-'

            final_message = build_nest_message(nest_data[3], nest_data[4], nest_data[0], nest_data[2], nest_data[7], nest_data[6], nest_data[1])

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
                except TelegramError:
                    msg = bot.send_message(
                        chat_id=group_id,
                        text=final_message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=None)
                    count_msgs += 1
                    if count_msgs > 15:
                        time.sleep(62)
                        count_msgs = 0

                    msg_id = msg["message_id"]
                    #dbglog(msg_id)
                    sql = "update nester set msg_id = {} where name = '{}'".format(msg_id, nest_data[0])
                    #dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
                    cursor = db.query(sql)
                    db.commit()
            else:
                msg = bot.send_message(
                    chat_id=group_id,
                    text=final_message,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=None)
                count_msgs += 1
                if count_msgs > 15:
                    time.sleep(62)
                    count_msgs = 0

                msg_id = msg["message_id"]
                #dbglog(msg_id)
                sql = "update nester set msg_id = {} where name = '{}'".format(msg_id, nest_data[0])
                #dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
                cursor = db.query(sql)
                db.commit()
    #dbglog("Done!")
    bot.send_message(text="Initialisierung/Update abgeschlossen!",
        chat_id=update.message.chat_id,
        parse_mode=ParseMode.HTML,
        reply_markup=None)
    logging.info('Init finished')
    migration_message(bot, None)
    logging.info('Migration Message posted')

# Change Pokemon's nesting and shiny state
def pokedex(bot, update):
    """/pokedex Handler
    Ask for Pokemon's name"""
    update.message.reply_text(
        'Welches Pokemon soll verändert werden?',
        reply_markup=None)
    return POKEMON

def pokemon(bot, update):
    """/pokemon Handler
    Edit Pokemon's state in DB"""
    query = update.callback_query
    pokemon = update.message.text
    #dbglog(pokemon)
    sql = "SELECT name,id FROM `pokemon_de` WHERE lower(`name`) like '{}%' or lower(`name`) like '%{}%'".format(pokemon.lower(),pokemon.lower())
    #dbglog(sql)
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
    """Global InlineButton Handler"""
    query = update.callback_query
    option = query.data
    msg_id = query.message.message_id
    #dbglog(query.message.message_id)
    #dbglog("Option: " + option)

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
                #dbglog(result[i])
                inline_row.append(InlineKeyboardButton(" {} ".format(result[i]).upper(), callback_data='new2:'+str(result[i]) ) )
                x += 1
                if x > 4:
                    keyboard.append(inline_row)
                    inline_row = []
                    x = 0

            if x <= 4:
                keyboard.append(inline_row)

            inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
            keyboard.append(inline_cancel_button)
            reply_markup = InlineKeyboardMarkup(keyboard)
            #dbglog(query)
            message_txt = "Welches Nest soll verändert werden?"
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
            ##dbglog(query)
            bot.edit_message_text(
                        query.message.text,
                        query.message.chat.id,
                        msg_id,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup)

    if option == 'list':
        db = DB()
        sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.id, nester.msg_id from nester left join pokemon_de on pokemon_de.id=nester.pokemon"
        #dbglog(sql)
        cursor = db.query(sql)
        result = cursor.fetchall()

        if len(result) > 0:
            for nest_tuple in result:
                nest_data = list(nest_tuple)
                #dbglog(nest_data)
                if not nest_data[2]:
                #    continue
                    nest_data[2] = '-'
                compare = 'Missigno.'
                if nest_data[2] == compare:
                    nest_data[2] = '-'

                final_message = build_nest_message(nest_data[3], nest_data[4], nest_data[0], nest_data[2], nest_data[7], nest_data[6], nest_data[1])

                keyboard2 = [[InlineKeyboardButton("Ändern", callback_data='change1:'+nest_data[0])]]
                reply_markup2 = InlineKeyboardMarkup(keyboard2)

                msg = bot.send_message(
                    chat_id=query.message.chat_id,
                    text=final_message,
                    message_id=query.message.message_id,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=reply_markup2)

                #dbglog(msg)
                #dbglog(msg["message_id"])

    if 'change1' in option:
        place = option.split(':')[1]
        keyboard = []

        sql = "SELECT UPPER(LEFT(pokemon_de.name,1)) as first_letter FROM `nesting_pokemon` LEFT JOIN `pokemon_de` ON pokemon_de.id = `nesting_pokemon`.`pokemon` WHERE `is_nesting` = '1' AND pokemon_de.name IS NOT NULL GROUP BY LEFT(pokemon_de.name,1)"
        db = DB()
        cursor = db.query(sql)
        result = [row[0] for row in cursor.fetchall()]

        # Already existing nest?
        sql = "SELECT pokemon_de.name from nester LEFT JOIN `pokemon_de` ON pokemon_de.id = `nester`.`pokemon` where nester.`name`='" + place +"'"
        db = DB()
        cursor = db.query(sql)
        result_1 = [row[0] for row in cursor.fetchall()]
        nest_text = " <b>" + place + "</b>?"
        if (len(result_1) > 0 and result_1[0] is not None):
            nest_text = nest_text + "\nPokemon im Nest: <b>" + result_1[0] + "</b>"

        if len(result) > 0:
            x = 0
            inline_row = []
            length = len(result)
            for i in range(length):
                ##dbglog(result[i])
                inline_row.append(InlineKeyboardButton(" {} ".format(result[i]).upper(), callback_data='change2:'+str(result[i])+':'+place) )
                x += 1
                if x > 4:
                    keyboard.append(inline_row)
                    inline_row = []
                    x = 0

            if x <= 4:
                keyboard.append(inline_row)

            inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>'+option)]
            keyboard.append(inline_cancel_button)
            reply_markup = InlineKeyboardMarkup(keyboard)
            #dbglog(query)
            final_text = "Welches Pokemon ist im Nest" + nest_text
            bot.edit_message_text(
                        final_text,
                        query.message.chat.id,
                        msg_id,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup)

    if  'change2' in option:
        #dbglog(option)
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
            #dbglog(query)
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
        sql = "update nester set pokemon = {} where name = '{}'".format(new_pokemon, place)
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


        final_message = build_nest_message(nest_data[3], nest_data[4], nest_data[0], nest_data[2], nest_data[7], nest_data[6], nest_data[1])

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
                #dbglog(msg_id)
                sql = "update nester set msg_id = {} where name = '{}'".format(msg_id, nest_data[0])
                #dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
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
            #dbglog(msg_id)
            sql = "update nester set msg_id = {} where name = '{}'".format(msg_id, nest_data[0])
            #dbglog(datetime.datetime.now().strftime("%H:%M") + sql)
            cursor = db.query(sql)
            db.commit()
        logging.info("Nest {} updated by {}".format(nest_data[0], str(query.from_user.username)))
        migration_message(bot, None)

    if 'cancel' in option:
        option = option.split('>')[1]
        #dbglog("Cancel_Option: " + option)
        if option == 'new':
            keyboard = [[InlineKeyboardButton("Neuer Eintrag", callback_data='new'),
                 InlineKeyboardButton("Liste", callback_data='list')],
                 [InlineKeyboardButton("Nestwechsel", callback_data='nest_switch')]]

            reply_markup = InlineKeyboardMarkup(keyboard)

            bot.edit_message_text(
                    config['MESSAGE']['message_disclaimer'],
                    query.message.chat.id,
                    msg_id,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup)
            return ConversationHandler.END

        elif 'new2' in option:
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
                    #dbglog(result[i])
                    inline_row.append(InlineKeyboardButton(" {} ".format(result[i]).upper(), callback_data='new2:'+str(result[i]) ) )
                    x += 1
                    if x > 4:
                        keyboard.append(inline_row)
                        inline_row = []
                        x = 0

                if x <= 4:
                    keyboard.append(inline_row)

                inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>new')]
                keyboard.append(inline_cancel_button)
                reply_markup = InlineKeyboardMarkup(keyboard)
                #dbglog(query)
                message_txt = "Welches Nest soll verändert werden?"
                bot.edit_message_text(
                            message_txt,
                            query.message.chat.id,
                            msg_id,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                            reply_markup=reply_markup)

        elif 'change1' in option:
            #dbglog("Change1: " + option)
            msg_id = query.message.message_id

            option_nest = option.split(':')[1]
            nest_first_letter = option_nest[0]
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

                inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>new2:'+option_nest)]
                keyboard.append(inline_cancel_button)
                reply_markup = InlineKeyboardMarkup(keyboard)
                ##dbglog(query)
                message_txt = "Welches Nest soll verändert werden?"
                bot.edit_message_text(
                            message_txt,
                            query.message.chat.id,
                            msg_id,
                            parse_mode=ParseMode.HTML,
                            reply_markup=reply_markup)


        elif 'change2' in option:
            #dbglog("Change2: " + option)
            place = option.split(':')[2]
            poke_letter = option.split(':')[1]
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
                    #dbglog(result[i])
                    inline_row.append(InlineKeyboardButton("{}".format(result[i]).capitalize(), callback_data='change2:'+str(result[i])+':'+place) )
                    x += 1
                    if x > 4:
                        keyboard.append(inline_row)
                        inline_row = []
                        x = 0

                if x <= 4:
                    keyboard.append(inline_row)

                inline_cancel_button = [InlineKeyboardButton("Abbrechen", callback_data='cancel>change1:'+place)]
                keyboard.append(inline_cancel_button)
                reply_markup = InlineKeyboardMarkup(keyboard)
                #dbglog(query)
                bot.edit_message_text(
                            query.message.text,
                            query.message.chat.id,
                            msg_id,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                            reply_markup=reply_markup)

    if 'nest_switch' in option:
        if 'yes' in option:
            do_nest_switch(bot, True, query)

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
        #dbglog(sql)
        db = DB()
        cursor = db.query(sql)
        result = cursor.fetchall()
        if len(result) > 0:
            poke_data = list(result[0])
            #dbglog(poke_data)
            is_shiny = poke_data[2]
            is_nesting = poke_data[3]
            keyboard = [[
                InlineKeyboardButton(('Shiny' if (not is_shiny) else 'Shiny ✅'), callback_data='chng_shiny:' + poke_number),
                InlineKeyboardButton(('Nest' if (not is_nesting) else 'Nest ✅'), callback_data='chng_nest:' + poke_number)
                ],
                [InlineKeyboardButton('Beenden 🔚', callback_data='save')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            #dbglog(query)
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
        #dbglog(sql)
        db = DB()
        cursor = db.query(sql)
        result = cursor.fetchall()
        if len(result) > 0:
            poke_data = list(result[0])
            if 'shiny' in option:
                is_shiny = not bool(poke_data[2])
                is_nesting = poke_data[3]
                sql = "UPDATE nesting_pokemon SET is_shiny = '{}' where pokemon = '{}'".format(int(is_shiny),poke_number)
                #dbglog(sql)
                cursor = db.query(sql)
                db.commit()
                logging.info("Pokemon {} is_shiny updated by {}".format(poke_number, str(query.from_user.username)) )

                # CHANGE NESTS WITH POKEMON
                # SQL QUERY GET ALL NESTS
                sql = "select nester.name, nester.spawns, pokemon_de.name, center_lat as lat, center_lon as lon, nester.msg_id, nester.id, nesting_pokemon.is_shiny from nester left join pokemon_de on pokemon_de.id=nester.pokemon left join nesting_pokemon on nesting_pokemon.pokemon = nester.pokemon where nester.pokemon={}".format(poke_number)
                cursor = db.query(sql)
                cursor.execute(sql)
                nests_tuples = cursor.fetchall()
                # FOR EVERY ENTRY
                for nest_tuple in nests_tuples:
                    # CHANGE ENTRY MESSAGE
                    nest_data = list(nest_tuple)
                    if not nest_data[2]:
                        nest_data[2] = '-'
                    compare = 'Missigno.'
                    if nest_data[2] == compare:
                        nest_data[2] = '-'

                    final_message = build_nest_message(nest_data[3],nest_data[4],nest_data[0],nest_data[2],nest_data[7],nest_data[6],nest_data[1])

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
                            dbglog("Nest {} konnte nicht editiert werden! (Msg-ID:{})".format(nest_data[0], nest_data[5]))


            if 'nest' in option:
                is_shiny = poke_data[2]
                is_nesting = not bool(poke_data[3])
                sql = "UPDATE nesting_pokemon SET is_nesting = '{}' where pokemon = '{}'".format(int(is_nesting),poke_number)
                logging.info("Pokemon {} is_nesting updated by {}".format(poke_number, str(query.from_user.username)) )
                #dbglog(sql)
                cursor = db.query(sql)
                db.commit()

            keyboard = [[
                InlineKeyboardButton(('Shiny' if (not is_shiny) else 'Shiny ✅'), callback_data='chng_shiny:' + poke_number),
                InlineKeyboardButton(('Nest' if (not is_nesting) else 'Nest ✅'), callback_data='chng_nest:' + poke_number)
                ],
                [InlineKeyboardButton('Beenden 🔚', callback_data='save')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            #dbglog(query)
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
    """/cancel Command Handler"""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text('Bye! I hope we can talk again some day.',
                              reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END

class nest_migration_handler(threading.Thread):
    def __init__ (self, bot):
        threading.Thread.__init__(self)
        self.__migration_overdue = False
        self.__bot = bot
    def run(self):
        while True:
            # read next scheduled date
            sql = "SELECT * FROM `nest_migration` WHERE NOW() < next_migration"
            db = DB()
            cursor = db.query(sql)
            result = cursor.fetchall()
            if len(result) > 0:
                # Wait for a bunch of time to re-check
                #logger.info("no new migration")
                threading.Event().wait(3600)
            else:
                # start migration
                # post new message
                logger.info("New migration scheduled!")
                do_nest_switch(self.__bot, False, None)

                # Get old nest_message to grab msg_id
                sql = "SELECT * FROM `nest_migration` order by id desc limit 1"
                cursor = db.query(sql)
                result = cursor.fetchall()[0]
                if result is not None:
                    migration_id = result[1] + 1
                    link = result[2]
                    date_format = "%Y-%m-%d %H:%M:%S"
                    current_date_str = "{}".format(result[3])
                    current_date = datetime.datetime.strptime(current_date_str, date_format)
                    next_date = current_date + datetime.timedelta(days=14)
                    next_date_str = next_date.strftime(date_format)

                    """migration_id = args[0]
                    link = args[1]
                    next_date = "{} {}".format(args[2],args[3])"""
                    migration_message(self.__bot, (migration_id, link, next_date_str.split(" ")[0], next_date_str.split(" ")[1]))

                threading.Event().wait(3600)


def main():
    """main"""
    # Create the EventHandler and pass it your bot's token.
    updater = Updater(config['TELEGRAM']['bot_api_key'], request_kwargs={'read_timeout': 10, 'connect_timeout': 10})

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start, Filters.user(admins)))
    dp.add_handler(CallbackQueryHandler(button))
    #dp.add_handler(CommandHandler('help', help))
    dp.add_handler(CommandHandler('init', init, Filters.user(admins)))
    dp.add_handler(CommandHandler('export', export, Filters.user(admins)))
    dp.add_handler(CommandHandler('migrate', migration_message, Filters.user(admins), pass_args=True))

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

    # Remove Service Message 'pinned_message'
    dp.add_handler(MessageHandler(Filters.status_update.pinned_message, remove_service_pin_message))

    # Start the Bot
    updater.start_polling()

    # Check for planned Nest Migrations
    _migration_handler = nest_migration_handler(updater.bot)
    _migration_handler.daemon = True
    _migration_handler.start()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()
