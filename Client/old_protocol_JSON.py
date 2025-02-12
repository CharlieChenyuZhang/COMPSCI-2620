import socket
import json
import threading
from utils import get_server_config

server_host, server_port = get_server_config()


class ChatClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.listener_thread = None
        self.running = False  # Flag to control the listener thread
        self.message_callback = None  # Function to handle new messages

    def connect(self):
        """Establish a persistent connection with the server."""
        if self.connected:
            return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((server_host, server_port))
            self.connected = True
            self.running = True
            print("Connected to chat server.")

            # Start a background thread to listen for incoming messages
            self.listener_thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.listener_thread.start()
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False

    def disconnect(self):
        """Disconnect from the server and stop the listener thread."""
        self.running = False  # Stop the listening thread
        if self.connected:
            try:
                self.sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")
            finally:
                self.connected = False
                print("Disconnected from chat server.")

    def send_request(self, request):
        """Send a request to the server."""
        try:
            if not self.connected:
                self.connect()

            self.sock.sendall(json.dumps(request).encode("utf-8"))
            self.sock.settimeout(5)  # Timeout after 5 seconds
            response = self.sock.recv(4096)  # Increase buffer size for large messages
            return json.loads(response.decode("utf-8"))
        except Exception as e:
            print(f"Error sending request: {e}")
            self.disconnect()

    def send_message(self, recipient, message):
        """Send a message to another user."""
        request = {"action": "send", "recipient": recipient, "message": message}
        self.send_request(request)

    def receive_messages(self):
        """Continuously listen for incoming messages from the server."""
        while self.running:
            try:
                response = self.sock.recv(4096).decode("utf-8")
                if response:
                    data = json.loads(response)
                    if data.get("status") == "new_message":
                        sender = data["sender"]
                        message = data["message"]
                        if self.message_callback:
                            self.message_callback(sender, message)
            except Exception as e:
                print(f"Error receiving message: {e}")
                self.running = False
                break

    def register_callback(self, callback):
        """Register a callback function to handle incoming messages."""
        self.message_callback = callback

    def create_account(self, username, password):
        """Create a new account."""
        request = {"action": "create", "username": username, "password": password}
        return self.send_request(request)

    def login(self, username, password):
        """Log in a user."""
        self.connect()  # Ensure connection before login
        request = {"action": "login", "username": username, "password": password}
        response = self.send_request(request)
        print("login response", response)
        if response.get("status") == "success":
            print(f"User {username} logged in successfully.")
        return response

    def read_messages(self, count):
        """Retrieve unread messages."""
        request = {"action": "load-unread", "count": count}
        return self.send_request(request)

    def list_accounts(self, pattern="*", username=None):
        """List all available accounts."""
        request = {"action": "list", "pattern": pattern, "user_name": username}
        response = self.send_request(request)
        print("list_accounts response", response)
        if response and response.get("status") == "success":
            return response.get("accounts", [])
        return []

    def logout(self):
        """Log out and disconnect."""
        self.disconnect()
        print("Logged out from chat server.")


# Create a shared instance of ChatClient
chat_client = ChatClient()
