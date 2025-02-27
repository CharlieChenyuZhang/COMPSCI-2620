import grpc
import chat_pb2
import chat_pb2_grpc
from typing import Dict, Optional
import streamlit as st
import threading
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatClient:
    def __init__(self, host='localhost', port=50051):
        self._host = host
        self._port = port
        self._create_channel()
        self.session_id: Optional[str] = None
        self._is_channel_active = True
        self._subscription_thread = None
        self._stop_subscription = threading.Event()

    def _create_channel(self):
        """Create a new gRPC channel and stub"""
        self.channel = grpc.insecure_channel(f'{self._host}:{self._port}')
        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
        self._is_channel_active = True

    def _ensure_channel(self):
        """Ensure channel is active, recreate if needed"""
        if not self._is_channel_active:
            self._create_channel()

    def _add_session_metadata(self) -> Optional[list]:
        return [('session_id', self.session_id)] if self.session_id else None

    def create_account(self, username: str, password: str) -> Dict:
        request = chat_pb2.CreateAccountRequest(username=username, password=password)
        try:
            response = self.stub.CreateAccount(request)
            return {'status': 'success' if response.success else 'error', 'message': response.message}
        except grpc.RpcError as e:
            return {'status': 'error', 'message': str(e)}

    def login(self, username: str, password: str) -> Dict:
        self._ensure_channel()
        request = chat_pb2.LoginRequest(username=username, password=password)
        try:
            response = self.stub.Login(request)
            if response.success:
                self.session_id = response.session_id
            return {'status': 'success' if response.success else 'error', 'message': response.message}
        except grpc.RpcError as e:
            return {'status': 'error', 'message': str(e)}

    def send_message(self, recipient: str, content: str) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
        request = chat_pb2.SendMessageRequest(
            sender=st.session_state.username,
            recipient=recipient,
            content=content
        )
        try:
            response = self.stub.SendMessage(request, metadata=self._add_session_metadata())
            return {'status': 'success' if response.success else 'error', 'message': response.message}
        except grpc.RpcError as e:
            return {'status': 'error', 'message': str(e)}

    def read_messages(self, other_user: str) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
        request = chat_pb2.LoadMessagesRequest(
            username=st.session_state.username,
            other_user=other_user
        )
        try:
            response = self.stub.LoadUnreadMessages(request, metadata=self._add_session_metadata())
            return {
                'status': 'success',
                'messages': [{'id': msg.id, 'sender': msg.sender, 'content': msg.content, 'timestamp': msg.timestamp} for msg in response.messages]
            }
        except grpc.RpcError as e:
            return {'status': 'error', 'message': str(e)}

    def list_accounts(self, pattern: str = "*", username: str = None) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
        request = chat_pb2.ListAccountsRequest(pattern=pattern, username=username)
        try:
            response = self.stub.ListAccounts(request, metadata=self._add_session_metadata())
            return [{'username': acc.username, 'unread_count': acc.unread_count} for acc in response.accounts]
        except grpc.RpcError as e:
            return []

    def delete_account(self, username: str, password: str) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
        request = chat_pb2.DeleteAccountRequest(username=username, password=password)
        try:
            response = self.stub.DeleteAccount(request, metadata=self._add_session_metadata())
            return {'status': 'success' if response.success else 'error', 'message': response.message}
        except grpc.RpcError as e:
            return {'status': 'error', 'message': str(e)}

    def subscribe_to_updates(self):
        """Subscribe to real-time updates"""
        if not self.session_id:
            logger.warning("Cannot subscribe without session ID")
            return
            
        # Capture username from session state before starting thread
        username = st.session_state.username
        
        def update_stream():
            try:
                request = chat_pb2.SubscribeRequest(username=username)
                logger.info(f"Starting subscription for user: {username} with session_id: {self.session_id}")
                
                # Add session metadata to the subscription request
                metadata = self._add_session_metadata()
                if not metadata:
                    logger.error("No session metadata available")
                    return
                    
                for update in self.stub.SubscribeToUpdates(
                    request, 
                    metadata=metadata
                ):
                    if self._stop_subscription.is_set():
                        logger.info("Subscription stopped")
                        break
                        
                    if update.HasField('message_received'):
                        msg = update.message_received
                        logger.info(f"Received new message from: {msg.sender}")
                        
                        # Store the message in session state
                        if 'chat_messages' not in st.session_state:
                            st.session_state.chat_messages = {}
                        
                        if msg.sender not in st.session_state.chat_messages:
                            st.session_state.chat_messages[msg.sender] = []
                            
                        st.session_state.chat_messages[msg.sender].append({
                            'id': msg.message_id,
                            'sender': msg.sender,
                            'content': msg.content,
                            'timestamp': msg.timestamp
                        })
                        
                        # Queue the message update for the main thread
                        st.experimental_rerun()
                    
                    elif update.HasField('message_deleted'):
                        msg_id = update.message_deleted.message_id
                        logger.info(f"Message deleted: {msg_id}")
                        st.experimental_rerun()
                    
                    elif update.HasField('account_deleted'):
                        deleted_user = update.account_deleted.username
                        logger.info(f"Account deleted: {deleted_user}")
                        st.experimental_rerun()
            
            except grpc.RpcError as e:
                if not self._stop_subscription.is_set():
                    logger.error(f"Subscription error: {e}")
                    if 'Not authorized' in str(e):
                        logger.error(f"Authorization failed for user: {username}")
                    self._is_channel_active = False
            except Exception as e:
                logger.error(f"Unexpected error in subscription: {e}")

        # Start subscription in a separate thread
        self._stop_subscription.clear()
        self._subscription_thread = threading.Thread(target=update_stream, daemon=True)
        self._subscription_thread.start()
        logger.info("Subscription thread started")

    def stop_subscription(self):
        """Stop the subscription thread"""
        if self._subscription_thread:
            logger.info("Stopping subscription thread")
            self._stop_subscription.set()
            self._subscription_thread.join(timeout=2)  # Wait up to 2 seconds
            self._subscription_thread = None

    def logout(self):
        """Close the gRPC channel."""
        logger.info("Logging out and cleaning up")
        self.stop_subscription()  # Stop subscription before closing channel
        try:
            self.channel.close()
        except Exception as e:
            logger.error(f"Error closing channel: {e}")
        self._is_channel_active = False
        self.session_id = None
