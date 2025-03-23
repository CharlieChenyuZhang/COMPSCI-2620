#!/usr/bin/env python3
import grpc
from concurrent import futures
import bcrypt
from datetime import datetime
import logging
import re
import time
import uuid
import sys
import os
import json
import threading
import argparse
import random

# Import generated proto modules.
# These modules are assumed to be generated from your .proto files.
import chat_pb2
import chat_pb2_grpc
import replication_pb2
import replication_pb2_grpc

# -------------------------------
# Replicated Persistent Store with Leader Election
# -------------------------------
class ReplicatedStore:
    """
    A persistent, replicated log for the chat backend with simplified leader election.
    This class loads a persistent log from disk, rebuilds state, and manages election state.
    """
    def __init__(self, node_id, peer_addresses, storage_file, is_leader=False):
        self.node_id = str(node_id)
        self.peer_addresses = peer_addresses  # List of peer replication addresses (e.g., "localhost:50052")
        self.storage_file = storage_file
        self.lock = threading.Lock()

        # Election state variables.
        self.current_term = 0
        self.voted_for = None
        # Role can be "follower", "candidate", or "leader"
        self.role = "leader" if is_leader else "follower"
        self.is_leader = is_leader
        self.last_heartbeat = time.time()

        # Load persistent log and rebuild in-memory state.
        self.log = self.load_log_from_disk()
        self.state = self.rebuild_state_from_log()

        logging.info(f"Node {self.node_id} started; role = {self.role}, leader flag = {self.is_leader}")

        # Start election daemon thread.
        threading.Thread(target=self.election_daemon, daemon=True).start()

    def load_log_from_disk(self):
        """Load the persistent log from disk (if it exists)."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    log_data = json.load(f)
                logging.info(f"Loaded log from {self.storage_file}")
                return log_data
            except Exception as e:
                logging.error(f"Error loading log: {e}")
                return []
        else:
            return []

    def persist_log_to_disk(self):
        """Persist the log to disk."""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.log, f, default=str)
            logging.info(f"Persisted log to {self.storage_file}")
        except Exception as e:
            logging.error(f"Error persisting log: {e}")

    def rebuild_state_from_log(self):
        """
        Rebuild the in-memory state from the log.
        State includes accounts and messages.
        """
        state = {"accounts": {}, "messages": []}
        for entry in self.log:
            op = entry.get("operation")
            if op == "create_account":
                state["accounts"][entry["username"]] = entry["hashed_password"]
            elif op == "delete_account":
                state["accounts"].pop(entry["username"], None)
            elif op == "send_message":
                state["messages"].append(entry)
            elif op == "delete_message":
                state["messages"] = [m for m in state["messages"] if m.get("message_id") != entry["message_id"]]
            # Ignore other operations (e.g., heartbeat) in state rebuilding.
        logging.info("State rebuilt from log.")
        return state

    def quorum_size(self):
        """Compute the required quorum size (including self)."""
        total_nodes = len(self.peer_addresses) + 1
        return total_nodes // 2 + 1

    def send_append_entry(self, peer, entry):
        """Send an AppendEntry RPC to a peer."""
        try:
            channel = grpc.insecure_channel(peer)
            stub = replication_pb2_grpc.ReplicationServiceStub(channel)
            # Convert the entry to JSON, using default=str to handle UUIDs.
            request = replication_pb2.AppendEntryRequest(entry_json=json.dumps(entry, default=str))
            response = stub.AppendEntry(request, timeout=3)
            return response.success
        except Exception as e:
            logging.error(f"Error sending append entry to {peer}: {e}")
            return False

    def append_entry(self, entry):
        """
        Append an entry to the local log and replicate it to peers.
        Only the leader should call this.
        """
        if not self.is_leader:
            raise Exception("Only leader can append log entries")
        with self.lock:
            # Append locally.
            self.log.append(entry)
            self.persist_log_to_disk()

            # Replicate to peers.
            success_count = 1  # Leader counts as a vote.
            for peer in self.peer_addresses:
                if self.send_append_entry(peer, entry):
                    success_count += 1

            if success_count >= self.quorum_size():
                self.commit_entry(entry)
                logging.info(f"Entry committed: {entry}")
                return True
            else:
                logging.error("Failed to replicate entry to a quorum")
                return False

    def commit_entry(self, entry):
        """
        Apply the log entry to the in-memory state.
        (This operation should be idempotent.)
        """
        op = entry.get("operation")
        if op == "create_account":
            self.state["accounts"][entry["username"]] = entry["hashed_password"]
        elif op == "delete_account":
            self.state["accounts"].pop(entry["username"], None)
        elif op == "send_message":
            self.state["messages"].append(entry)
        elif op == "delete_message":
            self.state["messages"] = [m for m in self.state["messages"] if m.get("message_id") != entry["message_id"]]

    # ---------------
    # Leader Election Methods
    # ---------------
    def start_election(self):
        """Trigger an election: become candidate, increment term, and request votes."""
        with self.lock:
            self.role = "candidate"
            self.current_term += 1
            self.voted_for = self.node_id
            vote_count = 1  # Vote for self.
            current_term = self.current_term
            logging.info(f"Node {self.node_id} starting election for term {current_term}")

        # Solicit votes from all peers.
        for peer in self.peer_addresses:
            try:
                channel = grpc.insecure_channel(peer)
                stub = replication_pb2_grpc.ReplicationServiceStub(channel)
                req = replication_pb2.RequestVoteRequest(term=current_term, candidate_id=self.node_id)
                response = stub.RequestVote(req, timeout=3)
                if response.vote_granted:
                    vote_count += 1
            except Exception as e:
                logging.error(f"Error sending RequestVote to {peer}: {e}")

        with self.lock:
            if vote_count >= self.quorum_size():
                self.role = "leader"
                self.is_leader = True
                logging.info(f"Node {self.node_id} became leader for term {self.current_term}")
            else:
                logging.info(f"Node {self.node_id} failed election in term {self.current_term} (got {vote_count} votes)")
                self.role = "follower"
                self.voted_for = None

    def send_heartbeats(self):
        """Send heartbeat messages (via AppendEntry RPC with a 'heartbeat' entry) to all peers."""
        heartbeat_entry = {
            "operation": "heartbeat",
            "term": self.current_term,
            "sender": self.node_id,
            "timestamp": datetime.now().isoformat()
        }
        for peer in self.peer_addresses:
            try:
                channel = grpc.insecure_channel(peer)
                stub = replication_pb2_grpc.ReplicationServiceStub(channel)
                req = replication_pb2.AppendEntryRequest(entry_json=json.dumps(heartbeat_entry))
                stub.AppendEntry(req, timeout=3)
            except Exception as e:
                # logging.error(f"Error sending heartbeat to {peer}: {e}")
                logging.error(f"Cannot send heartbeat to {peer}")

    def election_daemon(self):
        """
        Background thread that monitors heartbeats and triggers elections when needed.
        If this node is leader, it sends heartbeats.
        """
        while True:
            time.sleep(1)
            with self.lock:
                # If not leader, check if heartbeat timeout expired.
                if self.role != "leader":
                    timeout = random.uniform(5, 8)  # Randomized election timeout.
                    if time.time() - self.last_heartbeat > timeout:
                        self.start_election()
                # If leader, send heartbeats periodically.
                elif self.role == "leader":
                    self.send_heartbeats()
            time.sleep(2)

# -------------------------------
# Replication Service
# -------------------------------
class ReplicationServicer(replication_pb2_grpc.ReplicationServiceServicer):
    """
    GRPC service for replication and leader election.
    Provides AppendEntry (including heartbeat handling) and RequestVote RPCs.
    """
    def __init__(self, rep_store: ReplicatedStore):
        self.rep_store = rep_store

    def AppendEntry(self, request, context):
        try:
            entry = json.loads(request.entry_json)
        except Exception as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid entry format")

        with self.rep_store.lock:
            if entry.get("operation") == "heartbeat":
                # Heartbeat message: update last heartbeat and term.
                self.rep_store.last_heartbeat = time.time()
                incoming_term = entry.get("term", 0)
                if incoming_term > self.rep_store.current_term:
                    self.rep_store.current_term = incoming_term
                    self.rep_store.role = "follower"
                    self.rep_store.is_leader = False
            else:
                # Regular log entry: append and commit.
                self.rep_store.log.append(entry)
                self.rep_store.persist_log_to_disk()
                self.rep_store.commit_entry(entry)
        logging.info(f"Appended entry from leader: {entry}")
        return replication_pb2.AppendEntryResponse(success=True)

    def RequestVote(self, request, context):
        candidate_term = request.term
        candidate_id = request.candidate_id
        with self.rep_store.lock:
            # Reject vote if candidate's term is stale.
            if candidate_term < self.rep_store.current_term:
                return replication_pb2.RequestVoteResponse(vote_granted=False, term=self.rep_store.current_term)
            # Grant vote if not voted yet in this term or already voted for this candidate.
            if self.rep_store.voted_for is None or self.rep_store.voted_for == candidate_id:
                self.rep_store.voted_for = candidate_id
                self.rep_store.current_term = candidate_term
                # Reset heartbeat to avoid immediate election.
                self.rep_store.last_heartbeat = time.time()
                logging.info(f"Node {self.rep_store.node_id} voted for candidate {candidate_id} in term {candidate_term}")
                return replication_pb2.RequestVoteResponse(vote_granted=True, term=self.rep_store.current_term)
            else:
                return replication_pb2.RequestVoteResponse(vote_granted=False, term=self.rep_store.current_term)

# -------------------------------
# Chat Service
# -------------------------------
class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    """
    GRPC service for chat functionality.
    Write operations (e.g., SendMessage, CreateAccount) are delegated to the leader replica.
    """
    def __init__(self, rep_store: ReplicatedStore):
        self.rep_store = rep_store
        self.active_subscribers = {}  # Mapping from username to grpc.ServicerContext.
        self.user_sessions = {}       # Mapping from session_id to username.

    def _authenticate(self, context) -> str:
        metadata = dict(context.invocation_metadata())
        session_id = metadata.get('session_id')
        if not session_id or session_id not in self.user_sessions:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid session_id")
        return self.user_sessions[session_id]

    def CreateAccount(self, request, context):
        accounts = self.rep_store.state.get("accounts", {})
        if request.username in accounts:
            stored_hash = accounts[request.username].encode()
            if bcrypt.checkpw(request.password.encode(), stored_hash):
                return chat_pb2.CreateAccountResponse(
                    success=False,
                    message="Account exists and password matches",
                    unread_count=0
                )
            return chat_pb2.CreateAccountResponse(
                success=False,
                message="Account exists but password is incorrect"
            )
        hashed_password = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
        entry = {
            "operation": "create_account",
            "username": request.username,
            "hashed_password": hashed_password,
            "timestamp": datetime.now().isoformat()
        }
        if self.rep_store.is_leader:
            if self.rep_store.append_entry(entry):
                return chat_pb2.CreateAccountResponse(
                    success=True,
                    message="Account created successfully",
                    unread_count=0
                )
            else:
                return chat_pb2.CreateAccountResponse(
                    success=False,
                    message="Failed to replicate account creation"
                )
        else:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader")

    def Login(self, request, context):
        accounts = self.rep_store.state.get("accounts", {})
        if request.username not in accounts:
            return chat_pb2.LoginResponse(success=False, message="Account does not exist")
        if not bcrypt.checkpw(request.password.encode(), accounts[request.username].encode()):
            return chat_pb2.LoginResponse(success=False, message="Incorrect password")
        session_id = str(uuid.uuid4())
        self.user_sessions[session_id] = request.username

        unread_counts = {}
        for msg in self.rep_store.state.get("messages", []):
            if msg.get("recipient") == request.username and not msg.get("read", False):
                sender = msg.get("sender")
                unread_counts[sender] = unread_counts.get(sender, 0) + 1

        return chat_pb2.LoginResponse(
            success=True,
            message="Login successful",
            unread_counts=unread_counts,
            session_id=session_id
        )

    def ListAccounts(self, request, context):
        username = self._authenticate(context)
        accounts = self.rep_store.state.get("accounts", {})
        result_accounts = []
        regex = None
        if request.pattern != '*':
            try:
                regex = re.compile(request.pattern)
            except re.error:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid pattern")
        for acc in accounts:
            if acc != username:
                if regex and not regex.match(acc):
                    continue
                unread_count = sum(
                    1 for msg in self.rep_store.state.get("messages", [])
                    if msg.get("recipient") == username and msg.get("sender") == acc and not msg.get("read", False)
                )
                result_accounts.append(chat_pb2.AccountInfo(username=acc, unread_count=unread_count))
        return chat_pb2.ListAccountsResponse(accounts=result_accounts)

    def SendMessage(self, request, context):
        sender = self._authenticate(context)
        if sender != request.sender:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
        if request.sender == request.recipient:
            return chat_pb2.SendMessageResponse(success=False, message="Cannot send message to yourself")
        accounts = self.rep_store.state.get("accounts", {})
        if request.recipient not in accounts:
            return chat_pb2.SendMessageResponse(success=False, message="Recipient does not exist")
        message_id = uuid.uuid4().int % (1 << 63)
        entry = {
            "operation": "send_message",
            "message_id": message_id,
            "sender": request.sender,
            "recipient": request.recipient,
            "content": request.content,
            "timestamp": datetime.now().isoformat(),
            "read": False
        }
        if self.rep_store.is_leader:
            if self.rep_store.append_entry(entry):
                if request.recipient in self.active_subscribers:
                    try:
                        notification = chat_pb2.UpdateNotification(
                            message_received=chat_pb2.MessageReceived(
                                message_id=message_id,
                                sender=request.sender,
                                content=request.content,
                                timestamp=entry["timestamp"]
                            )
                        )
                        self.active_subscribers[request.recipient].send(notification)
                        entry["read"] = True
                        self.rep_store.persist_log_to_disk()
                    except Exception as e:
                        logging.error(f"Notification error: {e}")
                return chat_pb2.SendMessageResponse(success=True, message="Message sent", message_id=message_id)
            else:
                return chat_pb2.SendMessageResponse(success=False, message="Failed to replicate message")
        else:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader")

    def LoadUnreadMessages(self, request, context):
        username = self._authenticate(context)
        if username != request.username:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
        messages = []
        for msg in self.rep_store.state.get("messages", []):
            if msg.get("recipient") == username and not msg.get("read", False):
                messages.append(msg)
                msg["read"] = True
        self.rep_store.persist_log_to_disk()
        response_msgs = [
            chat_pb2.Message(
                id=int(msg["message_id"]) if isinstance(msg["message_id"], str) else msg["message_id"],
                sender=msg["sender"],
                content=msg["content"],
                timestamp=msg["timestamp"]
            )
            for msg in messages
        ]
        return chat_pb2.LoadMessagesResponse(messages=response_msgs)

    def DeleteMessage(self, request, context):
        username = self._authenticate(context)
        if username != request.username:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
        target_msg = next((msg for msg in self.rep_store.state.get("messages", []) if msg.get("message_id") == request.message_id), None)
        if not target_msg or target_msg.get("sender") != username:
            return chat_pb2.StatusResponse(success=False, message="Message not found or unauthorized")
        entry = {
            "operation": "delete_message",
            "message_id": request.message_id,
            "timestamp": datetime.now().isoformat()
        }
        if self.rep_store.is_leader:
            if self.rep_store.append_entry(entry):
                self.rep_store.state["messages"] = [m for m in self.rep_store.state.get("messages", [])
                                                     if m.get("message_id") != request.message_id]
                recipient = target_msg.get("recipient")
                if recipient in self.active_subscribers:
                    try:
                        notification = chat_pb2.UpdateNotification(
                            message_deleted=chat_pb2.MessageDeleted(message_id=request.message_id)
                        )
                        self.active_subscribers[recipient].send(notification)
                    except Exception as e:
                        logging.error(f"Notification error: {e}")
                return chat_pb2.StatusResponse(success=True, message="Message deleted")
            else:
                return chat_pb2.StatusResponse(success=False, message="Failed to replicate deletion")
        else:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader")

    def DeleteAccount(self, request, context):
        username = self._authenticate(context)
        if username != request.username:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
        accounts = self.rep_store.state.get("accounts", {})
        if request.username not in accounts or not bcrypt.checkpw(request.password.encode(), accounts[request.username].encode()):
            return chat_pb2.StatusResponse(success=False, message="Invalid credentials")
        entry = {
            "operation": "delete_account",
            "username": request.username,
            "timestamp": datetime.now().isoformat()
        }
        if self.rep_store.is_leader:
            if self.rep_store.append_entry(entry):
                self.rep_store.state["accounts"].pop(request.username, None)
                session_ids_to_remove = [sid for sid, uname in self.user_sessions.items() if uname == request.username]
                for sid in session_ids_to_remove:
                    del self.user_sessions[sid]
                notification = chat_pb2.UpdateNotification(
                    account_deleted=chat_pb2.AccountDeleted(username=request.username)
                )
                for sub in self.active_subscribers.values():
                    try:
                        sub.send(notification)
                    except Exception as e:
                        logging.error(f"Notification error: {e}")
                return chat_pb2.StatusResponse(success=True, message="Account deleted")
            else:
                return chat_pb2.StatusResponse(success=False, message="Failed to replicate account deletion")
        else:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader")

    def SubscribeToUpdates(self, request, context):
        try:
            username = self._authenticate(context)
            if username != request.username:
                context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not authorized")
            self.active_subscribers[username] = context
            notification_queue = []
            while context.is_active():
                time.sleep(1)
                while notification_queue:
                    yield notification_queue.pop(0)
                yield chat_pb2.UpdateNotification()  # Heartbeat to keep stream alive.
        except Exception as e:
            logging.error(f"Subscription error: {e}")
        finally:
            if username in self.active_subscribers:
                del self.active_subscribers[username]
            metadata = dict(context.invocation_metadata())
            session_id = metadata.get('session_id')
            if session_id in self.user_sessions:
                del self.user_sessions[session_id]

# -------------------------------
# Server Startup Function
# -------------------------------
def serve(port=50051, replication_port=50052, is_leader=False, peer_addresses=[]):
    storage_file = f"persistent_log_{port}.json"
    rep_store = ReplicatedStore(
        node_id=port,
        peer_addresses=peer_addresses,
        storage_file=storage_file,
        is_leader=is_leader
    )
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 1024*1024*10),  # 10MB
            ('grpc.max_receive_message_length', 1024*1024*10)  # 10MB
        ]
    )
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(rep_store), server)
    replication_pb2_grpc.add_ReplicationServiceServicer_to_server(ReplicationServicer(rep_store), server)
    server.add_insecure_port(f'[::]:{port}')
    server.add_insecure_port(f'[::]:{replication_port}')
    server.start()
    logging.info(f"Server started on chat port {port} and replication port {replication_port} as {rep_store.role}")
    server.wait_for_termination()

# -------------------------------
# Main
# -------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Replicated GRPC Chat Server with Leader Election")
    parser.add_argument("--port", type=int, default=50051, help="Port for ChatService")
    parser.add_argument("--replication_port", type=int, default=50052, help="Port for ReplicationService")
    parser.add_argument("--leader", action="store_true", help="Run this node as leader initially")
    parser.add_argument("--peers", nargs='*', default=[], help="List of peer replication addresses (e.g., localhost:50052)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    serve(port=args.port,
          replication_port=args.replication_port,
          is_leader=args.leader,
          peer_addresses=args.peers)
