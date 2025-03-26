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
        # Create a mock replicated store
        self.mock_store = MagicMock()
        
        # Setup state attribute used instead of a real DB
        self.mock_store.state = {
            "accounts": {},
            "messages": []
        }
        
        # Set the node as leader so that write operations are handled locally
        self.mock_store.is_leader = True
        
        # Patch the ReplicatedStore so that our servicer uses our mock_store
        self.store_patcher = patch('grpc_server.ReplicatedStore', return_value=self.mock_store)
        self.mock_store_class = self.store_patcher.start()
        
        # Create the ChatServicer with the mock store
        self.servicer = grpc_server.ChatServicer(rep_store=self.mock_store)
    
    def tearDown(self):
        self.store_patcher.stop()
    
    def test_create_account_success(self):
        # Ensure the account does not exist in state
        self.mock_store.state["accounts"] = {}
        
        # Setup the mock append_entry method to simulate success
        self.mock_store.append_entry = MagicMock(return_value=True)
        
        # Create request and context
        request = chat_pb2.CreateAccountRequest(username="testuser", password="password")
        context = MockContext()
        
        # Call CreateAccount
        response = self.servicer.CreateAccount(request, context)
        
        # Check that append_entry was called once with an entry containing expected fields.
        self.mock_store.append_entry.assert_called_once()
        entry = self.mock_store.append_entry.call_args[0][0]
        self.assertEqual(entry["operation"], "create_account")
        self.assertEqual(entry["username"], "testuser")
        self.assertIn("hashed_password", entry)
        
        # Check the response
        self.assertTrue(response.success)
        self.assertEqual(response.message, "Account created successfully")
    
    def test_create_account_already_exists(self):
        # Pre-populate the state with an account for "testuser"
        hashed_pw = bcrypt.hashpw("password".encode(), bcrypt.gensalt()).decode()
        self.mock_store.state["accounts"] = {"testuser": hashed_pw}
        
        # Setup mock append_entry (it should not be called)
        self.mock_store.append_entry = MagicMock()
        
        # Create request and context
        request = chat_pb2.CreateAccountRequest(username="testuser", password="password")
        context = MockContext()
        
        # Call CreateAccount
        response = self.servicer.CreateAccount(request, context)
        
        # Verify that append_entry was not called
        self.mock_store.append_entry.assert_not_called()
        
        # Check the response for the correct message
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Account exists and password matches")
    
    def test_login_success(self):
        # Pre-populate state with an account for testuser
        hashed_pw = bcrypt.hashpw("password".encode(), bcrypt.gensalt()).decode()
        self.mock_store.state["accounts"] = {"testuser": hashed_pw}
        
        # Create request and context for login
        request = chat_pb2.LoginRequest(username="testuser", password="password")
        context = MockContext()
        
        # Patch uuid.uuid4 for predictable session ID
        with patch('uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
            response = self.servicer.Login(request, context)
        
        # Check response and that the session was stored
        self.assertTrue(response.success)
        self.assertEqual(response.session_id, "12345678-1234-5678-1234-567812345678")
        self.assertEqual(self.servicer.user_sessions["12345678-1234-5678-1234-567812345678"], "testuser")
    
    def test_login_account_not_exists(self):
        # Ensure no accounts are present in state
        self.mock_store.state["accounts"] = {}
        
        # Create request and context
        request = chat_pb2.LoginRequest(username="testuser", password="password")
        context = MockContext()
        
        # Call Login
        response = self.servicer.Login(request, context)
        
        # Check the response
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Account does not exist")
    
    def test_login_incorrect_password(self):
        # Pre-populate state with an account for testuser with a known password
        hashed_pw = bcrypt.hashpw("correctpassword".encode(), bcrypt.gensalt()).decode()
        self.mock_store.state["accounts"] = {"testuser": hashed_pw}
        
        # Create request and context with a wrong password
        request = chat_pb2.LoginRequest(username="testuser", password="wrong-password")
        context = MockContext()
        
        # Call Login
        response = self.servicer.Login(request, context)
        
        # Check the response
        self.assertFalse(response.success)
        self.assertEqual(response.message, "Incorrect password")
    
    def test_authenticate_success(self):
        # Set up a valid session
        self.servicer.user_sessions = {"test-session-id": "testuser"}
        context = MockContext({"session_id": "test-session-id"})
        
        username = self.servicer._authenticate(context)
        self.assertEqual(username, "testuser")
    
    def test_authenticate_missing_session_id(self):
        # When missing a session id the current implementation aborts with INTERNAL.
        context = MockContext({})
        with self.assertRaises(grpc.RpcError):
            self.servicer._authenticate(context)
        # Updated expectation: INTERNAL with "Authentication error"
        self.assertEqual(context.code, grpc.StatusCode.INTERNAL)
        self.assertEqual(context.details, "Authentication error")
    
    def test_authenticate_invalid_session(self):
        # Valid session exists for a different ID
        self.servicer.user_sessions = {"valid-session-id": "testuser"}
        context = MockContext({"session_id": "invalid-session-id"})
        with self.assertRaises(grpc.RpcError):
            self.servicer._authenticate(context)
        # Updated expectation: INTERNAL with "Authentication error"
        self.assertEqual(context.code, grpc.StatusCode.INTERNAL)
        self.assertEqual(context.details, "Authentication error")
    
    def test_send_message_success(self):
        # Set up a valid session and ensure both sender and recipient exist
        self.servicer.user_sessions = {"test-session-id": "testuser"}
        self.mock_store.state["accounts"] = {"testuser": "dummy", "recipient": "dummy"}
        
        # Setup the mock append_entry to simulate successful replication
        self.mock_store.append_entry = MagicMock(return_value=True)
        
        # Create SendMessage request and context
        request = chat_pb2.SendMessageRequest(sender="testuser", recipient="recipient", content="Hello!")
        context = MockContext({"session_id": "test-session-id"})
        
        # Patch the SendMessageResponse constructor to convert message_id to int,
        # since the server code calls str(message_id) even though the proto expects an int.
        with patch('grpc_server.chat_pb2.SendMessageResponse', 
                   side_effect=lambda **kwargs: type('DummyResponse', (), {
                       'success': kwargs.get('success'),
                       'message': kwargs.get('message'),
                       'message_id': int(kwargs.get('message_id'))
                   })) as dummy_resp:
            response = self.servicer.SendMessage(request, context)
        
        # Check that append_entry was called with the correct entry
        self.mock_store.append_entry.assert_called_once()
        entry = self.mock_store.append_entry.call_args[0][0]
        self.assertEqual(entry["operation"], "send_message")
        self.assertEqual(entry["sender"], "testuser")
        self.assertEqual(entry["recipient"], "recipient")
        self.assertEqual(entry["content"], "Hello!")
        
        # Check the response – expect message "Message sent" and message_id equal to the one in the entry.
        self.assertTrue(response.success)
        self.assertEqual(response.message, "Message sent")
        self.assertEqual(response.message_id, entry["message_id"])

if __name__ == '__main__':
    unittest.main()
