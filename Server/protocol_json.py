import json
from protocol_base import ProtocolBase

class JSONProtocol(ProtocolBase):
    def encode_response(self, response_dict):
        return json.dumps(response_dict).encode('utf-8')
    
    def encode_request(self, request_dict):
        return json.dumps(request_dict).encode('utf-8')
    
    def decode_request(self, data):
        return json.loads(data.decode('utf-8'))
    
    def create_response(self, status, message, additional_data=None):
        response = {
            'status': status,
            'message': message
        }
        if additional_data:
            response.update(additional_data)
        return response