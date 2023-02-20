# -*- coding: utf-8 -*-
import json
from collections import namedtuple
from multiprocessing import Process, JoinableQueue, Queue
from typing import Dict

import pika

from agents.LauncherAgent import LauncherAgent
from constants.queues import ASKER_QUESTION_QUEUE, BRAINER_QUESTION_QUEUE, BRAINER_QUESTION_QUEUE_QUESTION_KEY, \
    BRAINER_QUESTION_QUEUE_ANSWER_KEY
from mongo.MongoConnector import MongoConnector
from mongo.MongoDAO import MongoDAO
from rabbitmq.AMQPConnector import AMQPConnector

__all__ = ['Memory']

AskerQuestion = namedtuple('AskerQuestion', ['question', 'reply_to', 'correlation_id'])

BrainerAnswer = namedtuple('BrainerAnswer', ['question', 'answer'])


class MemoryManager(Process):
    """
    A process that receive askers' questions and brainers' answers from the internal inter-process queue, and handle
    them through a MongoDb connection to maintain database state and with a RabbitMQ connection to send either
    questions to brainers and answers to pending askers.
    """
    __slots__ = ['__connection', '__mongo', '__mongo_dao_info', '__mongo_dao', '__sender_channel',
                 '__question_internal_queue']

    def __init__(self, configuration: Dict, question_internal_queue: Queue):
        super().__init__(daemon=False)
        self.__connection = AMQPConnector(configuration, heartbeat=0)
        self.__mongo = MongoConnector(configuration)
        self.__mongo_dao_info = None
        self.__extract_mongo_db_col_from_configuration(configuration)
        self.__mongo_dao = None
        self.__sender_channel = None
        self.__question_internal_queue = question_internal_queue

    def run(self) -> None:
        # Connect to mongo and RabbitMq
        with self.__mongo, self.__connection as co_mgr:
            # Setup mongo DAO and init collections indexes
            self.__mongo_dao = MongoDAO(self.__mongo, **self.__mongo_dao_info)
            self.__mongo_dao.init_indexes()
            # Declare a channel to send question to aksers or brainers
            self.__sender_channel = co_mgr.connection.channel()
            # Setup channel for brainers channel
            self.__sender_channel.exchange_declare(exchange=BRAINER_QUESTION_QUEUE, exchange_type='direct')

            # Loop over the internal inter-process queue
            keep_reading_queue = True
            try:
                while keep_reading_queue:
                    data = self.__question_internal_queue.get()
                    if data is None:
                        keep_reading_queue = False
                    elif isinstance(data, AskerQuestion):
                        self.__handle_asker_question(data)
                    elif isinstance(data, BrainerAnswer):
                        self.__handle_brainer_answer(data)
                    else:
                        print("MemoryManager: Cannot handle data of type: " + str(type(data)))
                    # in any case, ack task done from queue
                    self.__question_internal_queue.task_done()
            except ValueError as e:
                print("MemoryManager: Unable to read from internal queue: " + str(e))
            except KeyboardInterrupt as e:
                # Receive from user ^C keyboard input or any other SINGINT
                pass

    def __handle_asker_question(self, question: AskerQuestion) -> None:
        # Either create the question in Mongo, update it with the pending asker or just retrieve it if an answer is
        # already present
        mongo_question = self.__mongo_dao.initialize_question(question.question, question.reply_to,
                                                              question.correlation_id)
        if mongo_question.has_answer:
            print("Receive already known question from asker. Send the answer back.")
            self.__answer_to_asker(mongo_question.question, mongo_question.answer, question.reply_to,
                                   question.correlation_id)
        else:
            print("Receive a question from asker without known answer. Send the question to brainers.")
            self.__ask_question_to_brainers(mongo_question.question)

    def __handle_brainer_answer(self, answer: BrainerAnswer) -> None:
        # Either create the question with its answer, update it with the answer and clear the pending asker,
        # or do nothing if an answer is already present
        print("Receive an answer from a brainer.")
        mongo_question = self.__mongo_dao.set_answer(answer.question, answer.answer)
        if mongo_question.pending_aksers:
            print("Send an answer back to %d pending askers." % len(mongo_question.pending_aksers))
            for asker in mongo_question.pending_aksers:
                self.__answer_to_asker(mongo_question.question, mongo_question.answer,
                                       asker['reply_to'], asker['correlation_id'])

    def __answer_to_asker(self, question: str, answer: str, reply_to: str, correlation_id: str):
        self.__sender_channel.basic_publish(exchange='',
                                            routing_key=reply_to,
                                            properties=pika.BasicProperties(
                                                correlation_id=correlation_id,
                                                content_type='application/json'),
                                            body=json.dumps({'question': question, 'answer': answer}))

    def __ask_question_to_brainers(self, question: str):
        self.__sender_channel.basic_publish(
            exchange=BRAINER_QUESTION_QUEUE,
            routing_key=BRAINER_QUESTION_QUEUE_QUESTION_KEY,
            properties=pika.BasicProperties(content_type='application/json'),
            body=json.dumps({'question': question}))

    def __extract_mongo_db_col_from_configuration(self, configuration) -> None:
        conf = configuration.get('mongodb')
        self.__mongo_dao_info = dict()
        if 'database' in conf:
            self.__mongo_dao_info['database'] = conf['database']
        if 'collection' in conf:
            self.__mongo_dao_info['collection'] = conf['collection']


