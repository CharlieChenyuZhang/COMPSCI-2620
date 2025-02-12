import socket
import json
import threading

# Maximum message buffer size
MSGLEN = 409600

class ChatClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.sock.settimeout(2)  # Non-blocking socket with a timeout
        self.username = None
        self.lock = threading.Lock()

    def send_request(self, action, data):
        try:
            self.lock.acquire()
            request = json.dumps({"action": action, **data}).encode()
            self.sock.sendall(request)
            response = self.sock.recv(MSGLEN).decode()
            if response:
                return json.loads(response)
            return {"status": "error", "message": "No response from server"}
        finally:
            self.lock.release()

    def create_account(self, username, password):
        return self.send_request("create", {"username": username, "password": password})

    def login(self, username, password):
        response = self.send_request("login", {"username": username, "password": password})
        if response.get("status") == "success":
            self.username = username
        return response

    def send_message(self, recipient, message):
        return self.send_request("send", {"recipient": recipient, "message": message})

    def receive_messages(self):
        return self.send_request("load-unread", {})

    def list_accounts(self, pattern="*"):
        return self.send_request("list", {"pattern": pattern})

    def delete_account(self, password):
        response = self.send_request("delete_account", {"username": self.username, "password": password})
        if response.get("status") == "success":
            self.username = None
        return response

    def log_off(self):
        self.username = None
        return {"status": "success", "message": "Logged off successfully"}

    def close(self):
        self.sock.close()
