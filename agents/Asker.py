# -*- coding: utf-8 -*-
import json
import os
import signal
import uuid
from multiprocessing import Process, Pipe
from multiprocessing.connection import Connection
from typing import Dict

import pika

from agents.LauncherAgent import LauncherAgent
from constants.queues import ASKER_QUESTION_QUEUE
from rabbitmq.AMQPConnector import AMQPConnector

__all__ = ['Asker']


class AnswerReceiver(Process):
    """
    Answer receiver process : Prepare a personal reception queue, communicate it to the main process
    through a dedicated pipe, then receive memories' answers from this queue, to print them to the terminal.
    As the terminal is shared to print answer and asks question, a signal system is setup to re-print the question
    prompt once an answer has been printed.
    """
    __slots__ = ['__connection', '__cback_queue_sender']

    def __init__(self, configuration: Dict, cback_queue_sender: Connection):
        super().__init__(daemon=False)
        self.__connection = AMQPConnector(configuration)
        self.__cback_queue_sender = cback_queue_sender

    def run(self) -> None:
        # Connect to RabbitMq
        with self.__connection as coMgr:
            # Declare Answer receiver channel
            receiver_channel = coMgr.connection.channel()
            # Prepare result queue and setup channel
            result = receiver_channel.queue_declare(queue='', exclusive=True)
            callback_queue = result.method.queue
            receiver_channel.basic_consume(
                queue=callback_queue,
                on_message_callback=self.__on_answer,
                auto_ack=True)

            # Send callback queue through pipe to Asker process
            try:
                self.__cback_queue_sender.send(callback_queue)
            except ValueError as e:
                print("Answer Receiver: cannot communicate callback queue: " + str(e))
                return
            finally:
                self.__cback_queue_sender.close()

            # Receive memories' answers
            try:
                receiver_channel.start_consuming()
            except KeyboardInterrupt:
                # Receive from user ^C keyboard input or any other SINGINT
                pass

    @staticmethod
    def __on_answer(ch, method, props, body):
        try:
            ans = json.loads(body)
            question = ans.get('question')
            answer = ans.get('answer')
            if question is not None and answer is not None:
                print('\n' + '*' * 12)
                print("Question: " + question)
                print("Answer: " + answer)
                print('*' * 12 + '\n')
        except Exception as e:
            print("Invalid answer: " + str(e))
        # Ask a re-prompt from parent process
        os.kill(os.getppid(), signal.SIGUSR1)


class Asker(LauncherAgent):
    """
    Asker agent : Manage the Answer receiver process, and receive the personal reception queue from it through a
    dedicated pipe. Using a rabbitmq connection, send question typed by the user to a memory. To share properly the
    terminal with the Answer receiver process (printing answer as they arrive while also aksing for questions), use
    a signal system to interrupt the user input when an answer has been printed then re-prompt for a question.
    """
    __slots__ = ['__connection', '__sender_channel', '__cback_queue_pipe', '__ans_receiver',
                 '__reprompt_request_cpt']

    def __init__(self, configuration: Dict):
        super().__init__()
        self.__connection = AMQPConnector(configuration, heartbeat=0)
        self.__sender_channel = None
        self.__cback_queue_pipe = Pipe(duplex=False)
        self.__ans_receiver = AnswerReceiver(configuration, self.__cback_queue_pipe[1])
        self.__reprompt_request_cpt = 0

    def start(self) -> None:
        # Connect to RabbitMq
        with self.__connection as co_mgr:
            # Declare a channel to send question
            self.__sender_channel = co_mgr.connection.channel()
            # Prepare sender channel
            self.__sender_channel.queue_declare(queue=ASKER_QUESTION_QUEUE, durable=True)
            self.__sender_channel.basic_qos(prefetch_count=1)

            # set SIGINT handler to manage re-prompts
            old_sig_handler = signal.signal(signal.SIGUSR1, self.__handle_sigusr1_signal)
            # start answer receiver process
            self.__ans_receiver.start()
            # read callback queue from pipe
            try:
                callback_queue = self.__cback_queue_pipe[0].recv()
            except EOFError as e:
                print("Asker: Cannot receive callback queue: " + str(e))
                return
            finally:
                self.__cback_queue_pipe[0].close()

            print("Connection ready.")

            # Loop over user's questions until a "real" interruption (SIGINT) has been received (and not a SIGINT sent
            # only to interrupt the input function in order to re-prompt it properly after an answer has been printed)
            while True:
                try:
                    msg = input("Your question? ")
                    msg = msg.strip() if msg else None
                    if msg:
                        self.__ask_question(msg, callback_queue)
                except KeyboardInterrupt:
                    # if reprompt_request_cpt is > 0, a simple re prompt is required, otherwise exit is required
                    if self.__reprompt_request_cpt > 0:
                        self.__reprompt_request_cpt -= 1
                    else:
                        break

            # Reset SIGINT signal management
            signal.signal(signal.SIGUSR1, old_sig_handler)

        # Wait for answer receiver process termination
        self.__ans_receiver.join()

        print("\nBye.")

    def __ask_question(self, question: str, callback_queue: str) -> None:
        if question is None:
            return
        corr_id = str(uuid.uuid4())
        self.__sender_channel.basic_publish(
            exchange='',
            routing_key=ASKER_QUESTION_QUEUE,
            properties=pika.BasicProperties(
                reply_to=callback_queue,
                correlation_id=corr_id,
                content_type='application/json'
            ),
            body=json.dumps({'question': question}))

    def __handle_sigusr1_signal(self, signum, frame):
        # An answer has been printed on the terminal, we need to send a SIGINT interrupt to provoke the re-prompt of
        # the question
        self.__reprompt_request_cpt += 1
        os.kill(os.getpid(), signal.SIGINT)
