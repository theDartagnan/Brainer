# -*- coding: utf-8 -*-
import json
from typing import Dict

import pika

from agents.LauncherAgent import LauncherAgent
from constants.queues import BRAINER_QUESTION_QUEUE, BRAINER_QUESTION_QUEUE_ANSWER_KEY, \
    BRAINER_QUESTION_QUEUE_QUESTION_KEY
from rabbitmq.AMQPConnector import AMQPConnector

__all__ = ['BrainerSimple']


class BrainerSimple(LauncherAgent):
    """
    Brainer agent : Receive memories' questions from RabbitMq, allow the user to answer them and reply the question
    with its answer to any memories.
    """
    __slots__ = ['__connection']

    def __init__(self, configuration: Dict):
        super().__init__()
        self.__connection = AMQPConnector(configuration)

    def start(self) -> None:
        # Connect to RabbitMq
        with self.__connection as coMgr:
            # Declare a channel to receive questions and send answers
            channel = coMgr.connection.channel()
            # Setup channel to receive their questions
            channel.exchange_declare(exchange=BRAINER_QUESTION_QUEUE, exchange_type='direct')
            # Setup personnal queue
            result = channel.queue_declare(queue='', exclusive=True)
            queue_name = result.method.queue
            # Bind the result queue to channel with the routing key answer
            channel.queue_bind(exchange=BRAINER_QUESTION_QUEUE, queue=queue_name,
                               routing_key=BRAINER_QUESTION_QUEUE_QUESTION_KEY)
            # Prepare the consumtion of answer from bainers
            channel.basic_consume(queue=queue_name, on_message_callback=self.__on_question)

            # Await messages from internal queue
            print("Connection ready. Waiting for question...")
            try:
                channel.start_consuming()
            except KeyboardInterrupt:
                # Receive from user ^C keyboard input or any other SINGINT
                pass

        print("\nBye.")

    @staticmethod
    def __on_question(ch, method, props, body) -> None:
        try:
            q = json.loads(body)
            question = q.get('question')
            if not question:
                raise ValueError('Invalid question: missing question or answer')
        except Exception as e:
            print("Invalid question: " + str(e))
            return
        finally:
            # In any case, ack the reception
            ch.basic_ack(delivery_tag=method.delivery_tag)

        # Here question is ok : send it to the Question handler thread through internal queue
        print('*' * 12)
        print('Question: ' + question)
        answer = input('Answer (enter to skip): ')
        answer = answer.strip()
        if answer:
            try:
                ch.basic_publish(exchange=BRAINER_QUESTION_QUEUE,
                                 routing_key=BRAINER_QUESTION_QUEUE_ANSWER_KEY,
                                 properties=pika.BasicProperties(content_type='application/json'),
                                 body=json.dumps({'question': question, 'answer': answer}))
            except Exception as e:
                print("Exception while publishing answer: " + str(e))
