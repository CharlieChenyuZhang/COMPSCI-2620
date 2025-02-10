from datetime import datetime
import socket
import bcrypt
import re
from threading import Thread
from protocol_json import JSONProtocol
from protocol_custom import CustomProtocol
from db_manager import DatabaseManager

try:
    from config import server_host, server_port
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from config import server_host, server_port

class Actions:
    CREATE = "create"
    LOGIN = "login"
    LIST = "list"
    SEND = "send"
    LOAD_UNREAD = "load-unread"
    LOAD_PAST = "load-past"
    DELETE = "delete"
    DELETE_ACCOUNT = "delete_account"

class ChatServer:
    def __init__(self, host=server_host, port=server_port, use_json=True):
        self.host = host
        self.port = port
        self.protocol = JSONProtocol() if use_json else CustomProtocol()
        self.db = DatabaseManager()
        self.active_connections = {}  # {username: connection}
        self.user_connections = {}    # {connection: username}
        
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
                'unread_count': 0  # new account has no messages
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

        # store connection and get unread count
        self.active_connections[username] = conn
        unread_count = self.db.get_unread_count(username)
        
        return {
            'status': 'success',
            'unread_count': unread_count
        }
        
    def handle_list_accounts(self, data):
        pattern = data.get('pattern', '*')
        accounts = self.db.list_accounts()
        
        # handle pattern matching
        if pattern != '*':
            try:
                regex = re.compile(pattern)
                accounts = [acc for acc in accounts if regex.match(acc)]
            except re.error:
                return {
                    'status': 'error',
                    'message': 'Invalid pattern'
                }
                
        return {
            'status': 'success',
            'accounts': accounts
        }
        
    def handle_send_message(self, data, sender_conn):
        sender = self.user_connections.get(sender_conn)
        if not sender:
            return {
                'status': 'error',
                'message': 'Not logged in'
            }

        recipient = data.get('recipient')
        message = data.get('message')
        
        # check if user is trying to send message to themselves
        if sender == recipient:
            return {
                'status': 'error',
                'message': 'Cannot send messages to yourself'
            }

        if not self.db.account_exists(recipient):
            return {
                'status': 'error',
                'message': 'Recipient does not exist'
            }

        # store message in database
        message_id = self.db.store_message(sender, recipient, message)
        if not message_id:
            return {
                'status': 'error',
                'message': 'Failed to store message'
            }

        # if recipient is online, send message immediately
        recipient_conn = self.active_connections.get(recipient)
        if recipient_conn:
            try:
                notification = {
                    'status': 'message-received',
                    'message': message,
                    'sender': sender,
                    'message_id': message_id,
                    'timestamp': datetime.now().isoformat()
                }
                recipient_conn.sendall(self.protocol.encode_response(notification))
                # don't mark as read here - let recipient explicitly mark when loaded
            except Exception:
                pass

        return {'status': 'success', 'message_id': message_id}

    def handle_load_messages(self, data, conn):
        username = self.user_connections.get(conn)
        if not username:
            return {
                'status': 'error',
                'message': 'Not logged in'
            }

        action = data.get('action')
        count = data.get('count')
        other_user = data.get('recipient')

        if action == Actions.LOAD_UNREAD:
            # get unread messages for current user
            messages = self.db.get_messages(username, unread_only=True)
            if messages:
                # mark messages as read after retrieving them
                self.db.mark_messages_read(username)
        else:  # LOAD_PAST
            if not other_user:
                return {
                    'status': 'error',
                    'message': 'Recipient required for loading past messages'
                }
            if not count:
                return {
                    'status': 'error',
                    'message': 'Count required for loading past messages'
                }
            # get read messages between users
            messages = self.db.get_messages(
                username, 
                other_user=other_user, 
                count=count,
                read_only=True
            )

        return {
            'status': 'success',
            'messages': messages
        }
                                                
    def handle_delete_message(self, data, conn):
        username = self.user_connections.get(conn)
        if not username:
            return {
                'status': 'error',
                'message': 'Not logged in'
            }

        message_id = data.get('message_id')
        message = self.db.get_message(message_id)
        
        if not message or message['sender'] != username:
            return {
                'status': 'error',
                'message': 'Message not found or unauthorized'
            }

        recipient = message['recipient']
        self.db.delete_message(message_id)
        
        # notify recipient if online
        recipient_conn = self.active_connections.get(recipient)
        if recipient_conn:
            notification = {
                'status': 'message-deleted',
                'message_id': message_id
            }
            try:
                recipient_conn.sendall(self.protocol.encode_response(notification))
            except Exception:
                pass

        return {'status': 'success'}

    def handle_delete_account(self, data, conn):
        username = data.get('username')
        password = data.get('password')

        if not self.db.verify_account(username, password):
            return {
                'status': 'error',
                'message': 'Invalid credentials'
            }

        # delete all messages and account
        self.db.delete_account(username)  # this cascades to messages
        
        # notify all active users
        for other_conn in self.active_connections.values():
            if other_conn != conn:
                try:
                    notification = {
                        'status': 'account-deleted',
                        'username': username
                    }
                    other_conn.sendall(self.protocol.encode_response(notification))
                except Exception:
                    pass

        # clean up connections
        if username in self.active_connections:
            del self.active_connections[username]
        if conn in self.user_connections:
            del self.user_connections[conn]

        return {'status': 'success'}

    def handle_client(self, conn):
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                
                try:
                    request = self.protocol.decode_request(data)
                    action = request.get('action')
                    
                    if not action:
                        response = self.protocol.create_response(
                            False, 
                            'Invalid request format'
                        )
                    else:
                        try:
                            if action == Actions.CREATE:
                                response = self.handle_create_account(request)
                            elif action == Actions.LOGIN:
                                response = self.handle_login(request, conn)
                                if response['status'] == 'success':
                                    self.user_connections[conn] = request['username']
                            elif action == Actions.LIST:
                                response = self.handle_list_accounts(request)
                            elif action == Actions.SEND:
                                response = self.handle_send_message(request, conn)
                            elif action in [Actions.LOAD_UNREAD, Actions.LOAD_PAST]:
                                response = self.handle_load_messages(request, conn)
                            elif action == Actions.DELETE:
                                response = self.handle_delete_message(request, conn)
                            elif action == Actions.DELETE_ACCOUNT:
                                response = self.handle_delete_account(request, conn)
                                if response['status'] == 'success':
                                    break
                            else:
                                response = self.protocol.create_response(
                                    False, 
                                    'Invalid action'
                                )
                        except Exception as e:
                            response = self.protocol.create_response(
                                False,
                                f'Error processing request: {str(e)}'
                            )
                            print(f"Error processing request: {e}")
                    
                    conn.sendall(self.protocol.encode_response(response))
                except Exception as e:
                    error_response = self.protocol.create_response(
                        False,
                        f'Error decoding request: {str(e)}'
                    )
                    conn.sendall(self.protocol.encode_response(error_response))
                    print(f"Error decoding request: {e}")
                    
            except Exception as e:
                print(f"Connection error: {e}")
                break

        # clean up on disconnect
        if conn in self.user_connections:
            username = self.user_connections[conn]
            if username in self.active_connections:
                del self.active_connections[username]
            del self.user_connections[conn]
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