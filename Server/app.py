import socket
import bcrypt
from threading import Thread
from enum import IntEnum
from protocol_json import JSONProtocol
from protocol_custom import CustomProtocol

class OpCode(IntEnum):
    CREATE_ACCOUNT = 0
    LOGIN = 1 
    LIST_ACCOUNTS = 2
    # will add the other opcodes later

class ChatServer:
    def __init__(self, host='127.0.0.1', port=65432, use_json=True): # just chose a random port
        self.host = host
        self.port = port
        
        self.protocol = JSONProtocol() if use_json else CustomProtocol() # default is JSON

        self.accounts = {}  # {username: {'password': hashed_password, 'unread_messages': []}}
        self.active_connections = {}  # {username: connection}

    def hash_password(self, password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    def verify_password(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed)

    def handle_create_account(self, data):
        username = data.get('username')
        password = data.get('password')

        if username in self.accounts:
            if self.verify_password(password, self.accounts[username]['password']):
                return self.protocol.create_response(False, 'FAILURE: Account already exists and password matches')
            return self.protocol.create_response(False, 'FAILURE: Account exists but password is incorrect')
        
        hashed_password = self.hash_password(password)
        self.accounts[username] = {
            'password': hashed_password,
            'unread_messages': []
        }
        return self.protocol.create_response(True, 'SUCCESS: Account created successfully')

    def handle_login(self, data, conn):
        username = data.get('username')
        password = data.get('password')

        if username not in self.accounts:
            return self.protocol.create_response(False, 'FAILURE: Account does not exist')

        if not self.verify_password(password, self.accounts[username]['password']):
            return self.protocol.create_response(False, 'FAILURE: Incorrect password')

        unread_count = len(self.accounts[username]['unread_messages']) # to do
        self.active_connections[username] = conn
        
        return self.protocol.create_response(
            True, 
            f'SUCCESS: Login successful. You have {unread_count} unread messages'
        )

    def handle_list_accounts(self):
        return self.protocol.create_response(
            True,
            'SUCCESS: Accounts retrieved',
            {'accounts': list(self.accounts.keys())}
        )
    
    def handle_client(self, conn, addr):
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                
                request = self.protocol.decode_request(data)
                opcode = request.get('opcode')
                response = self.protocol.create_response(False, 'FAILURE: Invalid opcode')

                if opcode == OpCode.CREATE_ACCOUNT:
                    response = self.handle_create_account(request)
                elif opcode == OpCode.LOGIN:
                    response = self.handle_login(request, conn)
                elif opcode == OpCode.LIST_ACCOUNTS:
                    response = self.handle_list_accounts(request)

                conn.sendall(self.protocol.encode_response(response))
            except Exception as e:
                print(f"Error handling client: {e}")
                break

        conn.close()

    def start(self):
        # open socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((self.host, self.port))
            server_socket.listen()
            print(f"server listening on {self.host}:{self.port}")

            # accept incoming connections and create a new thread per connection (good start for chat)
            while True:
                conn, addr = server_socket.accept()
                print(f"connected by {addr}")
                
                client_thread = Thread(target=self.handle_client, args=(conn, addr))
                client_thread.start()

if __name__ == "__main__":
    server = ChatServer()
    server.start()