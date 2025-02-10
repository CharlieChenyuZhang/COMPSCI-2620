from abc import ABC, abstractmethod

class ProtocolBase(ABC):
    @abstractmethod
    def encode_response(self, response_dict):
        pass
    
    @abstractmethod
    def decode_request(self, data):
        pass
    
    @abstractmethod
    def create_response(self, status, message, additional_data=None):
        pass