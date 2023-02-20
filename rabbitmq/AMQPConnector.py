# -*- coding: utf-8 -*-
from copy import copy
from typing import Dict
import pika

__all__ = ['AMQPConnector']


class AMQPConnector:
    __slots__ = ['_connection_params', '_connection']

    def __init__(self, configuration: Dict, heartbeat: int = None):
        self._connection = None
        self._connection_params = None
        self.__init_configuration(configuration, heartbeat)

    @property
    def connection(self):
        return self._connection

    @property
    def is_opened(self):
        return self._connection is not None

    def open(self):
        if self._connection_params is None:
            raise ValueError("AMQP Connector not initialized.")
        self._connection = pika.BlockingConnection(self._connection_params)

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __init_configuration(self, configuration: Dict, heartbeat: int = None):
        if 'rabbitmq' in configuration:
            conf = copy(configuration.get('rabbitmq'))
            creds = conf.get('credentials')
            if creds:
                username = creds.get('username')
                password = creds.get('password')
                if username and password:
                    conf['credentials'] = pika.PlainCredentials(username, password)
                else:
                    del conf['credentials']
            conf['heartbeat'] = heartbeat
            self._connection_params = pika.ConnectionParameters(**conf)
        else:
            self._connection_params = pika.ConnectionParameters(host='localhost', heartbeat=heartbeat)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.close()
        except Exception as e:
            print("Exception while closing AMQP connection: " + str(e))
