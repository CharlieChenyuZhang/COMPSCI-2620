import socket
import json
from utils import get_server_config

server_host, server_port = get_server_config()

class ChatClient:
    def __init__(self):
        self.sock = None
        self.connected = False

    def connect(self):
        """ Establish a connection to the chat server. """
        if not self.connected:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_host, server_port))
            self.connected = True

    def send_request(self, request):
        """ Send a request to the server and receive a response. """
        try:
            if not self.connected:
                self.connect()

            self.sock.sendall(json.dumps(request).encode('utf-8'))
            response = self.sock.recv(4096)  # Increase buffer size for large messages
            return json.loads(response.decode('utf-8'))
        except Exception as e:
            print(f"Error: {e}")
            self.connected = False  # Reset connection status if an error occurs
            return {"status": "error", "message": "Connection lost"}

    def create_account(self, username, password):
        request = {
            "action": "create",
            "username": username,
            "password": password
        }
        return self.send_request(request)

    def login(self, username, password):
        request = {
            "action": "login",
            "username": username,
            "password": password
        }
        response = self.send_request(request)
        if response.get("status") == "success":
            print(f"User {username} logged in successfully.")
        return response

    def send_message(self, recipient, message):
        request = {
            "action": "send",
            "recipient": recipient,
            "message": message
        }
        return self.send_request(request)

    def read_messages(self, count):
        request = {
            "action": "load-unread",
            "count": count
        }
        return self.send_request(request)

    def list_accounts(self, pattern="*"):
        request = {
            "action": "list",
            "pattern": pattern
        }
        response = self.send_request(request)
        print("list_accounts response", response)
        if response.get("status") == "success":
            return response.get("accounts", [])
        return {}

    def logout(self):
        """ Disconnect from the server. """
        if self.connected:
            self.sock.close()
            self.connected = False
            print("Disconnected from server.")

# Create a shared instance of ChatClient
chat_client = ChatClient()
