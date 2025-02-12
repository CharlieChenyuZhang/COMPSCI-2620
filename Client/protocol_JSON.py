import socket
import json
from utils import get_server_config

server_host, server_port = get_server_config()
MSGLEN = 409600

class ChatClient:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False
    def connect(self):
        if self.connected:
            self.disconnect()  # Ensure previous connection is closed
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.connected = True

    def disconnect(self):
        """Close the current connection if it exists."""
        if self.connected and self.sock:
            self.sock.close()
            self.connected = False

    def send_request(self, request):
        """Send a request to the server and receive a response."""
        try:
            if not self.connected:
                self.connect()  # Ensure connection before sending request

            self.sock.sendall(json.dumps(request).encode("utf-8"))
            response = self.sock.recv(MSGLEN)  # Increase buffer size for large messages
            return json.loads(response.decode("utf-8"))
        except Exception as e:
            print(f"Error: {e}")
            self.disconnect()  # Reset connection status if an error occurs
            return {"status": "error", "message": "Connection lost"}

    def create_account(self, username, password):
        """Create a new account."""
        request = {
            "action": "create",
            "username": username,
            "password": password
        }
        return self.send_request(request)

    def login(self, username, password):
        """Log in with a new connection every time."""
        self.connect()  # Ensure a new connection for login
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
        """Send a message to a recipient."""
        request = {
            "action": "send",
            "recipient": recipient,
            "message": message
        }
        return self.send_request(request)

    def read_messages(self, count):
        """Retrieve unread messages."""
        request = {
            "action": "load-unread",
            "count": count
        }
        return self.send_request(request)

    def list_accounts(self, pattern="*", username=None):
        """List all accounts matching the given pattern."""
        request = {
            "action": "list",
            "pattern": pattern,
            "user_name": username
        }
        response = self.send_request(request)
        if response.get("status") == "success":
            return response.get("accounts", [])
        return {}

    def logout(self):
        """Disconnect from the server."""
        self.disconnect()
        print("Disconnected from server.")
        
    def delete_account(self, username, password):
        """Delete an existing account."""
        request = {
            "action": "delete_account",
            "username": username,
            "password": password
        }
        return self.send_request(request)


# Create a shared instance of ChatClient
# chat_client = ChatClient()
