import socket
import bcrypt
from threading import Thread
from enum import IntEnum
from protocol_json import JSONProtocol
from protocol_custom import CustomProtocol
from db_manager import DatabaseManager

class Actions:
    CREATE = "create"
    LOGIN = "login"
    LIST = "list"
    SEND = "send"
    READ = "read"
    DELETE = "delete"
    DELETE_ACCOUNT = "delete_account"

class ChatServer:
    def __init__(self, host='127.0.0.1', port=12345, use_json=True):  # Changed port to match client
        self.host = host
        self.port = port
        self.protocol = JSONProtocol() if use_json else CustomProtocol()
        self.db = DatabaseManager()
        self.active_connections = {}

    def hash_password(self, password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    def verify_password(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed)

    def handle_create_account(self, data):
        username = data.get('username')
        password = data.get('password')

        if self.db.account_exists(username):
            if self.db.verify_account(username, password):
                return {
                    'status': 'error',
                    'message': 'Account already exists and password matches'
                }
            return {
                'status': 'error',
                'message': 'Account exists but password is incorrect'
            }
        
        hashed_password = self.hash_password(password)
        if self.db.create_account(username, hashed_password):
            return {
                'status': 'success',
                'unread_count': 0  # New account has no messages
            }
        return {
            'status': 'error',
            'message': 'Could not create account'
        }

    def handle_login(self, data, conn):
        username = data.get('username')
        password = data.get('password')

        if not self.db.account_exists(username):
            return {
                'status': 'error',
                'message': 'Account does not exist'
            }

        if not self.db.verify_account(username, password):
            return {
                'status': 'error',
                'message': 'Incorrect password'
            }

        self.active_connections[username] = conn
        # TODO: Implement unread messages count from database
        return {
            'status': 'success',
            'unread_count': 0  # Will be implemented with messages
        }

    def handle_list_accounts(self, data):
        pattern = data.get('pattern', '*')  # Default to all accounts if no pattern
        accounts = self.db.list_accounts()
        return {
            'status': 'success',
            'accounts': accounts
        }

    def handle_client(self, conn):
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                
                request = self.protocol.decode_request(data)
                action = request.get('action')
                response = {'status': 'error', 'message': 'Invalid action'}

                if action == Actions.CREATE:
                    response = self.handle_create_account(request)
                elif action == Actions.LOGIN:
                    response = self.handle_login(request, conn)
                elif action == Actions.LIST:
                    response = self.handle_list_accounts(request)
                # TODO: Add other actions (SEND, READ, DELETE, DELETE_ACCOUNT)

                conn.sendall(self.protocol.encode_response(response))
            except Exception as e:
                print(f"Error handling client: {e}")
                break

        conn.close()
        
    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((self.host, self.port))
            server_socket.listen()
            print(f"server listening on {self.host}:{self.port}")

            while True:
                conn, addr = server_socket.accept()
                print(f"connected by {addr}")
                client_thread = Thread(target=self.handle_client, args=(conn,))
                client_thread.start()

if __name__ == "__main__":
    server = ChatServer()
    server.start()