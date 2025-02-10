import pytest
from protocol_json import JSONProtocol
from protocol_custom import CustomProtocol

@pytest.fixture(params=[JSONProtocol(), CustomProtocol()])
def protocol(request):
    return request.param

def test_encode_decode_create(protocol):
    request = {
        'action': 'create',
        'username': 'testuser',
        'password': 'testpass'
    }
    # for CustomProtocol, we need to format as a string
    if isinstance(protocol, CustomProtocol):
        encoded = f"CREATE testuser testpass".encode('utf-8')
    else:
        encoded = protocol.encode_request(request)
    decoded = protocol.decode_request(encoded)
    assert decoded['action'] == request['action']
    assert decoded['username'] == request['username']

def test_encode_decode_message(protocol):
    request = {
        'action': 'send',
        'recipient': 'user',
        'message': 'test message'
    }
    # for CustomProtocol, we need to format as a string
    if isinstance(protocol, CustomProtocol):
        msg_len = len(request['message'])
        encoded = f"SEND {request['recipient']} {msg_len} {request['message']}".encode('utf-8')
    else:
        encoded = protocol.encode_request(request)
    decoded = protocol.decode_request(encoded)
    assert decoded['action'] == request['action']
    assert decoded['message'] == request['message']