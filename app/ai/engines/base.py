from abc import ABC, abstractmethod


class AIEngine(ABC):

    @abstractmethod
    def name(self):
        raise NotImplementedError

    @abstractmethod
    def process(self, input_path, output_path, scale):
        raise NotImplementedError
