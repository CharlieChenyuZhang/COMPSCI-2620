import socket
from utils import get_server_config

server_host, server_port, _ = get_server_config()
MSGLEN = 409600  # Increased buffer size for large messages

class CustomChatClient:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connected = False

    def connect(self):
        """Establish a connection with the server."""
        if self.connected:
            return
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.connected = True

    def disconnect(self):
        """Close the connection if it exists."""
        if self.connected and self.sock:
            self.sock.close()
            self.connected = False

    def send_request(self, request):
        """Send a request to the server and receive a response as a string."""
        try:
            if not self.connected:
                self.connect()
            
            self.sock.sendall(request.encode("utf-8"))  # Send raw string request
            response = self.sock.recv(MSGLEN).decode("utf-8")  # Receive and decode response
            return response
        except Exception as e:
            print(f"Error: {e}")
            self.disconnect()  # Reset connection on error
            return "ERROR Connection lost"

    def create_account(self, username, password):
        """Create a new account."""
        request = f"CREATE {username} {password}"  # Assume password is already hashed
        return self.send_request(request)

    def login(self, username, password):
        """Log in, ensuring a new connection each time."""
        self.connect()
        request = f"LOGIN {username} {password}"
        response = self.send_request(request)

        if response.startswith("SUCCESS"):
            print(f"User {username} logged in successfully.")
        return response

    def send_message(self, recipient, message):
        """Send a message to a recipient."""
        message_length = len(message)
        request = f"SEND {recipient} {message_length} {message}"
        return self.send_request(request)

    def read_messages(self, count):
        """Retrieve unread messages."""
        request = f"READ {count}"
        return self.send_request(request)

    def list_accounts(self, pattern="*"):
        """List all accounts matching a pattern."""
        request = f"LIST {pattern}"
        response = self.send_request(request)

        if response.startswith("ACCOUNTS"):
            parts = response.split()
            num_accounts = int(parts[1])
            accounts = {}
            for i in range(num_accounts):
                username = parts[2 + i * 2]
                unread_count = int(parts[3 + i * 2])
                accounts[username] = unread_count
            return accounts
        return {}

    def delete_account(self, username, password):
        """Delete an existing account."""
        request = f"DELETE_ACCOUNT {username} {password}"
        return self.send_request(request)

    def logout(self):
        """Logout and disconnect from the server."""
        self.disconnect()
        print("Disconnected from server.")

# Create a shared instance of CustomChatClient
chat_client = CustomChatClient()
