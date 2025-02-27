import grpc
from concurrent import futures
import bcrypt
from datetime import datetime
import logging
import re
import time
import uuid
from typing import Dict, List
import sys
import os

# Add Server directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'Server'))

import chat_pb2
import chat_pb2_grpc
from db_manager import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self):
        self.db = DatabaseManager()
        self.active_subscribers: Dict[str, grpc.ServicerContext] = {}
        self.user_sessions: Dict[str, str] = {}  # session_id to username mapping
        
    def _authenticate(self, context) -> str:
        """Authenticate user from metadata"""
        try:
            metadata = dict(context.invocation_metadata())
            session_id = metadata.get('session_id')
            if not session_id:
                logging.error("Missing session ID in request")
                context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Missing session ID')
            
            username = self.user_sessions.get(session_id)
            if not username:
                logging.error(f"Invalid session ID: {session_id}")
                context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Invalid session')
            logging.info(f"Successfully authenticated user: {username}")
            return username
        except Exception as e:
            logging.error(f"Authentication error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, 'Authentication error')

    def CreateAccount(self, request, context):
        if self.db.account_exists(request.username):
            if self.db.verify_account(request.username, request.password):
                return chat_pb2.CreateAccountResponse(
                    success=False,
                    message="Account already exists and password matches"
                )
            return chat_pb2.CreateAccountResponse(
                success=False,
                message="Account exists but password is incorrect"
            )
            
        hashed_password = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt())
        if self.db.create_account(request.username, hashed_password):
            return chat_pb2.CreateAccountResponse(
                success=True,
                message="Account created successfully",
                unread_count=0
            )
            
        return chat_pb2.CreateAccountResponse(
            success=False,
            message="Failed to create account"
        )

    def Login(self, request, context):
        if not self.db.account_exists(request.username):
            return chat_pb2.LoginResponse(
                success=False,
                message="Account does not exist"
            )
            
        if not self.db.verify_account(request.username, request.password):
            return chat_pb2.LoginResponse(
                success=False,
                message="Incorrect password"
            )
            
        # Generate a unique session ID
        session_id = str(uuid.uuid4())
        self.user_sessions[session_id] = request.username
        
        # Get unread counts per user
        unread_counts = {}
        for other_user in self.db.list_accounts():
            if other_user != request.username:
                count = self.db.get_unread_count_from_sender(request.username, other_user)
                if count > 0:
                    unread_counts[other_user] = count
                    
        return chat_pb2.LoginResponse(
            success=True,
            message="Login successful",
            unread_counts=unread_counts,
            session_id=session_id
        )

    def ListAccounts(self, request, context):
        # Authenticate user
        username = self._authenticate(context)
        
        accounts = []
        all_accounts = self.db.list_accounts()
        
        if request.pattern != '*':
            try:
                regex = re.compile(request.pattern)
                filtered_accounts = [acc for acc in all_accounts if regex.match(acc)]
            except re.error:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid pattern")
        else:
            filtered_accounts = all_accounts

        for account in filtered_accounts:
            if account != username:
                unread_count = self.db.get_unread_count_from_sender(username, account)
                accounts.append(chat_pb2.AccountInfo(
                    username=account,
                    unread_count=unread_count
                ))
                
        return chat_pb2.ListAccountsResponse(accounts=accounts)

    def SendMessage(self, request, context):
        # Authenticate sender
        sender = self._authenticate(context)
        if sender != request.sender:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
        
        if request.sender == request.recipient:
            return chat_pb2.SendMessageResponse(
                success=False,
                message="Cannot send message to yourself"
            )
            
        if not self.db.account_exists(request.recipient):
            return chat_pb2.SendMessageResponse(
                success=False,
                message="Recipient does not exist"
            )
            
        message_id = self.db.store_message(
            request.sender,
            request.recipient,
            request.content
        )
        
        if not message_id:
            return chat_pb2.SendMessageResponse(
                success=False,
                message="Failed to store message"
            )
            
        # If recipient is subscribed, send them the message notification
        if request.recipient in self.active_subscribers:
            try:
                notification = chat_pb2.UpdateNotification(
                    message_received=chat_pb2.MessageReceived(
                        message_id=message_id,
                        sender=request.sender,
                        content=request.content,
                        timestamp=datetime.now().isoformat()
                    )
                )
                self.active_subscribers[request.recipient].send(notification)
                # Mark as read since recipient is online
                self.db.mark_message_read(message_id)
            except Exception as e:
                logging.error(f"Failed to send notification: {e}")
        
        return chat_pb2.SendMessageResponse(
            success=True,
            message="Message sent",
            message_id=message_id
        )

    def LoadUnreadMessages(self, request, context):
        # Authenticate user
        username = self._authenticate(context)
        if username != request.username:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
            
        messages = self.db.get_messages(username, unread_only=True)
        
        if messages:
            # Mark messages as read after retrieving
            self.db.mark_messages_read(username)
            
        return chat_pb2.LoadMessagesResponse(
            messages=[
                chat_pb2.Message(
                    id=msg['id'],
                    sender=msg['sender'],
                    content=msg['message'],
                    timestamp=msg['timestamp']
                ) for msg in messages
            ]
        )

    def DeleteMessage(self, request, context):
        # Authenticate user
        username = self._authenticate(context)
        if username != request.username:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
            
        message = self.db.get_message(request.message_id)
        if not message or message['sender'] != username:
            return chat_pb2.StatusResponse(
                success=False,
                message="Message not found or unauthorized"
            )
            
        self.db.delete_message(request.message_id)
        recipient = message['recipient']
        
        # Notify recipient if they're subscribed
        if recipient in self.active_subscribers:
            try:
                notification = chat_pb2.UpdateNotification(
                    message_deleted=chat_pb2.MessageDeleted(
                        message_id=request.message_id
                    )
                )
                self.active_subscribers[recipient].send(notification)
            except Exception:
                pass
                
        return chat_pb2.StatusResponse(
            success=True,
            message="Message deleted"
        )

    def DeleteAccount(self, request, context):
        # Authenticate user
        username = self._authenticate(context)
        if username != request.username:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
            
        if not self.db.verify_account(request.username, request.password):
            return chat_pb2.StatusResponse(
                success=False,
                message="Invalid credentials"
            )
            
        self.db.delete_account(request.username)
        
        # Remove session
        session_ids_to_remove = [sid for sid, uname in self.user_sessions.items() if uname == username]
        for sid in session_ids_to_remove:
            del self.user_sessions[sid]
        
        # Notify all subscribers
        notification = chat_pb2.UpdateNotification(
            account_deleted=chat_pb2.AccountDeleted(
                username=request.username
            )
        )
        
        for subscriber in self.active_subscribers.values():
            try:
                subscriber.send(notification)
            except Exception:
                pass
                
        return chat_pb2.StatusResponse(
            success=True,
            message="Account deleted"
        )

    def SubscribeToUpdates(self, request, context):
        """Handle subscription requests"""
        try:
            # Authenticate user
            username = self._authenticate(context)
            logging.info(f"Subscribe request from {username}")
            
            # Verify the username matches the authenticated user
            if username != request.username:
                logging.error(f"Username mismatch: {username} != {request.username}")
                context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
            
            # Store the subscriber
            self.active_subscribers[username] = context
            logging.info(f"Added subscriber: {username}")
            
            # Create a notification queue for this user
            notification_queue = []
            
            try:
                # Keep connection alive and handle new notifications
                while context.is_active():
                    # Sleep briefly to prevent busy waiting
                    time.sleep(1)
                    
                    # Check for new notifications and yield them
                    while notification_queue:
                        yield notification_queue.pop(0)
                    
                    # Yield a heartbeat message to keep the connection alive
                    yield chat_pb2.UpdateNotification()
                
            except Exception as e:
                logging.error(f"Subscription error for {username}: {e}")
            finally:
                # Clean up
                if username in self.active_subscribers:
                    del self.active_subscribers[username]
                    logging.info(f"Removed subscriber: {username}")
                # Clean up session if disconnected (but don't remove all user sessions)
                metadata = dict(context.invocation_metadata())
                session_id = metadata.get('session_id')
                if session_id and session_id in self.user_sessions:
                    del self.user_sessions[session_id]
                    logging.info(f"Cleaned up session for: {username}")
                
        except Exception as e:
            logging.error(f"Error in SubscribeToUpdates: {e}")
            raise

def serve(port=50051):
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 1024 * 1024 * 10),  # 10MB
            ('grpc.max_receive_message_length', 1024 * 1024 * 10)  # 10MB
        ]
    )
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logging.info(f"Server started on port {port}")
    server.wait_for_termination()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    serve()