class BrainerAnswerManager(Process):
    """
    A process that receive brainers' answers from RabbitMq, and send them to the internal inter-process queue.
    """
    __slots__ = ['__connection', '__question_internal_queue', '__channel', '__consumer_tag']

    def __init__(self, configuration: Dict, question_internal_queue: Queue):
        super().__init__(daemon=False)
        self.__connection = AMQPConnector(configuration)
        self.__question_internal_queue = question_internal_queue
        self.__channel = None
        self.__consumer_tag = None

    def run(self) -> None:
        # Connect to RabbitMq
        with self.__connection as co_mgr:
            # connection is assumed to be opened
            # Declare a channel to receive answer from brainers
            self.__channel = co_mgr.connection.channel()
            # Declare the queue to receive from
            # Setup channel to receive their questions
            self.__channel.exchange_declare(exchange=BRAINER_QUESTION_QUEUE, exchange_type='direct')
            # Setup personnal queue
            result = self.__channel.queue_declare(queue='', exclusive=True)
            queue_name = result.method.queue
            # Bind the result queue to channel with the routing key answer
            self.__channel.queue_bind(exchange=BRAINER_QUESTION_QUEUE, queue=queue_name,
                                      routing_key=BRAINER_QUESTION_QUEUE_ANSWER_KEY)
            # Prepare the consumtion of answer from bainers
            self.__consumer_tag = self.__channel.basic_consume(queue=queue_name,
                                                               on_message_callback=self.__on_brainer_answer)

            # Await for askers' questions
            print("Waiting for brainers' answer...")
            try:
                self.__channel.start_consuming()
            except KeyboardInterrupt:
                # Receive from user ^C keyboard input or any other SINGINT
                pass

            print("BrainerAnswerManager: will exit")

    # def stop(self) -> None:
    #    if self.__consumer_tag is not None:
    #        self.__channel.basic_cancel(self.__consumer_tag)
    #       self.__consumer_tag = None

    def __on_brainer_answer(self, ch, method, props, body):
        try:
            data = json.loads(body)
            question = data.get('question')
            answer = data.get('answer')
            if not question or not answer:
                raise ValueError('Missing question or answer')
        except Exception as e:
            print("Invalid brainer's question: " + str(e))
            return
        else:
            brainer_ans = BrainerAnswer(question, answer)
            self.__question_internal_queue.put(brainer_ans)
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)


class Memory(LauncherAgent):
    """
    Memory agent : manage BrainerAnswerManager and MemoryManager processes, and receive askers' question
    from RabbitMq, then send them to the internal inter-process queue.
    """
    __slots__ = ['__connection', '__question_internal_queue', '__asker_question_manager', '__brainer_answer_manager']

    def __init__(self, configuration: Dict):
        super().__init__()
        self.__connection = AMQPConnector(configuration)
        self.__question_internal_queue = JoinableQueue()
        self.__asker_question_manager = MemoryManager(configuration, self.__question_internal_queue)
        self.__brainer_answer_manager = BrainerAnswerManager(configuration, self.__question_internal_queue)

    def start(self) -> None:
        # Connect to RabbitMq
        with self.__connection as co_mgr:
            # Declare a channel to receive question from askers
            channel = co_mgr.connection.channel()
            # Declare the queue to receive from
            channel.queue_declare(queue=ASKER_QUESTION_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)
            # Bind the queue to the channel
            channel.basic_consume(queue=ASKER_QUESTION_QUEUE, on_message_callback=self.__on_asker_question)

            # start the asker manager process
            self.__asker_question_manager.start()

            # Create the BrainerAnswerManager
            self.__brainer_answer_manager.start()

            # Await for askers' questions
            print("Waiting for askers' questions")
            try:
                channel.start_consuming()
            except KeyboardInterrupt:
                pass

            # Wait for BrainerAnswerManager and MemoryManager processes to stop
            self.__brainer_answer_manager.join(3000)
            self.__asker_question_manager.join(3000)
            # Empty the internal inter-process queue to stop it properly
            while not self.__question_internal_queue.empty():
                self.__question_internal_queue.get_nowait()
                self.__question_internal_queue.task_done()
            # Wait for the internal inter-process queue to stop
            self.__question_internal_queue.join()

        print("Bye.")

    def __on_asker_question(self, ch, method, props, body):
        try:
            q = json.loads(body)
            question = q.get('question')
            if not question:
                raise ValueError('Missing question')
        except Exception as e:
            print("Invalid asker's question: " + str(e))
            return
        else:
            asker_question = AskerQuestion(question, props.reply_to, props.correlation_id)
            self.__question_internal_queue.put(asker_question)
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)
