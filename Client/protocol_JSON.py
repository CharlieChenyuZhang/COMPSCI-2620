import socket
import json

def send_request(request):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('localhost', 12345))  # Connect to the server
        s.sendall(json.dumps(request).encode('utf-8'))  # Send request
        response = s.recv(1024)  # Receive response
        return json.loads(response.decode('utf-8'))

def create_account(username, password):
    request = {
        "action": "create",
        "username": username,
        "password": password  # Assume password is already hashed
    }
    return send_request(request)

def login(username, password):
    request = {
        "action": "login",
        "username": username,
        "password": password  # Assume password is already hashed
    }
    return send_request(request)

def send_message(recipient, message):
    request = {
        "action": "send",
        "recipient": recipient,
        "message": message
    }
    return send_request(request)

def read_messages(count):
    request = {
        "action": "read",
        "count": count
    }
    return send_request(request)
