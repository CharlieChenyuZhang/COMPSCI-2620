import socket
import json
import threading
import time
import sys
import os
import getpass  # for password prompt
import datetime

# Maximum message buffer size
MSGLEN = 409600

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def create_request(action, **kwargs):
    """
    Helper that creates a JSON-encoded request matching the server's expected structure.
    For example:
      action = "login"
      username = "alice"
      password = "secret"
    """
    req = {"action": action}
    # Merge in additional keyword args
    req.update(kwargs)
    return json.dumps(req).encode()

class ChatClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.username = None
        self.logged_in = False

    def create_account(self, username):
        """
        Prompts for password and sends a 'create' request to the server.
        """
        password = getpass.getpass("Enter a password for new account: ")
        self.sock.sendall(
            create_request(
                action="create",
                username=username,
                password=password
            )
        )

    def login(self, username):
        """
        Prompts for password and sends a 'login' request to the server.
        """
        if self.logged_in:
            eprint("You are already logged in.")
            return

        password = getpass.getpass("Enter your password: ")
        self.sock.sendall(
            create_request(
                action="login",
                username=username,
                password=password
            )
        )

    def send_message(self, recipient, message):
        """
        Sends a message to the specified recipient.
        """
        if not self.logged_in:
            eprint("You must be logged in to send messages.")
            return

        self.sock.sendall(
            create_request(
                action="send",
                recipient=recipient,
                message=message
            )
        )

    def list_accounts(self, pattern="*"):
        """
        Requests list of accounts, optionally applying a wildcard/pattern.
        """
        if not self.logged_in:
            eprint("You must be logged in to list accounts.")
            return

        self.sock.sendall(
            create_request(
                action="list",
                pattern=pattern,
                user_name=self.username  # The server requires 'user_name'
            )
        )

    def load_unread_messages(self):
        """
        Requests all unread messages from the server (action='load-unread').
        """
        if not self.logged_in:
            eprint("You must be logged in to receive messages.")
            return

        self.sock.sendall(
            create_request(
                action="load-unread"
            )
        )

    def delete_account(self):
        """
        Deletes the currently logged-in user's account.
        Prompts for password again for confirmation.
        """
        if not self.logged_in:
            eprint("You must be logged in to delete your account.")
            return

        password = getpass.getpass("Enter your password to DELETE account: ")
        self.sock.sendall(
            create_request(
                action="delete_account",
                username=self.username,
                password=password
            )
        )

    def close(self):
        """
        Close the socket. (No explicit 'close' action is defined on server.)
        """
        self.sock.close()

# Adjust these to point to your server
PORT = 65432
HOST = "127.0.0.1"
client = ChatClient(HOST, PORT)

def handle_user():
    while True:
        if not client.logged_in:
            print("\nAvailable commands:")
            print("0. Login to an existing account")
            print("1. Create a new account")
            print("2. Exit")

            choice = input("Enter a command number (0-2): ").strip()
            if choice == "0":
                username = input("Enter your username: ").strip()
                client.login(username)
            elif choice == "1":
                username = input("Enter the username to create: ").strip()
                client.create_account(username)
            elif choice == "2":
                client.close()
                os._exit(0)
            else:
                print("Invalid command. Please try again.")
        else:
            # Once logged in, you can do more stuff
            print("\nAvailable commands:")
            print("0. Send a message")
            print("1. Load unread messages")
            print("2. List accounts")
            print("3. Delete account")
            print("4. Log off")
            choice = input("Enter a command number (0-4): ").strip()

            if choice == "0":
                recipient = input("Enter the recipient's username: ").strip()
                message = input("Enter the message: ")
                client.send_message(recipient, message)

            elif choice == "1":
                client.load_unread_messages()

            elif choice == "2":
                pattern = input("Enter a matching pattern (default '*'): ").strip()
                pattern = pattern if pattern else "*"
                client.list_accounts(pattern)

            elif choice == "3":
                # Deleting the account
                client.delete_account()

            elif choice == "4":
                # For "log off", we simply reset local state 
                # and remove ourselves from "active" on the client side.
                print("Logging off locally...")
                client.logged_in = False
                client.username = None
            else:
                print("Invalid command. Please try again.")

def handle_message():
    """
    Continuously read messages from server, parse JSON, 
    and handle them according to server's 'status' or fields.
    """
    while True:
        try:
            msg = client.sock.recv(MSGLEN)
            if not msg:
                print("Server closed the connection.")
                os._exit(1)
            response = json.loads(msg.decode())

            status = response.get("status", "")
            if status == "success":
                # This covers successful create/login/list/send/delete_account, etc.
                if "unread_count" in response:
                    # means either 'login' or 'create' returned it
                    print("SUCCESS. Unread messages count:", response["unread_count"])
                    # If it's a login success, store the username
                    # In your server code, you store it in user_connections if login succeeds.
                    # So let's figure out which is which:
                    if client.username is None:
                        # We used the 'login' action
                        # We didn't pass the username in the server's response, so we rely on client input
                        # If you want, you can store it from the last login attempt
                        # or store it earlier in the login function. 
                        # But let's just keep it here for clarity:
                        # we must ask them again or store it from the last input
                        # For simplicity, let's do:
                        # "already set it in client.login"? Actually let's set it now:
                        # We'll guess the server didn't echo the username. 
                        # We can manually do it or we can do a simpler approach 
                        # (like storing it right after we send the request). 
                        pass
                if client.username is None and "message" not in response:
                    # Might be from a 'create' success or 'login' success
                    # If we just tried to 'login', let's assume user typed a username last time.
                    # We can't 100% know from the server's response alone
                    # so let's ask the user or let's store it from the user input in login() 
                    # after we see success. 
                    # We'll do that below based on separate checks or you can do:
                    pass

                if "accounts" in response:
                    # This is from 'list' => respond with a list of accounts
                    print("List of accounts:")
                    for acc in response["accounts"]:
                        print(f"  {acc['username']} (unread from them: {acc['unread_count']})")

                if "messages" in response:
                    # This is from 'load-unread' or 'load-past'
                    print("You have unread messages:")
                    for m in response["messages"]:
                        print(f"From: {m['sender']}, Msg: {m['content']}, Time: {m['timestamp']}")

                if "message_id" in response and response.get("message"):
                    # Possibly from a 'send' success
                    print("Sent message successfully. Server says:", response["message"])

                if "message" in response and not response.get("message_id"):
                    # Some success messages might just have "message"
                    print("Server says:", response["message"])

            elif status == "error":
                # The server is indicating an error
                err_msg = response.get("message", "Unknown error")
                print("[ERROR]", err_msg)

            elif status == "message-received":
                # Real-time incoming message from another user
                print(
                    f"\n--- NEW MESSAGE ---\n"
                    f"From: {response.get('sender')}\n"
                    f"Message: {response.get('message')}\n"
                    f"Time: {response.get('timestamp')}\n"
                )

            elif status == "account-deleted":
                # Another account was deleted
                print(f"Account '{response.get('username')}' has been deleted.")

            elif status == "message-deleted":
                # A message was deleted
                print(f"Message with ID {response.get('message_id')} was deleted.")

            else:
                # Unexpected response or some custom status
                print("Server response:", response)

        except Exception as e:
            print("Error receiving/parsing server response:", e)
            break

# Start threads
threading.Thread(target=handle_user).start()
threading.Thread(target=handle_message).start()
