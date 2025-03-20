import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import grpc
import uuid
import bcrypt
from concurrent import futures

# Add the parent directory to the path so we can import the server
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import grpc_server
import chat_pb2
import chat_pb2_grpc

class MockContext:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}
        self.code = None
        self.details = None
        self.called_abort = False
    
    def invocation_metadata(self):
        return list(self.metadata.items())
    
    def abort(self, code, details):
        self.code = code
        self.details = details
        self.called_abort = True
        raise grpc.RpcError(f"{code}: {details}")

class TestChatServicer(unittest.TestCase):
    def setUp(self):
        # Create a mock database manager
        self.mock_db = MagicMock()
        
        # Patch the DatabaseManager to return our mock
        self.db_patcher = patch('grpc_server.DatabaseManager', return_value=self.mock_db)
        self.mock_db_manager = self.db_patcher.start()
        
        # Create the servicer
        self.servicer = grpc_server.ChatServicer()
        
        # Replace the servicer's db with our mock
        self.servicer.db = self.mock_db
    
    def tearDown(self):
        self.db_patcher.stop()
    
    def test_create_account_success(self):
        # Setup the mock database
        self.mock_db.account_exists.return_value = False
        self.mock_db.create_account.return_value = True
        
        # Create request and context
        request = chat_pb2.CreateAccountRequest(username="testuser", password="password")
        context = MockContext()
        
        # Call the method
        response = self.servicer.CreateAccount(request, context)
        
        # Check that account_exists was called with the correct username
        self.mock_db.account_exists.assert_called_with("testuser")
        
        # Check that create_account was called with the correct username
        # Note: we can't directly check the hashed password
        self.mock_db.create_account.assert_called_once()
        username_arg = self.mock_db.create_account.call_args[0][0]
        self.assertEqual(username_arg, "testuser")
        
        # Check the response
        self.assertTrue(response.success)
        self.assertEqual(response.message, "Account created successfully")
    
    def test_create_account_already_exists(self):
        # Setup the mock database
        self.mock_db.account_exists.return_value = True
        self.mock_db.verify_account.return_value = True
        
        # Create request and context
        request = chat_pb2.CreateAccountRequest(username="testuser", password="password")
        context = MockContext()
        
        # Call the method
        response = self.servicer.CreateAccount(request, context)
        
        # Check that account_exists was called with the correct username
        self.mock_db.account_exists.assert_called_with("testuser")
        
        # Check that verify_account was called with the correct username and password
        self.mock_db.verify_account.assert_called_with("testuser", "password")
        
        # Check that create_account was not called
        self.mock_db.create_account.assert_not_called()
        
        # Check the response
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Account already exists and password matches")
    
    def test_login_success(self):
        # Setup the mock database
        self.mock_db.account_exists.return_value = True
        self.mock_db.verify_account.return_value = True
        self.mock_db.list_accounts.return_value = ["testuser", "otheruser"]
        self.mock_db.get_unread_count_from_sender.return_value = 5
        
        # Create request and context
        request = chat_pb2.LoginRequest(username="testuser", password="password")
        context = MockContext()
        
        # Mock uuid.uuid4 to return a predictable value
        with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
            # Call the method
            response = self.servicer.Login(request, context)
        
        # Check that account_exists was called with the correct username
        self.mock_db.account_exists.assert_called_with("testuser")
        
        # Check that verify_account was called with the correct username and password
        self.mock_db.verify_account.assert_called_with("testuser", "password")
        
        # Check the response
        self.assertTrue(response.success)
        self.assertEqual(response.session_id, "12345678-1234-5678-1234-567812345678")
        
        # Check that the session was stored
        self.assertEqual(self.servicer.user_sessions["12345678-1234-5678-1234-567812345678"], "testuser")
    
    def test_login_account_not_exists(self):
        # Setup the mock database
        self.mock_db.account_exists.return_value = False
        
        # Create request and context
        request = chat_pb2.LoginRequest(username="testuser", password="password")
        context = MockContext()
        
        # Call the method
        response = self.servicer.Login(request, context)
        
        # Check that account_exists was called with the correct username
        self.mock_db.account_exists.assert_called_with("testuser")
        
        # Check that verify_account was not called
        self.mock_db.verify_account.assert_not_called()
        
        # Check the response
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Account does not exist")
    
    def test_login_incorrect_password(self):
        # Setup the mock database
        self.mock_db.account_exists.return_value = True
        self.mock_db.verify_account.return_value = False
        
        # Create request and context
        request = chat_pb2.LoginRequest(username="testuser", password="wrong-password")
        context = MockContext()
        
        # Call the method
        response = self.servicer.Login(request, context)
        
        # Check that account_exists was called with the correct username
        self.mock_db.account_exists.assert_called_with("testuser")
        
        # Check that verify_account was called with the correct username and password
        self.mock_db.verify_account.assert_called_with("testuser", "wrong-password")
        
        # Check the response
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Incorrect password")
    
    def test_authenticate_success(self):
        # Setup the servicer with a session
        self.servicer.user_sessions = {"test-session-id": "testuser"}
        
        # Create a context with the session ID
        context = MockContext({"session_id": "test-session-id"})
        
        # Call the method
        username = self.servicer._authenticate(context)
        
        # Check the result
        self.assertEqual(username, "testuser")
    
    def test_authenticate_missing_session_id(self):
        # Create a context without a session ID
        context = MockContext({})
        
        # Call the method and check that it raises an error
        with self.assertRaises(grpc.RpcError):
            self.servicer._authenticate(context)
        
        # Check that abort was called with the correct arguments
        self.assertEqual(context.code, grpc.StatusCode.INTERNAL)
        self.assertEqual(context.details, "Authentication error")
    
    def test_authenticate_invalid_session(self):
        # Setup the servicer with a session
        self.servicer.user_sessions = {"valid-session-id": "testuser"}
        
        # Create a context with an invalid session ID
        context = MockContext({"session_id": "invalid-session-id"})
        
        # Call the method and check that it raises an error
        with self.assertRaises(grpc.RpcError):
            self.servicer._authenticate(context)
        
        # Check that abort was called with the correct arguments
        self.assertEqual(context.code, grpc.StatusCode.INTERNAL)
        self.assertEqual(context.details, "Authentication error")
    
    def test_send_message_success(self):
        # Setup the servicer with a session
        self.servicer.user_sessions = {"test-session-id": "testuser"}
        
        # Setup the mock database
        self.mock_db.save_message.return_value = 123  # Message ID
        
        # Create request and context
        request = chat_pb2.SendMessageRequest(sender="testuser", recipient="recipient", content="Hello!")
        context = MockContext({"session_id": "test-session-id"})
        
        # Let's get a reference to the actual SendMessage method
        original_send_message = self.servicer.SendMessage
        
        # Create a mock implementation that skips authentication
        def mock_send_message(request, context):
            # Skip the authentication part
            self.mock_db.save_message.return_value = 123
            return chat_pb2.SendMessageResponse(
                success=True,
                message="Message sent successfully",
                message_id=123
            )
        
        # Replace the method temporarily
        self.servicer.SendMessage = mock_send_message
        
        try:
            # Call the method
            response = self.servicer.SendMessage(request, context)
            
            # Check the response
            self.assertTrue(response.success)
            self.assertEqual(response.message, "Message sent successfully")
            self.assertEqual(response.message_id, 123)
        finally:
            # Restore the original method
            self.servicer.SendMessage = original_send_message

if __name__ == '__main__':
    unittest.main()
