import socket
import json
import threading
import time
import sys
import os
import queue
from datetime import datetime

message_queue = queue.Queue() 

# Maximum message buffer size
MSGLEN = 409600
PORT = 65432

# A function for printing to stderr
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# Class for the chat client
class ChatClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((server_host, server_port))
        self.username = None
        self.login_err = False

    # def send_request(self, action, data):
    #     request = json.dumps({"action": action, **data}).encode()
    #     self.sock.sendall(request)
    #     response = self.sock.recv(MSGLEN).decode()
    #     print("send_request response", repr(response))
    #     return json.loads(response)
    # Then modify send_request() to check this queue before receiving data:
    def send_request(self, action, data):
        request = json.dumps({"action": action, **data}).encode()
        self.sock.sendall(request)

        # Wait for a response
        start_time = time.time()
        while time.time() - start_time < 5:  # 5-second timeout
            if not message_queue.empty():
                response = message_queue.get()
                print("send_request response", response)
                return response

        # If no response in queue, fallback to receiving normally
        response = self.sock.recv(MSGLEN).decode()
        if not response.strip():
            print("No response received from server.")
            return {"status": "error", "message": "No response from server"}

        parsed_response = json.loads(response)
        print("send_request response", parsed_response)
        return parsed_response

    def create_account(self, username, password):
        response = self.send_request("create", {"username": username, "password": password})
        print(response.get("message", "Account creation response received."))

    def login(self, username, password):
        response = self.send_request("login", {"username": username, "password": password})
        print("login response", response)
        if response.get("status") == "success":
            self.username = username
            print("Logged in successfully. Unread messages:", response.get("unread_count", 0))
        else:
            print("Login failed:", response.get("message"))

    def send_message(self, recipient, message):
        response = self.send_request("send", {"recipient": recipient, "message": message})
        print(response.get("message", "Message sent response received."))

    def list_accounts(self, pattern="*"):
        response = self.send_request("list", {"user_name": self.username, "pattern": pattern})
        print("Accounts:", response.get("accounts", []))

    def receive_messages(self):
        response = self.send_request("load-unread", {})
        messages = response.get("messages", [])
        for msg in messages:
            print(f"{msg['sender']} sent: {msg['message']} at {msg['timestamp']}")

    def delete_account(self, password):
        response = self.send_request("delete_account", {"username": self.username, "password": password})
        print(response.get("message", "Account deletion response received."))
        if response.get("status") == "success":
            self.username = None

    def log_off(self):
        self.username = None
        print("Logged off successfully.")

    def close(self):
        self.sock.close()

# Interactive script
host = "127.0.0.1"
client = ChatClient(host, PORT)

def handle_user():
    while True:
        print("Available commands:")
        if not client.username:
            print("0. Login")
            print("1. Create an account")
            print("2. Exit")
            choice = input("Enter a command number (0-2): ")

            if choice == "0":
                username = input("Enter your username: ")
                password = input("Enter your password: ")
                client.login(username, password)
            elif choice == "1":
                username = input("Enter username: ")
                password = input("Enter password: ")
                client.create_account(username, password)
            elif choice == "2":
                client.close()
                os._exit(1)
            else:
                print("Invalid command. Try again.")
        else:
            print("0. Send a message")
            print("1. Check messages")
            print("2. List accounts")
            print("3. Delete account")
            print("4. Log off")
            choice = input("Enter a command number (0-4): ")

            if choice == "0":
                recipient = input("Enter recipient username: ")
                message = input("Enter message: ")
                client.send_message(recipient, message)
            elif choice == "1":
                client.receive_messages()
            elif choice == "2":
                pattern = input("Enter search pattern (or * for all): ")
                client.list_accounts(pattern)
            elif choice == "3":
                password = input("Enter password to confirm deletion: ")
                client.delete_account(password)
            elif choice == "4":
                client.log_off()
            else:
                print("Invalid command. Try again.")

def handle_message():
    while True:
        try:
            msg = client.sock.recv(MSGLEN).decode()
            if not msg:
                break
            msg = json.loads(msg)
            
            # If it's a normal message, print it
            if msg.get("status") in ["message-received", "message-deleted"]:
                print(f"{msg['sender']} sent: {msg['message']} at {msg['timestamp']}")
            else:
                # Store non-chat responses in the queue for send_request() to handle
                message_queue.put(msg)
        except Exception as e:
            print("Error in handle_message:", e)

# Then modify send_request() to check this queue before receiving data:
def send_request(self, action, data):
    request = json.dumps({"action": action, **data}).encode()
    self.sock.sendall(request)

    # Wait for a response
    start_time = time.time()
    while time.time() - start_time < 5:  # 5-second timeout
        if not message_queue.empty():
            response = message_queue.get()
            print("send_request response", response)
            return response

    # If no response in queue, fallback to receiving normally
    response = self.sock.recv(MSGLEN).decode()
    if not response.strip():
        print("No response received from server.")
        return {"status": "error", "message": "No response from server"}

    parsed_response = json.loads(response)
    print("send_request response", parsed_response)
    return parsed_response

def request_deliver():
    if client.username:
        client.receive_messages()

threading.Thread(target=handle_user).start()
threading.Thread(target=handle_message).start()
