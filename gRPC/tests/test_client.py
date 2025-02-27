import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import grpc
import logging

# Add the parent directory to the path so we can import the client
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import grpc_client
import chat_pb2
import chat_pb2_grpc

class TestChatClient(unittest.TestCase):
    def setUp(self):
        # Create a mock channel and stub
        self.mock_channel = MagicMock()
        self.mock_stub = MagicMock()
        
        # Patch the grpc.insecure_channel to return our mock channel
        self.channel_patcher = patch('grpc.insecure_channel', return_value=self.mock_channel)
        self.mock_insecure_channel = self.channel_patcher.start()
        
        # Patch the ChatServiceStub to return our mock stub
        self.stub_patcher = patch('chat_pb2_grpc.ChatServiceStub', return_value=self.mock_stub)
        self.mock_chat_service_stub = self.stub_patcher.start()
        
        # Create the client
        self.client = grpc_client.ChatClient(host='localhost', port=50051)
        
        # Replace the client's stub with our mock
        self.client.stub = self.mock_stub
    
    def tearDown(self):
        self.channel_patcher.stop()
        self.stub_patcher.stop()
        
        # Stop any subscription thread if running
        if self.client._subscription_thread:
            self.client.stop_subscription()
    
    def test_create_channel(self):
        # Test the _create_channel method
        self.client._create_channel()
        
        # Check that grpc.insecure_channel was called with the correct address
        self.mock_insecure_channel.assert_called_with('localhost:50051')
        
        # Check that ChatServiceStub was called with the channel
        self.mock_chat_service_stub.assert_called_with(self.mock_channel)
        
        # Check that _is_channel_active is True
        self.assertTrue(self.client._is_channel_active)
    
    def test_create_account_success(self):
        # Setup the mock response
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.message = "Account created successfully"
        self.mock_stub.CreateAccount.return_value = mock_response
        
        # Call the method
        result = self.client.create_account("testuser", "password")
        
        # Check that stub method was called with correct request
        request_arg = self.mock_stub.CreateAccount.call_args[0][0]
        self.assertEqual(request_arg.username, "testuser")
        self.assertEqual(request_arg.password, "password")
        
        # Check the result
        self.assertEqual(result, {'status': 'success', 'message': 'Account created successfully'})
    
    def test_create_account_failure(self):
        # Setup the mock response
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.message = "Account exists"
        self.mock_stub.CreateAccount.return_value = mock_response
        
        # Call the method
        result = self.client.create_account("testuser", "password")
        
        # Check the result
        self.assertEqual(result, {'status': 'error', 'message': 'Account exists'})
    
    def test_create_account_error(self):
        # Setup the stub to raise an RpcError
        self.mock_stub.CreateAccount.side_effect = grpc.RpcError("Connection error")
        
        # Call the method
        result = self.client.create_account("testuser", "password")
        
        # Check the result
        self.assertEqual(result, {'status': 'error', 'message': 'Connection error'})
    
    def test_login_success(self):
        # Setup the mock response
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.message = "Login successful"
        mock_response.session_id = "test-session-id"
        self.mock_stub.Login.return_value = mock_response
        
        # Call the method
        result = self.client.login("testuser", "password")
        
        # Check that stub method was called with correct request
        request_arg = self.mock_stub.Login.call_args[0][0]
        self.assertEqual(request_arg.username, "testuser")
        self.assertEqual(request_arg.password, "password")
        
        # Check the result
        self.assertEqual(result, {'status': 'success', 'message': 'Login successful'})
        self.assertEqual(self.client.session_id, "test-session-id")
    
    def test_login_failure(self):
        # Setup the mock response
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.message = "Invalid credentials"
        self.mock_stub.Login.return_value = mock_response
        
        # Call the method
        result = self.client.login("testuser", "wrong-password")
        
        # Check the result
        self.assertEqual(result, {'status': 'error', 'message': 'Invalid credentials'})
        self.assertIsNone(self.client.session_id)
    
    def test_send_message_success(self):
        # Set the session ID
        self.client.session_id = "test-session-id"
        
        # Create a mock session_state with attribute access
        mock_session_state = MagicMock()
        mock_session_state.username = 'testuser'
        
        # Mock session state with proper attribute access
        with patch('streamlit.session_state', mock_session_state):
            # Setup the mock response
            mock_response = MagicMock()
            mock_response.success = True
            mock_response.message = "Message sent"
            self.mock_stub.SendMessage.return_value = mock_response
            
            # Call the method
            result = self.client.send_message("recipient", "Hello!")
            
            # Check that stub method was called with correct request and metadata
            request_arg = self.mock_stub.SendMessage.call_args[0][0]
            metadata_arg = self.mock_stub.SendMessage.call_args[1]['metadata']
            
            self.assertEqual(request_arg.sender, "testuser")
            self.assertEqual(request_arg.recipient, "recipient")
            self.assertEqual(request_arg.content, "Hello!")
            self.assertEqual(metadata_arg, [('session_id', 'test-session-id')])
            
            # Check the result
            self.assertEqual(result, {'status': 'success', 'message': 'Message sent'})
    
    def test_send_message_not_authenticated(self):
        # Set the session ID to None
        self.client.session_id = None
        
        # Call the method
        result = self.client.send_message("recipient", "Hello!")
        
        # Verify that SendMessage was not called
        self.mock_stub.SendMessage.assert_not_called()
        
        # Check the result
        self.assertEqual(result, {'status': 'error', 'message': 'Not authenticated'})
    
    def test_logout(self):
        # Mock the subscription thread
        self.client._subscription_thread = MagicMock()
        self.client.session_id = "test-session-id"
        
        # Call the method
        self.client.logout()
        
        # Check that channel was closed
        self.mock_channel.close.assert_called_once()
        
        # Check that subscription was stopped
        self.assertTrue(self.client._stop_subscription.is_set())
        
        # Check that session_id was cleared
        self.assertIsNone(self.client.session_id)
        self.assertFalse(self.client._is_channel_active)
        
    def test_payload_sizes(self):
        """Test and compare payload sizes between gRPC and equivalent JSON"""
        
        # Test case 1: Account Creation
        grpc_request = chat_pb2.CreateAccountRequest(
            username="testuser",
            password="testpass"
        )
        json_payload = {
            "action": "create",
            "username": "testuser",
            "password": "testpass"
        }
        
        grpc_size = len(grpc_request.SerializeToString())
        json_size = len(str(json_payload).encode('utf-8'))
        
        # Test case 2: Send Message with longer content
        message_content = "Hello, this is a test message with some typical content!"
        grpc_msg_request = chat_pb2.SendMessageRequest(
            sender="testuser",
            recipient="recipient",
            content=message_content
        )
        json_msg_payload = {
            "action": "send",
            "sender": "testuser",
            "recipient": "recipient",
            "message": message_content
        }
        
        grpc_msg_size = len(grpc_msg_request.SerializeToString())
        json_msg_size = len(str(json_msg_payload).encode('utf-8'))
        
        # Test case 3: List Accounts with multiple accounts
        account_list = [
            chat_pb2.AccountInfo(username="user1", unread_count=5),
            chat_pb2.AccountInfo(username="user2", unread_count=3),
            chat_pb2.AccountInfo(username="user3", unread_count=0)
        ]
        grpc_list_response = chat_pb2.ListAccountsResponse(accounts=account_list)
        
        json_list_payload = {
            "status": "success",
            "accounts": [
                {"username": "user1", "unread_count": 5},
                {"username": "user2", "unread_count": 3},
                {"username": "user3", "unread_count": 0}
            ]
        }
        
        grpc_list_size = len(grpc_list_response.SerializeToString())
        json_list_size = len(str(json_list_payload).encode('utf-8'))
        
        # Log and assert results
        logging.info(f"""
        Payload Size Comparison:
        
        1. Account Creation:
        gRPC: {grpc_size} bytes
        JSON: {json_size} bytes
        Difference: {json_size - grpc_size} bytes ({(json_size/grpc_size - 1)*100:.1f}% larger)
        
        2. Send Message:
        gRPC: {grpc_msg_size} bytes
        JSON: {json_msg_size} bytes
        Difference: {json_msg_size - grpc_msg_size} bytes ({(json_msg_size/grpc_msg_size - 1)*100:.1f}% larger)
        
        3. List Accounts:
        gRPC: {grpc_list_size} bytes
        JSON: {json_list_size} bytes
        Difference: {json_list_size - grpc_list_size} bytes ({(json_list_size/grpc_list_size - 1)*100:.1f}% larger)
        """)
        
        # Assert that gRPC payloads are smaller
        self.assertLess(grpc_size, json_size, "gRPC payload should be smaller for account creation")
        self.assertLess(grpc_msg_size, json_msg_size, "gRPC payload should be smaller for sending messages")
        self.assertLess(grpc_list_size, json_list_size, "gRPC payload should be smaller for listing accounts")

if __name__ == '__main__':
    unittest.main()
