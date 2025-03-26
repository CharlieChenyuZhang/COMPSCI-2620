import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import grpc

# Add the parent directory to the path so we can import the client
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import grpc_client
import chat_pb2
import chat_pb2_grpc

# Define a FakeRpcError that implements code() for testing purposes.
class FakeRpcError(grpc.RpcError):
    def __init__(self, message, code_value):
        self._message = message
        self._code_value = code_value
        super().__init__()

    def code(self):
        return self._code_value

    def __str__(self):
        return self._message

class TestChatClient(unittest.TestCase):
    def setUp(self):
        # Create a mock channel and stub
        self.mock_channel = MagicMock()
        self.mock_stub = MagicMock()
        
        # Patch grpc.insecure_channel to return our mock channel
        self.channel_patcher = patch('grpc.insecure_channel', return_value=self.mock_channel)
        self.mock_insecure_channel = self.channel_patcher.start()
        
        # Patch ChatServiceStub to return our mock stub
        self.stub_patcher = patch('chat_pb2_grpc.ChatServiceStub', return_value=self.mock_stub)
        self.mock_chat_service_stub = self.stub_patcher.start()
        
        # Patch _connect_to_server to bypass real socket-level connectivity checks.
        self.connect_patch = patch.object(grpc_client.ChatClient, '_connect_to_server', return_value=True)
        self.mock_connect = self.connect_patch.start()
        
        # Create the client with known_ports set to [50051]
        self.client = grpc_client.ChatClient(host='localhost', known_ports=[50051])
        
        # Force the client's channel state as active and set _port manually.
        self.client._is_channel_active = True
        self.client._port = 50051
        # Also, set a dummy channel and stub (so _create_channel works as expected)
        self.client.channel = self.mock_channel
        self.client.stub = self.mock_stub
    
    def tearDown(self):
        self.channel_patcher.stop()
        self.stub_patcher.stop()
        self.connect_patch.stop()
        
        # Stop any subscription thread if running
        if self.client._subscription_thread:
            self.client.stop_subscription()
    
    def test_create_channel(self):
        # Set the current port so that _create_channel uses 'localhost:50051'
        self.client._port = 50051
        self.client._create_channel()
        
        # Instead of asserting the full call, verify that the first argument is correct.
        call_args = self.mock_insecure_channel.call_args
        self.assertEqual(call_args[0][0], 'localhost:50051')
        
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
        
        # Check the result and that session_id is stored
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
        
        # Check the result and that session_id is cleared
        self.assertEqual(result, {'status': 'error', 'message': 'Invalid credentials'})
        self.assertIsNone(self.client.session_id)
    
    def test_send_message_success(self):
        # Set the session ID
        self.client.session_id = "test-session-id"
        
        # Create a mock session_state with attribute access
        mock_session_state = MagicMock()
        mock_session_state.username = 'testuser'
        
        # Patch streamlit.session_state with our mock
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
        
        # Check that channel.close was called
        self.mock_channel.close.assert_called_once()
        
        # Check that subscription stop event is set
        self.assertTrue(self.client._stop_subscription.is_set())
        
        # Check that session_id was cleared and channel marked inactive
        self.assertIsNone(self.client.session_id)
        self.assertFalse(self.client._is_channel_active)

if __name__ == '__main__':
    unittest.main()
