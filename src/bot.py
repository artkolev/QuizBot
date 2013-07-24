#!/usr/bin/env python
# -*- coding: utf-8 -*-

import Skype4Py
import datetime
import time
import random
import logging
import sqlite3

from hashlib import sha1
from collections import deque

FORMAT=u'%(name)s %(thread)d  %(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)
logging.getLogger('').setLevel(logging.INFO)
logging.getLogger('app').setLevel(logging.DEBUG)
logging.getLogger('handlers').setLevel(logging.INFO)
logging.getLogger('SkypeMessenger').setLevel(logging.INFO)

log = logging.getLogger('app')

class QuizBot:
    #Инициализация бота
    def __init__(self):
        log.info ("Starting application...")
        #Дефолнтые значения для переменных
        #Дата запуска
        self.start = datetime.datetime.now()
        #Файл с вопросами
        self.bot_db = "QuizBot.db"
        #Разрешенные чаты
        self.listen_chats = [u'рабочие вопросы',
                             u'семейная викторина']
        #период неповторения вопроса
        self.quest_between = "-2 hours"
        #период до второй подсказки (сек)
        self.hint_timeout = 10
        #период до ответа
        self.answer_timeout = 15
        #Бот не остановлен
        self.running = False
        #Активность викторины
        self.listen = []
        #Соединение с БД
        self.db_conn = None
        #Курсор БД
        self.db_cur = None
        #Текущий вопрос
        self.current_question = {}
        #Текущая подсказка
        self.current_hint = {}
        #Текущий ответ
        self.current_answer = {}
        #Проверка от повторений
        self.last_message = {}
        #Полученный контекст
        self.context = ""
        #Очередь задач
        self.stack = deque([])
        #Инстанс скайпа
        self.skype = Skype4Py.Skype()
        #Запущен ли клиент?
        if not self.skype.Client.IsRunning:
            self.skype.Client.Start()
        #Подключение к запущенному скайпу
        self.skype.Attach()
        #Событие приёма сообщения
        self.skype.OnMessageStatus = self.run_action

    def run(self):
        self.running = True
        log.info("Now run!")        
        while self.running:
            try:
                if len(self.stack):
                    action = self.stack.popleft()
                    if action["time"]<=datetime.datetime.now():
                        chat = self.skype.Chat(action["chat"])
                        if chat.Name in self.listen\
                        and chat.Name in self.current_question:
                            hash_key = sha1(u"hash:{0}:{1}".format(
                                self.current_question[chat.Name],
                                self.current_answer[chat.Name])\
                            .encode('utf-8')).hexdigest()
                            if hash_key == action["hash"]:
                                if action["action"] == "answer":
                                    chat.SendMessage(u"Правильный ответ: {0}"\
                                    .format(self.current_answer[chat.Name]))
                                    del(self.current_question[chat.Name])
                                    del(self.current_hint[chat.Name])
                                    del(self.current_answer[chat.Name])
                                    self.stack.append({"time": datetime.datetime.now() +
                                  datetime.timedelta(seconds=2),
                                    "action": 'new_question',
                                    "chat": self.context.Chat.Name})
                                if action["action"] == "hint":
                                    len_answer = \
                                            int(len(self.current_answer[chat.Name]))
                                    len_hint = int(1.5 * len_answer / 4)
                                    hint = u'{}{}{}'.format(
                                    self.current_answer[chat.Name][:len_hint],
                                    '*'*(len_answer-len_hint*2),
                                    self.current_answer[chat.Name][-len_hint:])
                                    chat.SendMessage(u"Подсказка: {0}"\
                                    .format(hint))
                        else:
                            if action["action"] == "new_question":
                                self.new_question()
                    else:
                        self.stack.append(action)
                time.sleep(0.5)
            except KeyboardInterrupt:
                self.shutdown()

    def shutdown(self):
        log.debug("Disconnecting...")
        self.stop_quiz()
        log.info("Now shutdown...")
        if self.db_conn and self.db_cur:
            self.db_disconnect()
        self.running = False
        work_time = datetime.datetime.now() - self.start
        log.info("Work time: %s" % work_time)
        return True

    def db_connect(self):
        if not self.db_conn and not self.db_cur:
            log.debug("Connect to database...")
            self.db_conn = sqlite3.connect(self.bot_db)
            log.debug("Get cursor")
            self.db_cur = self.db_conn.cursor()
        else:
            log.error("Database connect already exits...")
    
    def db_disconnect(self):
        if self.db_conn and self.db_cur:
            log.debug("Commit to database...")
            self.db_conn.commit()
            log.debug("Close connection...")
            self.db_conn.close()
            self.db_cur = None
            self.db_conn = None
        else:
            log.error("No database connect...")

    def run_action(self, message, status):
        if message.Chat.FriendlyName.lower() in self.listen_chats and \
        not (message.Sender.Handle in self.last_message and\
        self.last_message[message.Sender.Handle] == message.Body) and \
        (status == 'SENT' or status == 'RECEIVED'):
            log.info(u"Action: '{0}' Message: '{1} ({2}): {3}'".format(status,
                                                      message.Sender.Handle,
                                                      message.Chat.FriendlyName,
                                                      message.Body))            
            self.last_message[message.Sender.Handle] = message.Body
            command = message.Body.split(' ')[0].lower()
            if command in self.functions:
                self.context = message
                self.functions[command](self)
            elif self.context.Chat.Name in self.listen:
                self.parse_answer(message)
        else:
            log.debug(u"Action: '{0}' Message: '{1} ({2}): {3}'".format(status,
                                                    message.Sender.Handle,
                                                    message.Chat.FriendlyName,
                                                    message.Body))

    def new_question(self):
        self.db_connect()
        new_quest = self.db_cur.execute("""SELECT question, answer
                          FROM questions
                          WHERE last_show < strftime('%s','now','{0}')
                          ORDER BY RANDOM()
                          LIMIT 1""".format(self.quest_between)).fetchone()
        if new_quest:
            self.current_question[self.context.Chat.Name] = new_quest[0]
            self.current_answer[self.context.Chat.Name] = new_quest[1]
            hint = u'{}{}{}'.format(new_quest[1][0],
                                    '*'*(len(new_quest[1])-2),
                                    new_quest[1][-1])
            self.current_hint[self.context.Chat.Name] = hint
            self.context.Chat.SendMessage(u'Новый вопрос: {}'.format(new_quest[0]))
            time.sleep(0.5)
            self.context.Chat.SendMessage(u'/me Подсказка: {}'.format(hint))
            self.db_cur.execute(u"""UPDATE questions
                                    SET last_show = strftime('%s','now')
                                    WHERE question = '{0}'
                                    AND answer = '{1}'""".format(
                                                                 new_quest[0],
                                                                 new_quest[1]))
            hash_key = sha1(u"hash:{0}:{1}".format(new_quest[0],new_quest[1])\
                            .encode('utf-8')).hexdigest()
                              
            self.stack.append({"time": datetime.datetime.now() +
                               datetime.timedelta(seconds=self.hint_timeout),
                               "action": 'hint',
                               "chat": self.context.Chat.Name,
                               "hash": hash_key})
            self.stack.append({"time": datetime.datetime.now() +
                               datetime.timedelta(seconds=self.answer_timeout),
                               "action": 'answer',
                               "chat": self.context.Chat.Name,
                               "hash": hash_key})
        else:
            self.context.Chat.SendMessage(u'Вопросы кончились.')
            self.stop_quiz()
        self.db_disconnect()

    def start_quiz(self):
        if not self.context.Chat.Name in self.listen:
            log.info("Starting quiz...")
            self.context.Chat.SendMessage(u'/me Запускаем викторину!')
            self.db_connect()
            count_quest = self.db_cur.execute("SELECT COUNT(*) FROM questions")\
            .fetchone()
            self.db_disconnect()
            if count_quest:
                self.listen.append(self.context.Chat.Name)
                self.context.Chat.SendMessage(u'/me Вопросы загружены. В базе \
%s вопросов' % count_quest)
                self.stack.append({"time": datetime.datetime.now(),
                                    "action": 'new_question',
                                    "chat": self.context.Chat.Name})
            else:
                self.context.Chat.SendMessage(u'/me Вопросов в базе не найдено')
        else:
            self.context.Chat.SendMessage(u'Викторина уже запущена!!! \
Не стоит паниковать.')

    def stop_quiz(self):
        if self.listen:
            log.info("Stoping quiz...")
            self.listen = []
            self.context.Chat.SendMessage(u'/me Викторина остановлена!')

    def parse_answer(self, message):
        if self.context.Chat.Name in self.listen\
        and message.Chat.Name in self.current_answer \
        and message.Body.lower() == self.current_answer[message.Chat.Name].lower():
            self.listen.remove(self.context.Chat.Name)
            del(self.current_question[self.context.Chat.Name])
            del(self.current_hint[self.context.Chat.Name])
            log.info(u"Correct answer '{0}' from user {1}'".format(message.Body,
                                                         message.Sender.Handle))
            self.db_connect()
            user_points = self.db_cur.execute("""SELECT points
                                                 FROM leaders
                                                 WHERE name = '{0}'
                                                 AND chat = '{1}'"""\
                          .format(message.Sender.Handle,
                                  message.Chat.Name)).fetchone()
            if user_points and user_points[0]:
                user_points = int(user_points[0]) + 1
                message.Chat.SendMessage(u"/me {0}, правильно!!! Ответ '{1}'. У тебя {2} очков."\
                                         .format(message.Sender.Handle,
                                         self.current_answer[message.Chat.Name],
                                         user_points))
                del(self.current_answer[self.context.Chat.Name])
                self.db_cur.execute("""UPDATE leaders
                                       SET points = {0}
                                       WHERE name = '{1}'
                                       AND chat = '{2}'""".format(user_points,
                                                          message.Sender.Handle,
                                                          message.Chat.Name))
            else:
                user_points = 1
                message.Chat.SendMessage(u"/me {0}, правильно!!! Ответ '{1}'. У тебя первое очко."\
                                        .format(message.Sender.Handle,
                                        self.current_answer[message.Chat.Name]))
                self.db_cur.execute("""INSERT INTO leaders(name, points, chat)
                                       VALUES ('{0}', 1, '{1}')"""\
                                       .format(message.Sender.Handle,
                                               message.Chat.Name))
            self.db_disconnect()
            self.listen.append(self.context.Chat.Name)
            self.stack.append({"time": datetime.datetime.now(),
                               "action": 'new_question',
                               "chat": self.context.Chat.Name})

    def next_answer(self):
        if self.context.Chat.Name in self.listen\
        and self.context.Chat.Name in self.current_answer:
            log.info(u"Next answer from user {0}'".format(self.context.Sender\
                                                         .Handle))
            self.context.Chat.SendMessage(
            u"/me Пользователь {0} пропустил вопрос. Правильный ответ был '{1}'"\
            .format(self.context.Sender.Handle,
                    self.current_answer[self.context.Chat.Name]))
            del(self.current_question[self.context.Chat.Name])
            del(self.current_hint[self.context.Chat.Name])
            del(self.current_answer[self.context.Chat.Name])
            self.stack.append({"time": datetime.datetime.now() +
                                       datetime.timedelta(seconds=2),
                               "action": 'new_question',
                               "chat": self.context.Chat.Name})

    def show_hint(self):
        if self.context.Chat.Name in self.listen:
            self.context.Chat.SendMessage(u'/me Подсказка: {0}'.format(
                self.current_hint[self.context.Chat.Name]))
   
    def show_top10(self):
        self.db_connect()
        leaderboard = self.db_cur.execute("""SELECT name, points
                                             FROM leaders
                                             WHERE chat = '{0}'
                                             ORDER BY points DESC
                                             LIMIT 0,10"""\
                      .format(self.context.Chat.Name)).fetchall()
        if len(leaderboard):
            self.context.Chat.SendMessage(u"Топ-10 лидеров:")
            time.sleep(1)
            i = 1
            for name, points in leaderboard:
                self.context.Chat.SendMessage(u"/me {0}. {1} - {2}"\
                                              .format(i, name, points))
                i+=1
                time.sleep(0.5)
            i = None
        else:
            self.context.Chat.SendMessage(u"/me Лидеров еще нет")
        self.db_disconnect()
    

    #Допустимые комманды
    functions = {"!start": start_quiz,
                 u"!старт": start_quiz,
                 "!stop": stop_quiz,
                 u"!стоп": stop_quiz,
                 "!next": next_answer,
                 u"!далее": next_answer,
                 "!hint": show_hint,
                 u"!подсказка": show_hint,
                 "!top": show_top10,
                 u"!топ": show_top10,
                 }

if __name__ == "__main__":
    quiz_cis = QuizBot()
    quiz_cis.run()

