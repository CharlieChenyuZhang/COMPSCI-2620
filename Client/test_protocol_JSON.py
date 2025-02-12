import socket
import json
import time
from utils import get_server_config

server_host, server_port = get_server_config()
MSGLEN = 409600

class ChatClient:
    def __init__(self):
        """Initialize the client with a persistent connection."""
        self.sock = None
        self.connected = False
        self.username = None  # Track the logged-in user
        # self.connect()

    def connect(self):
        """Ensure a new connection is established only when necessary."""
        # if self.connected and self.sock:
        #     return

        # self.disconnect()  # Ensure cleanup of previous socket if any
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_host, server_port))
            self.connected = True
            print("✅ Connected to server")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            self.connected = False

    def disconnect(self):
        """Close the current connection if it exists."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.connected = False

    def send_request(self, request):
        """Send a request to the server and handle connection errors."""
        if not self.connected:
            print("🔄 Reconnecting before sending request...")
            self.connect()

        try:
            self.sock.sendall(json.dumps(request).encode("utf-8"))
            response = self.sock.recv(MSGLEN)
            return json.loads(response.decode("utf-8"))
        except (socket.error, ConnectionResetError, BrokenPipeError) as e:
            print(f"⚠️ Connection error: {e}. Reconnecting...")
            self.connect()
            return {"status": "error", "message": "Connection lost. Please try again."}
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return {"status": "error", "message": "An unexpected error occurred."}

    def create_account(self, username, password):
        """Create a new account."""
        request = {
            "action": "create",
            "username": username,
            "password": password
        }
        return self.send_request(request)

    def login(self, username, password):
        """Log in with a persistent connection."""
        self.connect()
        # if self.username:
        #     print(f"🔄 Already logged in as {self.username}. Reconnecting...")
        #     self.connect()  # Ensure persistent connection is maintained

        request = {
            "action": "login",
            "username": username,
            "password": password
        }
        response = self.send_request(request)

        if response.get("status") == "success":
            print(f"✅ User {username} logged in successfully.")
            self.username = username  # Store logged-in user
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
        print("📋 list_accounts response:", response)
        if response.get("status") == "success":
            return response.get("accounts", [])
        return {}

    def logout(self):
        """Log out and disconnect from the server."""
        if self.username:
            print(f"🔓 Logging out {self.username}...")
        self.username = None
        self.disconnect()
        print("🔌 Disconnected from server.")

# Create a **persistent** shared instance of ChatClient
chat_client = ChatClient()
