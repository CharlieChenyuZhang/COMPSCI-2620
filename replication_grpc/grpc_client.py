import grpc
import chat_pb2
import chat_pb2_grpc
from typing import Dict, Optional, List
import streamlit as st
import threading
import logging
from datetime import datetime
import re
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatClient:
    def __init__(self, host='localhost', known_ports=None, max_port_attempts=8):
        self._host = host
        if known_ports is None:
            self._known_ports = [50051, 50061, 50071]  # Default known ports
        else:
            self._known_ports = known_ports
            
        self._current_port_idx = 0
        self._max_port_attempts = max_port_attempts
        self._tried_ports = set()
        self._leader_port = None
        self._port = self._known_ports[self._current_port_idx]
        self.session_id: Optional[str] = None
        self._is_channel_active = False
        self._subscription_thread = None
        self._stop_subscription = threading.Event()
        self._connect_to_server()

    def _connect_to_server(self):
        """Try to connect to a server, first attempting known ports then exploring others"""
        # Track known dead servers to avoid re-trying too quickly
        if not hasattr(self, '_dead_servers'):
            self._dead_servers = {}  # port -> timestamp when detected dead
        
        # Clean up old dead server entries (older than 30 seconds)
        current_time = time.time()
        for port in list(self._dead_servers.keys()):
            if current_time - self._dead_servers[port] > 30:
                del self._dead_servers[port]
                
        # First try the leader port if we know it
        if self._leader_port is not None:
            if self._leader_port not in self._dead_servers:
                logger.info(f"Trying known leader at port {self._leader_port}")
                if self._try_connect(self._leader_port):
                    return True
                else:
                    logger.warning(f"Known leader at port {self._leader_port} is not responsive")
                    self._dead_servers[self._leader_port] = current_time
                    self._leader_port = None
        
        # Reset tried ports - we want to try all known ports in order
        self._tried_ports.clear()
        
        # Try round-robin on known ports, skipping recently detected dead servers
        attempts = 0
        max_attempts = self._max_port_attempts
        
        # Save original starting index to avoid infinite loop
        starting_idx = self._current_port_idx
        tried_count = 0
        
        while attempts < max_attempts:
            # Get the next port to try
            if tried_count < len(self._known_ports):
                port = self._known_ports[self._current_port_idx]
                
                # Move to next port for next attempt, wrapping around if needed
                self._current_port_idx = (self._current_port_idx + 1) % len(self._known_ports)
                tried_count += 1
                
                # If we've tried all known ports and come back to starting point, move to discovery
                if self._current_port_idx == starting_idx and tried_count >= len(self._known_ports):
                    tried_count = len(self._known_ports)  # Move to discovery phase
                    
                # Skip ports we know are dead
                if port in self._dead_servers:
                    attempts += 1
                    continue
                    
                logger.info(f"Trying known port {port} (attempt {attempts+1}/{max_attempts})")
            else:
                # Try discovery ports
                if attempts == len(self._known_ports):
                    port = max(self._known_ports) + 10
                else:
                    port += 10
                    
                # Skip ports we know are dead
                if port in self._dead_servers:
                    attempts += 1
                    continue
                    
                logger.info(f"Trying discovery port {port} (attempt {attempts+1}/{max_attempts})")
            
            # Skip already tried ports
            if port in self._tried_ports:
                attempts += 1
                continue
                
            self._tried_ports.add(port)
            if self._try_connect(port):
                return True
                
            # Mark port as dead if connection failed
            self._dead_servers[port] = current_time
            
            attempts += 1
            time.sleep(0.2)  # Shorter delay between connection attempts
            
        logger.error(f"Failed to connect to any server after {max_attempts} attempts")
        return False

    def _try_connect(self, port):
        """Try to connect to a specific port with more robust connection validation"""
        try:
            logger.info(f"Attempting to connect to {self._host}:{port}")
            self._port = port
            
            # First do a quick socket-level check
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)  # Short timeout for quick checking
                result = s.connect_ex((self._host, port))
                
                # If connection fails, don't even try gRPC
                if result != 0:
                    logger.warning(f"Socket-level connection failed for {self._host}:{port}")
                    s.close()
                    self._is_channel_active = False
                    return False
                    
                # Try to send some data to check if socket is actually responsive
                try:
                    s.send(b'\x00')
                    s.settimeout(0.2)
                    try:
                        s.recv(1)
                    except socket.timeout:
                        # Expected timeout, socket appears working
                        pass
                except (ConnectionRefusedError, BrokenPipeError) as e:
                    logger.warning(f"Socket communication failed for {self._host}:{port}: {e}")
                    s.close()
                    self._is_channel_active = False
                    return False
                    
                s.close()
            except Exception as e:
                logger.warning(f"Socket check error for {self._host}:{port}: {e}")
                self._is_channel_active = False
                return False
            
            # Create channel with lower timeouts to detect suspended servers faster
            try:
                self.channel = grpc.insecure_channel(
                    f'{self._host}:{self._port}',
                    options=[
                        ('grpc.keepalive_time_ms', 5000),
                        ('grpc.keepalive_timeout_ms', 1000),
                        ('grpc.http2.min_time_between_pings_ms', 5000),
                        ('grpc.keepalive_permit_without_calls', True),
                        ('grpc.max_connection_idle_ms', 5000),
                        ('grpc.max_connection_age_ms', 10000),
                        ('grpc.client_idle_timeout_ms', 3000),
                        ('grpc.connect_timeout_ms', 1000),  # 1 second connection timeout
                    ]
                )
                self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
                
                # Use a direct request to check channel readiness instead of get_state
                # which might not be supported in all gRPC versions
                request = chat_pb2.ListAccountsRequest(pattern="*")
                
                # Check connectivity with a very short timeout
                try:
                    # Very short timeout to just check connectivity
                    future = self.stub.ListAccounts.future(request, timeout=0.5)
                    
                    try:
                        future.result(timeout=0.3)
                        # Successfully got a response
                        self._is_channel_active = True
                        logger.info(f"Successfully connected to {self._host}:{port}")
                        return True
                    except grpc.FutureTimeoutError:
                        # Cancel the future to avoid hanging
                        future.cancel()
                        # This doesn't necessarily mean failure - just timeout
                        # For robust connectivity, assume it's still connecting
                        self._is_channel_active = True
                        logger.info(f"Connection to {self._host}:{port} established (request timed out but channel active)")
                        return True
                    except grpc.RpcError as e:
                        # Even certain errors like UNIMPLEMENTED mean the server is there
                        if e.code() in (grpc.StatusCode.UNIMPLEMENTED, 
                                        grpc.StatusCode.UNAUTHENTICATED, 
                                        grpc.StatusCode.PERMISSION_DENIED,
                                        grpc.StatusCode.FAILED_PRECONDITION):
                            logger.info(f"Server at {self._host}:{port} is responsive (returned {e.code()})")
                            self._is_channel_active = True
                            return True
                        else:
                            logger.warning(f"Server at {self._host}:{port} returned error: {e.code()}")
                            self._is_channel_active = False
                            return False
                except Exception as e:
                    # Try one more way to check - a simple unary call without timeout
                    try:
                        # If the first approach failed, try a simpler approach
                        self.stub.ListAccounts(request)
                        self._is_channel_active = True
                        logger.info(f"Successfully connected to {self._host}:{port} (basic check)")
                        return True
                    except grpc.RpcError as e:
                        # Even certain errors are ok - they mean server is there
                        if e.code() in (grpc.StatusCode.UNIMPLEMENTED, 
                                        grpc.StatusCode.UNAUTHENTICATED, 
                                        grpc.StatusCode.PERMISSION_DENIED,
                                        grpc.StatusCode.FAILED_PRECONDITION,
                                        grpc.StatusCode.DEADLINE_EXCEEDED):
                            logger.info(f"Server at {self._host}:{port} is responsive (simple check returned {e.code()})")
                            self._is_channel_active = True
                            return True
                    logger.warning(f"Failed connectivity check for {self._host}:{port}: {e}")
            except Exception as e:
                logger.error(f"Connection error to {self._host}:{port}: {e}")
                self._is_channel_active = False
                return False
            
            # If we've reached here, we weren't definitively successful or unsuccessful
            # Assume the channel is active
            self._is_channel_active = True
            logger.info(f"Connection to {self._host}:{port} assumed active")
            return True
        except Exception as e:
            logger.error(f"Connection error to {self._host}:{port}: {e}")
            self._is_channel_active = False
            return False
                                                
    def _create_channel(self):
        """Create a new gRPC channel and stub"""
        try:
            self.channel = grpc.insecure_channel(
                f'{self._host}:{self._port}',
                options=[
                    ('grpc.keepalive_time_ms', 10000),
                    ('grpc.keepalive_timeout_ms', 5000),
                    ('grpc.keepalive_permit_without_calls', True),
                ]
            )
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
            self._is_channel_active = True
            logger.info(f"Successfully connected to {self._host}:{self._port}")
        except Exception as e:
            logger.error(f"Error creating channel: {e}")
            self._is_channel_active = False

    def _ensure_channel(self):
        """Ensure channel is active, recreate if needed"""
        if not self._is_channel_active:
            return self._connect_to_server()
        return True

    def _handle_rpc_error(self, e):
        """Handle RPC errors, including leadership changes"""
        if e.code() == grpc.StatusCode.FAILED_PRECONDITION:
            if "Not the leader" in e.details():
                # Extract leader port from error message
                match = re.search(r'port (\d+)', e.details())
                if match:
                    leader_port = int(match.group(1))
                    logger.info(f"Switching to leader at port {leader_port}")
                    self._leader_port = leader_port
                    if self._connect_to_server():
                        return True  # Successfully reconnected
                        
            # If we get here, either:
            # 1. No leader info was available in the error
            # 2. We couldn't connect to the identified leader
            # In either case, continue with round-robin
            logger.warning("No leader information available or couldn't connect to leader, trying next server")
            self._leader_port = None
            # Move to next port in the round-robin and clear any faulty port cache
            self._current_port_idx = (self._current_port_idx + 1) % len(self._known_ports)
            self._tried_ports.clear()
            if self._connect_to_server():
                return True
        
        elif e.code() == grpc.StatusCode.INTERNAL:
            logger.warning(f"Server returned internal error: {e.details()}, trying another server")
            # Most likely an authentication error during redirect - try next server
            self._current_port_idx = (self._current_port_idx + 1) % len(self._known_ports)
            self._tried_ports.clear()
            if self._connect_to_server():
                return True
        
        elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
            # For authentication errors in methods like create_account, this is expected
            # Just return False to let the upper layer handle it
            logger.warning(f"Authentication error: {e.details()}")
            return False
                
        self._is_channel_active = False
        return False  # Failed to handle the error

    def _add_session_metadata(self) -> Optional[list]:
        return [('session_id', self.session_id)] if self.session_id else None

    def create_account(self, username: str, password: str) -> Dict:
        if not self._ensure_channel():
            return {'status': 'error', 'message': 'Unable to connect to server'}
            
        request = chat_pb2.CreateAccountRequest(username=username, password=password)
        
        # Try all servers before giving up
        for attempt in range(len(self._known_ports) * 2):
            try:
                response = self.stub.CreateAccount(request)
                return {'status': 'success' if response.success else 'error', 'message': response.message}
            except grpc.RpcError as e:
                logger.warning(f"Server error on attempt {attempt+1}: {e.code()}")
                
                # Force a complete reset of connection state on failure
                if attempt == 0:
                    # First failure, reset everything and try all servers
                    self._is_channel_active = False
                    self._current_port_idx = 0  # Start from the first port again
                    self._tried_ports.clear()
                    self._leader_port = None
                
                if self._handle_rpc_error(e):
                    # _handle_rpc_error succeeded in reconnecting, retry the request
                    continue
                elif attempt >= len(self._known_ports):
                    # We've tried enough servers, return the error
                    return {'status': 'error', 'message': str(e)}
                # Otherwise try the next server
            except Exception as e:
                return {'status': 'error', 'message': f"Unexpected error: {str(e)}"}
                
        return {'status': 'error', 'message': 'Failed to create account after trying all servers'}

    def login(self, username: str, password: str) -> Dict:
        if not self._ensure_channel():
            return {'status': 'error', 'message': 'Unable to connect to server'}
            
        request = chat_pb2.LoginRequest(username=username, password=password)
        
        # Try all servers before giving up (similar to create_account)
        for attempt in range(len(self._known_ports) * 2):
            try:
                response = self.stub.Login(request)
                if response.success:
                    self.session_id = response.session_id
                return {'status': 'success' if response.success else 'error', 'message': response.message}
            except grpc.RpcError as e:
                logger.warning(f"Server error on login attempt {attempt+1}: {e.code()}")
                
                # Force a complete reset of connection state on first failure
                if attempt == 0:
                    self._is_channel_active = False
                    self._current_port_idx = 0  # Start from the first port again
                    self._tried_ports.clear()
                    self._leader_port = None
                    
                if self._handle_rpc_error(e):
                    # Retry if we successfully reconnected
                    continue
                elif attempt >= len(self._known_ports):
                    # We've tried enough servers, return the error
                    return {'status': 'error', 'message': str(e)}
                # Otherwise try the next server
            except Exception as e:
                return {'status': 'error', 'message': f"Unexpected error: {str(e)}"}
                
        return {'status': 'error', 'message': 'Failed to login after trying all servers'}

    def send_message(self, recipient: str, content: str) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
            
        if not self._ensure_channel():
            return {'status': 'error', 'message': 'Unable to connect to server'}
            
        request = chat_pb2.SendMessageRequest(
            sender=st.session_state.username,
            recipient=recipient,
            content=content
        )
        try:
            response = self.stub.SendMessage(request, metadata=self._add_session_metadata())
            return {'status': 'success' if response.success else 'error', 'message': response.message}
        except grpc.RpcError as e:
            if self._handle_rpc_error(e):
                # Retry the request if we successfully reconnected
                return self.send_message(recipient, content)
            return {'status': 'error', 'message': str(e)}

    def read_messages(self, other_user: str) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
            
        if not self._ensure_channel():
            return {'status': 'error', 'message': 'Unable to connect to server'}
            
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
            if self._handle_rpc_error(e):
                # Retry the request if we successfully reconnected
                return self.read_messages(other_user)
            return {'status': 'error', 'message': str(e)}

    def list_accounts(self, pattern: str = "*", username: str = None) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
            
        if not self._ensure_channel():
            return {'status': 'error', 'message': 'Unable to connect to server'}
            
        request = chat_pb2.ListAccountsRequest(pattern=pattern, username=username)
        try:
            response = self.stub.ListAccounts(request, metadata=self._add_session_metadata())
            return [{'username': acc.username, 'unread_count': acc.unread_count} for acc in response.accounts]
        except grpc.RpcError as e:
            if self._handle_rpc_error(e):
                # Retry the request if we successfully reconnected
                return self.list_accounts(pattern, username)
            return []

    def delete_account(self, username: str, password: str) -> Dict:
        if not self.session_id:
            return {'status': 'error', 'message': 'Not authenticated'}
            
        if not self._ensure_channel():
            return {'status': 'error', 'message': 'Unable to connect to server'}
            
        request = chat_pb2.DeleteAccountRequest(username=username, password=password)
        try:
            response = self.stub.DeleteAccount(request, metadata=self._add_session_metadata())
            return {'status': 'success' if response.success else 'error', 'message': response.message}
        except grpc.RpcError as e:
            if self._handle_rpc_error(e):
                # Retry the request if we successfully reconnected
                return self.delete_account(username, password)
            return {'status': 'error', 'message': str(e)}

    def subscribe_to_updates(self):
        """Subscribe to real-time updates"""
        if not self.session_id:
            logger.warning("Cannot subscribe without session ID")
            return
        
        if not self._ensure_channel():
            logger.error("Unable to connect to server for subscription")
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
                    elif "Not the leader" in str(e):
                        # Try to reconnect to the leader
                        self._handle_rpc_error(e)
                        # Try to resubscribe after a short delay
                        time.sleep(2)
                        if self._is_channel_active:
                            self.subscribe_to_updates()
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