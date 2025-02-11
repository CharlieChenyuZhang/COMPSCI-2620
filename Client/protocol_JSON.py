import socket
import json
from utils import get_server_config

server_host, server_port = get_server_config()

def send_request(request):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((server_host, server_port))  # Use config values
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
    response = send_request(request)
    print("read_messages response", response)
    return response.get("messages", [])

def list_accounts(pattern="*"):
    request = {
        "action": "list",
        "pattern": pattern
    }
    response = send_request(request)
    print("response", response)
    if response.get("status") == "success":
        accounts = response.get("accounts", [])
        # FIXME: use this when the server is ready
        # return {account['username']: account['unread_count'] for account in accounts}
        return {account: 10 for account in accounts}
    return {}
