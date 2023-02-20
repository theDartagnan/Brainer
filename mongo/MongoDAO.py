# -*- coding: utf-8 -*-
from typing import List, Dict

from pymongo import ReturnDocument

from mongo.MongoConnector import MongoConnector

__all__ = ['MongoQuestion', 'MongoDAO']


class MongoQuestion:
    __slots__ = ['question', 'answer', 'pending_aksers']

    def __init__(self, question: str, answer: str, pending_askers: List = None):
        self.question = question
        self.answer = answer
        self.pending_aksers = pending_askers

    @property
    def has_answer(self):
        return self.answer is not None and self.answer != ''

    def __str__(self):
        return "{q: \"%s\", ans: \"%s\", askers:%s" % (self.question, self.answer, str(self.pending_aksers))

    @staticmethod
    def from_document(document: Dict):
        if not document:
            raise ValueError('document should not be None')
        if 'question' not in document:
            raise ValueError('mongo question document must have a question')
        return MongoQuestion(document.get('question'), document.get('answer'), document.get('pending_askers'))


class MongoDAO:
    def __init__(self, mongo_connector: MongoConnector, database: str = "brainers_db", collection: str = "questions"):
        self.__connector = mongo_connector
        self.__db = mongo_connector.client[database]
        self.__question_col = self.__db[collection]

    def init_indexes(self):
        self.__question_col.create_index("question", unique=True)

    def initialize_question(self, question: str, reply_to: str = None, correlation_id: str = None) -> MongoQuestion:
        corrected_question = question.strip().lower() if question else None
        if not corrected_question:
            raise ValueError("Question must not be null.")
        # Get question from mongo.
        # If present with an answer, just retrieve it
        # If present but without any answer, update its pendingAskers array with the new asker (if any).
        # If absent, insert it with a pending askers array of the new asker (if any)
        if not reply_to or not correlation_id:
            document = self.__question_col.find_one_and_update(
                {'question': corrected_question},
                {'$set': {'question': corrected_question}},
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
        else:
            document = self.__question_col.find_one_and_update(
                {'question': corrected_question},
                [
                    {
                        '$set': {
                            'pending_askers': {
                                '$switch': {
                                    'branches': [
                                        {
                                            'case': {
                                                '$and': [
                                                    {'$lte': ['$answer', None]},
                                                    {'$lte': ['$pending_askers', None]}
                                                ]
                                            },
                                            'then': [{"reply_to": reply_to, "correlation_id": correlation_id}]
                                        },
                                        {
                                            'case': {
                                                '$and': [
                                                    {'$lte': ['$answer', None]},
                                                    {'$not': {'$in': [reply_to, "$pending_askers.reply_to"]}}
                                                ]
                                            },
                                            'then': {'$concatArrays': [
                                                '$pending_askers',
                                                [{"reply_to": reply_to, "correlation_id": correlation_id}]
                                            ]}
                                        }
                                    ],
                                    'default': "$pending_askers"
                                }
                            }
                        }
                    }
                ],
                upsert=True,
                return_document=ReturnDocument.AFTER
            )
        return MongoQuestion(document.get('question'), document.get('answer'), document.get('pending_askers'))

    def set_answer(self, question: str, answer: str) -> MongoQuestion:
        corrected_question = question.strip().lower() if question else None
        if not corrected_question:
            raise ValueError("Question must not be null.")
        corrected_answer = answer.strip() if answer else None
        if not corrected_answer:
            raise ValueError("Answer must not be null.")
        # Get question from mongo.
        # If present with an answer, just retrieve it
        # If present but without any answer, update its answer and remove pendingAskers
        document = self.__question_col.find_one_and_update(
            {'question': corrected_question},
            [
                {
                    '$replaceWith': {
                        '$cond': {
                            'if': {'$lte': ['$answer', None]},
                            'then': {
                                '_id': '$_id',
                                'question': '$question',
                                'answer': corrected_answer
                            },
                            'else': '$$ROOT'
                        }
                    }
                }
            ],
            upsert=True,
            return_document=ReturnDocument.BEFORE
        )
        if document is None:
            return MongoQuestion(corrected_question, corrected_answer)
        else:
            return MongoQuestion(corrected_question, corrected_answer, document.get('pending_askers'))
