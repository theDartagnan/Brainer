# -*- coding: utf-8 -*-
from copy import copy
from typing import Dict
from pymongo import MongoClient

__all__ = ['MongoConnector']


class MongoConnector:
    __slots__ = ['__configuration', '__connection']

    def __init__(self, configuration: Dict):
        self.__configuration = configuration.get('mongodb')
        self.__connection = None

    @property
    def client(self):
        return self.__connection

    @property
    def is_opened(self):
        return self.__connection is not None

    def open(self):
        host = self.__configuration.get('host', 'localhost')
        if 'port' in self.__configuration:
            host = "%s:%s" % (host, self.__configuration.get('port'))
        extra_params = dict()
        if 'credentials' in self.__configuration:
            creds = self.__configuration['credentials']
            if 'username' in creds:
                extra_params['username'] = creds['username']
                if 'password' in creds:
                    extra_params['password'] = creds['password']
                if 'authSource' in creds:
                    extra_params['authSource'] = creds['authSource']
                if 'authMechanism' in creds:
                    extra_params['authMechanism'] = creds['authMechanism']

        self.__connection = MongoClient(host, **extra_params)

    def close(self):
        if self.__connection is not None:
            self.__connection.close()
            self.__connection = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.close()
        except Exception as e:
            print("Exception while closing Mongo connection: " + str(e))
