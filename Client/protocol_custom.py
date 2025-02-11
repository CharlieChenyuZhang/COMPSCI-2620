import socket
from utils import get_server_config

server_host, server_port = get_server_config()

def send_request(request):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((server_host, server_port))  # Use config values
        s.sendall(request.encode('utf-8'))  # Send request
        response = s.recv(1024)  # Receive response
        return response.decode('utf-8')

def create_account(username, password):
    request = f"CREATE {username} {password}"  # Assume password is already hashed
    return send_request(request)

def login(username, password):
    request = f"LOGIN {username} {password}"  # Assume password is already hashed
    return send_request(request)

def send_message(recipient, message):
    message_length = len(message)
    request = f"SEND {recipient} {message_length} {message}"
    return send_request(request)

def read_messages(count):
    request = f"READ {count}"
    return send_request(request)
