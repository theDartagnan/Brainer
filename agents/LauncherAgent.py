# -*- coding: utf-8 -*-
from abc import ABCMeta, abstractmethod


class LauncherAgent(metaclass=ABCMeta):

    @abstractmethod
    def start(self) -> None:
        pass
