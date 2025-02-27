import grpc
import chat_pb2
import chat_pb2_grpc
from typing import Dict, Optional
import streamlit as st

class ChatClient:
    def __init__(self, host='localhost', port=50051):
        self._host = host
        self._port = port
        self._create_channel()
        self.session_id: Optional[str] = None
        self._is_channel_active = True

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

    def logout(self):
        """Close the gRPC channel."""
        try:
            self.channel.close()
        except:
            pass
        self._is_channel_active = False
        self.session_id = None
