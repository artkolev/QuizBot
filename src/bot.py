#!/usr/bin/env python
# -*- coding: utf-8 -*-

import Skype4Py
import datetime
import time
import random
import logging
import sqlite3

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
        #Бот не остановлен
        self.running = False
        #Файл с вопросами
        self.bot_db = "QuizBot.db"
        #Разрешенные чаты
        self.listen_chats = [u'рабочие вопросы',
                             u'ирина миндерова | ту']
        #период неповторения вопроса
        self.quest_between = "-2 hours"
        #Активность викторины
        self.listen = False
        #Соединение с БД
        self.db_conn = None
        #Курсор БД
        self.db_cur = None
        #Текущий вопрос
        self.current_question = ""
        #Текущая подсказка
        self.current_hint = ""
        #Текущий ответ
        self.current_answer = ""
        #Проверка от повторений
        self.last_message = {}
        #Полученный контекст
        self.context = ""
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
        log.info("Starting application...")
        self.running = True
        log.info("Now run!")        
        while self.running:
            try:
                time.sleep (0.1)
            except KeyboardInterrupt:
                self.shutdown()

    def shutdown(self):
        log.info("Disconnecting...")
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
            log.info("Connect to database...")
            self.db_conn = sqlite3.connect(self.bot_db)
            log.info("Get cursor")
            self.db_cur = self.db_conn.cursor()
        else:
            log.error("Database connect already exits...")
    
    def db_disconnect(self):
        if self.db_conn and self.db_cur:
            log.info("Commit to database...")
            self.db_conn.commit()
            log.info("Close connection...")
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
            elif self.listen:
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
            self.current_question = new_quest[0]
            self.current_answer = new_quest[1]
            self.current_hint = u'{}{}{}'.format(self.current_answer[0],
                                               '*'*(len(self.current_answer)-2),
                                                self.current_answer[-1])
            self.context.Chat.SendMessage(u'Новый вопрос: %s' %
                                          self.current_question)
            self.context.Chat.SendMessage(u'/me Подсказка: %s' %
                                          self.current_hint)
            self.db_cur.execute(u"""UPDATE questions
                                    SET last_show = strftime('%s','now')
                                    WHERE question = '{0}'
                                    AND answer = '{1}'""".format(
                                        self.current_question,
                                        self.current_answer))
        else:
            self.context.Chat.SendMessage(u'Вопросы кончились.')
            self.stop_quiz()
        self.db_disconnect()

    def start_quiz(self):
        if not self.listen:
            log.info("Starting quiz...")
            self.context.Chat.SendMessage(u'/me Запускаем викторину!')
            self.db_connect()
            count_quest = self.db_cur.execute("SELECT COUNT(*) FROM questions")\
            .fetchone()
            self.db_disconnect()
            if count_quest:
                self.listen = True                
                self.context.Chat.SendMessage(u'/me Вопросы загружены. В базе \
%s вопросов' % count_quest)
                self.new_question()
            else:
                self.context.Chat.SendMessage(u'/me Вопросов в базе не найдено')
        else:
            self.context.Chat.SendMessage(u'Викторина уже запущена!!! \
Не стоит паниковать.')

    def stop_quiz(self):
        if self.listen:
            log.info("Stoping quiz...")
            self.listen = False
            self.context.Chat.SendMessage(u'/me Викторина остановлена!')

    def parse_answer(self, message):
        if self.listen and message.Body.lower() == self.current_answer.lower():
            self.listen = False
            log.info(u"Correct answer '{0}' from user {1}'".format(message.Body,
                                                         message.Sender.Handle))
            self.context.Chat.SendMessage(u"/me {0}, правильно!!! Ответ '{1}'"\
                                         .format(message.Sender.Handle,
                                                 self.current_answer))
            time.sleep(2)
            self.listen = True
            self.new_question()

    def next_answer(self):
        if self.listen:
            self.listen = False
            log.info(u"Next answer from user {0}'".format(self.context.Sender\
                                                         .Handle))
            self.context.Chat.SendMessage(
            u"/me Пользователь {0} пропустил вопрос. Правильный ответ был '{1}'"\
            .format(self.context.Sender.Handle,
             self.current_answer))
            time.sleep(2)
            self.listen = True
            self.new_question()

    def show_hint(self):
        if self.listen:
            self.context.Chat.SendMessage(u'/me Подсказка: {0}'.format(
                self.current_hint))

    #Допустимые комманды
    functions = {"!start": start_quiz,
                 u"!старт": start_quiz,
                 "!stop": stop_quiz,
                 u"!стоп": stop_quiz,
                 "!next": next_answer,
                 u"!далее": next_answer,
                 "!hint": show_hint,
                 u"!подсказка": show_hint
                 }

if __name__ == "__main__":
    quiz_cis = QuizBot()
    quiz_cis.run()

