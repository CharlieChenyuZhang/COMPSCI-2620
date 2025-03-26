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
        self.initial_peer_addresses = peer_addresses.copy()  # Keep original list
        self.peer_addresses = peer_addresses.copy()  # List of peer replication addresses (e.g., "localhost:50052")
        self.storage_file = storage_file
        self.metadata_file = f"metadata_{node_id}.json"  # Store peers and other metadata
        self.lock = threading.RLock()  # reentrant lock. allows the same thread to acquire the lock multiple times without deadlocking.

        # Load metadata if exists (peer list, etc)
        self.load_metadata()

        self.peer_failure_times = {}  # Keep track of when peers failed
        self.peer_retry_intervals = {}  # How long to wait before retrying
        self.MAX_RETRY_INTERVAL = 60  # Max 60 seconds between retries

        # Election state variables.
        self.current_term = 0
        self.voted_for = None
        # Initially set to follower regardless of flag; will be updated after checking cluster state
        self.role = "follower"
        self.is_leader = False
        self.last_heartbeat = time.time()
        self.leadership_established = time.time()  # Track when leadership was established
        
        # Create separate channels for each peer to avoid reconnection delays
        self.peer_channels = {}
        self.peer_stubs = {}
        for peer in self.peer_addresses:
            try:
                self.peer_channels[peer] = grpc.insecure_channel(
                    peer,
                    options=[
                        ('grpc.keepalive_time_ms', 10000),
                        ('grpc.keepalive_timeout_ms', 5000),
                        ('grpc.keepalive_permit_without_calls', True),
                        ('grpc.http2.max_pings_without_data', 0),
                    ]
                )
                self.peer_stubs[peer] = replication_pb2_grpc.ReplicationServiceStub(self.peer_channels[peer])
                logging.info(f"Created channel to peer {peer}")
            except Exception as e:
                logging.error(f"Error creating channel to {peer}: {e}")

        # Load persistent log and rebuild in-memory state.
        self.log = self.load_log_from_disk()
        self.state = self.rebuild_state_from_log()
        
        # Find current term from log
        for entry in reversed(self.log):
            if entry.get("operation") == "heartbeat":
                self.current_term = max(self.current_term, entry.get("term", 0))
                break
        
        # If specifically asked to be leader, increase the current term to be fresh
        if is_leader:
            self.current_term += 1  # Start with a higher term to establish leadership
            
        # Check if there's an existing leader with a higher term before claiming leadership
        highest_term_found = self._check_for_existing_leader()
        
        # Only become leader if specified by flag AND no higher term found
        if is_leader and not highest_term_found:
            self.role = "leader"
            self.is_leader = True
            self.leadership_established = time.time()  # Set leadership establishment time
            self.voted_for = self.node_id  # Vote for yourself as leader
            logging.info(f"Node {self.node_id} starting as leader for term {self.current_term}")
        else:
            if is_leader and highest_term_found:
                logging.info(f"Not assuming leadership: found existing leader with higher term")
            
        logging.info(f"Node {self.node_id} started; role = {self.role}, leader flag = {self.is_leader}")
        
        # New server gets an extended initial election timeout to avoid disrupting the cluster
        self.initial_startup = True
        self.startup_time = time.time()
        
        # Announce to existing peers if we're new
        self._announce_to_cluster()

        # Start election daemon thread.
        threading.Thread(target=self.election_daemon, daemon=True).start()
                            
    def _verify_peer_is_alive(self, peer_address):
        """Verify if a peer server is actually alive and responding"""
        try:
            # Extract the port from the peer address
            port = int(peer_address.split(":")[-1])
            host = peer_address.split(":")[0]
            
            # Try socket-level check first
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)  # Very short timeout
            
            result = s.connect_ex((host, port))
            if result != 0:
                s.close()
                return False
                
            # Basic TCP handshake succeeded, now close properly
            try:
                s.shutdown(socket.SHUT_RDWR)
            except:
                pass
            s.close()
            
            # For a more thorough check, try gRPC if we have a stub
            if peer_address in self.peer_stubs:
                try:
                    # Simple heartbeat with very short timeout
                    probe_entry = {
                        "operation": "heartbeat",
                        "term": self.current_term,
                        "sender": self.node_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    req = replication_pb2.AppendEntryRequest(entry_json=json.dumps(probe_entry))
                    response = self.peer_stubs[peer_address].AppendEntry(req, timeout=0.5)
                    return True
                except Exception:
                    # If gRPC call fails but socket succeeded, give it the benefit of the doubt
                    # This avoids too aggressively removing peers during temporary network issues
                    return True
            
            # If we got here, socket check succeeded but no gRPC stub to test
            return True
            
        except Exception as e:
            logging.debug(f"Peer connectivity check error for {peer_address}: {e}")
            return False
                                
    def _check_for_existing_leader(self):
        """Check if there's an existing leader with a higher term"""
        highest_term_found = self.current_term
        highest_term_leader_id = None
        active_server_found = False
        
        # Try to connect to each peer and check their term
        for peer in self.peer_addresses:
            if peer in self.peer_stubs:
                try:
                    # Check if peer is actually responsive
                    peer_port = int(peer.split(":")[-1])
                    if not self._verify_peer_is_alive(peer_port):
                        logging.warning(f"Peer {peer} appears to be suspended or unresponsive")
                        continue
                    
                    # Send a simple heartbeat with the current term to probe the cluster
                    probe_entry = {
                        "operation": "heartbeat",
                        "term": self.current_term,  # Use actual term instead of 0
                        "sender": self.node_id,
                        "timestamp": datetime.now().isoformat()
                    }
                    request = replication_pb2.AppendEntryRequest(entry_json=json.dumps(probe_entry))
                    response = self.peer_stubs[peer].AppendEntry(request, timeout=1)  # Shorter timeout
                    
                    # Track active servers
                    active_server_found = True
                    logging.info(f"Found active server at {peer}")
                    
                    # If we find a higher term, update our state
                    if hasattr(response, 'term') and response.term > highest_term_found:
                        old_term = self.current_term
                        self.current_term = response.term
                        highest_term_found = response.term
                        
                        # Try to extract the node ID from the peer address
                        try:
                            peer_port = peer.split(":")[-1]
                            highest_term_leader_id = peer_port
                        except Exception:
                            pass
                            
                        logging.info(f"Found peer {peer} with higher term: {response.term}, updated from {old_term}")
                except Exception as e:
                    logging.debug(f"No response from {peer} during leader check: {e}")
                    # Remove the stub if it's not responsive
                    if "UNAVAILABLE" in str(e) or "failed to connect" in str(e):
                        if peer in self.peer_stubs:
                            del self.peer_stubs[peer]
                        if peer in self.peer_channels:
                            del self.peer_channels[peer]
                        logging.warning(f"Removed non-responsive peer {peer} from stubs")
                    continue
        
        # If we were asked to be leader and no higher term was found, proceed
        if self.current_term > highest_term_found or not active_server_found:
            logging.info(f"No higher term found, proceeding with my term {self.current_term}")
            return False
                
        # Return True if we found any active server with a higher term
        return highest_term_found > self.current_term

    def _announce_to_cluster(self):
        """Announce this server to all known peers"""
        # If we have no initial peers, we're starting a new cluster
        if not self.peer_addresses:
            return
            
        my_replication_port = int(self.node_id) + 1  # Assuming the convention
        my_address = f"localhost:{my_replication_port}"
        
        # Send announcement to all peers
        success_count = 0
        for peer in self.peer_addresses.copy():  # Use copy to avoid modification during iteration
            try:
                if peer in self.peer_stubs:
                    stub = self.peer_stubs[peer]
                else:
                    # Create a new channel if needed
                    channel = grpc.insecure_channel(peer)
                    stub = replication_pb2_grpc.ReplicationServiceStub(channel)
                
                # Create announcement request
                request = replication_pb2.AnnounceRequest(
                    node_id=self.node_id,
                    replication_address=my_address
                )
                
                # Send announcement
                response = stub.AnnounceNode(request, timeout=2)
                if response.success:
                    success_count += 1
                    logging.info(f"Successfully announced to peer {peer}")
                    
                    # Check if peer sent back their peer list
                    if response.peer_addresses:
                        for new_peer in response.peer_addresses:
                            if (new_peer not in self.peer_addresses and 
                                new_peer != my_address):
                                self.peer_addresses.append(new_peer)
                                logging.info(f"Discovered new peer {new_peer} from announcement response")
            except Exception as e:
                logging.warning(f"Failed to announce to peer {peer}: {e}")
        
        if success_count > 0:
            logging.info(f"Successfully announced to {success_count} peers")
            # Save updated peer list
            self.save_metadata()
        else:
            logging.warning("Failed to announce to any peers, will retry during heartbeats")

    def prune_dead_peers(self):
        """Remove unresponsive peers from peer_addresses list"""
        if not hasattr(self, 'peer_failure_count'):
            self.peer_failure_count = {}  # Track consecutive failures
        
        peers_to_remove = []
        
        for peer in self.peer_addresses[:]:  # Work on a copy to avoid modification during iteration
            # Check if this peer has had persistent failures
            if peer in self.peer_failure_times:
                current_time = time.time()
                failure_duration = current_time - self.peer_failure_times[peer]
                
                # Increment failure count if it exists, otherwise initialize to 1
                self.peer_failure_count[peer] = self.peer_failure_count.get(peer, 0) + 1
                
                # If persistent failures for over 60 seconds or 5+ consecutive failures, consider removing
                if failure_duration > 60 or self.peer_failure_count.get(peer, 0) >= 5:
                    # Verify one more time before removing
                    if not self._verify_peer_is_alive(peer):
                        peers_to_remove.append(peer)
                        logging.warning(f"Removing persistently unresponsive peer: {peer}")
                    else:
                        # Peer is responsive again
                        if peer in self.peer_failure_times:
                            del self.peer_failure_times[peer]
                        if peer in self.peer_failure_count:
                            del self.peer_failure_count[peer]
        
        # Remove dead peers
        for peer in peers_to_remove:
            if peer in self.peer_addresses:
                self.peer_addresses.remove(peer)
            if peer in self.peer_stubs:
                del self.peer_stubs[peer]
            if peer in self.peer_channels:
                del self.peer_channels[peer]
            if peer in self.peer_failure_times:
                del self.peer_failure_times[peer]
            if peer in self.peer_failure_count:
                del self.peer_failure_count[peer]
        
        # If we removed any peers, save metadata
        if peers_to_remove:
            self.save_metadata()
        
        return len(peers_to_remove)

    def load_metadata(self):
        """Load metadata including peer list from disk"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
                    
                    # Get stored peer list, but prioritize command line arguments
                    stored_peers = metadata.get("peer_addresses", [])
                    
                    # If we have initial_peer_addresses from command line args, use them instead
                    if hasattr(self, 'initial_peer_addresses') and self.initial_peer_addresses:
                        self.peer_addresses = self.initial_peer_addresses.copy()
                        # Only add additional stored peers that aren't already in our list
                        for peer in stored_peers:
                            if peer not in self.peer_addresses:
                                self.peer_addresses.append(peer)
                    else:
                        # Otherwise use stored peers
                        self.peer_addresses = stored_peers
                        
                    # Store node ID from metadata if available
                    if "node_id" in metadata:
                        self.node_id = metadata["node_id"]
                    
                    logging.info(f"Loaded metadata with {len(self.peer_addresses)} peers")
                    
                    # Mark all loaded peers as potentially inactive until verified
                    self.pending_verification_peers = set(self.peer_addresses.copy())
                    return True
        except Exception as e:
            logging.error(f"Error loading metadata: {e}")
        
        # If we get here, either no metadata file exists or there was an error
        # Save current state as new metadata
        self.save_metadata()
        return False

    def save_metadata(self):
        """Save metadata including peer list to disk"""
        try:
            metadata = {
                "peer_addresses": self.peer_addresses,
                "node_id": self.node_id,
                "timestamp": datetime.now().isoformat()
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, default=str)
            
            logging.debug(f"Saved metadata with {len(self.peer_addresses)} peers")
            return True
        except Exception as e:
            logging.error(f"Error saving metadata: {e}")
            return False

    def add_peer(self, peer_address):
        """Add a new peer to the cluster"""
        with self.lock:
            # Check if peer already exists
            if peer_address in self.peer_addresses:
                return False
            
            # Don't add ourselves as a peer
            if peer_address == f"localhost:{self.node_id}":
                return False
                
            # Add to peer list
            self.peer_addresses.append(peer_address)
            
            # Create channel to new peer
            try:
                self.peer_channels[peer_address] = grpc.insecure_channel(
                    peer_address,
                    options=[
                        ('grpc.keepalive_time_ms', 10000),
                        ('grpc.keepalive_timeout_ms', 5000),
                        ('grpc.keepalive_permit_without_calls', True),
                        ('grpc.http2.max_pings_without_data', 0),
                    ]
                )
                self.peer_stubs[peer_address] = replication_pb2_grpc.ReplicationServiceStub(self.peer_channels[peer_address])
                logging.info(f"Added new peer {peer_address} to cluster")
                
                # Save updated peer list
                self.save_metadata()
                return True
            except Exception as e:
                logging.error(f"Error creating channel to new peer {peer_address}: {e}")
                # Remove from list since we couldn't connect
                self.peer_addresses.remove(peer_address)
                return False

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
            logging.debug(f"Persisted log to {self.storage_file}")
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
        """
        Compute the required quorum size (including self) based on ACTIVE servers.
        Servers that haven't responded recently are excluded from the calculation.
        """
        current_time = time.time()
        
        # First prune any dead peers
        self.prune_dead_peers()
        
        # Count active peers (those not in failure_times or with recent activity)
        active_peers = 0
        
        for peer in self.peer_addresses:
            # If peer isn't in failure list or the failure was detected a long time ago (might be back online)
            if peer not in self.peer_failure_times:
                active_peers += 1
        
        # Total active nodes is active peers plus self
        total_active_nodes = active_peers + 1
        
        # Calculate minimum needed for quorum (majority of active nodes)
        quorum = total_active_nodes // 2 + 1
        
        logging.info(f"Quorum calculation: {quorum} of {total_active_nodes} active nodes (from {len(self.peer_addresses) + 1} total)")
        
        # Ensure minimum quorum of 2 (self + at least one peer)
        # This ensures system can make progress with just 2 nodes
        return max(2, quorum)

    def send_append_entry(self, peer, entry):
        """Send an AppendEntry RPC to a peer."""
        try:
            # Use the cached stub if available
            if peer in self.peer_stubs:
                stub = self.peer_stubs[peer]
            else:
                # Fall back to creating a new channel if needed
                channel = grpc.insecure_channel(peer)
                stub = replication_pb2_grpc.ReplicationServiceStub(channel)
                
            # Convert the entry to JSON, using default=str to handle UUIDs.
            request = replication_pb2.AppendEntryRequest(entry_json=json.dumps(entry, default=str))
            response = stub.AppendEntry(request, timeout=5)  # Increased timeout from 3 to 5 seconds
            return response.success
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                logging.warning(f"Timeout sending append entry to {peer}")
            else:
                logging.error(f"gRPC error sending append entry to {peer}: {e.code()}: {e.details()}")
            return False
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
                    logging.debug(f"Successfully replicated entry to {peer}")

            if success_count >= self.quorum_size():
                self.commit_entry(entry)
                logging.info(f"Entry committed: {entry}")
                return True
            else:
                logging.error(f"Failed to replicate entry to a quorum (only {success_count} of {self.quorum_size()} needed)")
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
    def refresh_peer_connections(self):
        """Refresh connections to peers that might have failed, with exponential backoff"""
        current_time = time.time()
        
        for peer in self.peer_addresses:
            if peer not in self.peer_channels or peer not in self.peer_stubs:
                # Check if we need to respect the backoff period
                if peer in self.peer_failure_times:
                    last_failure = self.peer_failure_times[peer]
                    retry_interval = self.peer_retry_intervals.get(peer, 1)
                    
                    # If not enough time has passed since last failure, skip
                    if current_time - last_failure < retry_interval:
                        continue
                    
                    # Double the retry interval for next time (with a cap)
                    self.peer_retry_intervals[peer] = min(retry_interval * 2, self.MAX_RETRY_INTERVAL)
                
                try:
                    self.peer_channels[peer] = grpc.insecure_channel(
                        peer,
                        options=[
                            ('grpc.keepalive_time_ms', 10000),
                            ('grpc.keepalive_timeout_ms', 5000),
                            ('grpc.keepalive_permit_without_calls', True),
                        ]
                    )
                    self.peer_stubs[peer] = replication_pb2_grpc.ReplicationServiceStub(self.peer_channels[peer])
                    logging.info(f"Recreated channel to peer {peer}")
                    
                    # Success - remove from failure tracking
                    if peer in self.peer_failure_times:
                        del self.peer_failure_times[peer]
                        del self.peer_retry_intervals[peer]
                        
                except Exception as e:
                    # Record the failure time
                    self.peer_failure_times[peer] = current_time
                    if peer not in self.peer_retry_intervals:
                        self.peer_retry_intervals[peer] = 1
                    
                    logging.error(f"Error recreating channel to {peer}: {e}")
                                    
    def start_election(self):
        """Trigger an election: become candidate, increment term, and request votes."""
        logging.info("Starting election")
        
        # Prune dead peers before election
        self.prune_dead_peers()
        
        # Refresh connections to peers before election
        self.refresh_peer_connections()
        
        with self.lock:
            # Increment term and become candidate
            self.current_term += 1
            self.role = "candidate"
            self.voted_for = self.node_id  # Vote for self
            vote_count = 1  # Start with 1 vote (self)
            current_term = self.current_term
            logging.info(f"Node {self.node_id} starting election for term {current_term}")
        
        logging.info("Soliciting votes")
        
        # Track active and unreachable peers for better logging
        active_peers = []
        unreachable_peers = []
        
        # Gather votes from peers
        for peer in self.peer_addresses:
            try:
                # Try to use existing stub if available
                if peer in self.peer_stubs:
                    stub = self.peer_stubs[peer]
                else:
                    # Create a new channel if needed
                    channel = grpc.insecure_channel(peer)
                    stub = replication_pb2_grpc.ReplicationServiceStub(channel)
                
                # Request vote with current term
                req = replication_pb2.RequestVoteRequest(term=current_term, candidate_id=self.node_id)
                response = stub.RequestVote(req, timeout=5)
                
                # Successfully contacted this peer, so it's active
                active_peers.append(peer)
                
                if response.vote_granted:
                    vote_count += 1
                    logging.info(f"Received vote from {peer} for term {current_term}")
                else:
                    # If peer reports a higher term, adopt it
                    if response.term > current_term:
                        logging.info(f"Peer {peer} has higher term {response.term}, updating from {current_term}")
                        with self.lock:
                            self.current_term = response.term
                            self.role = "follower"
                            self.voted_for = None
                    else:
                        logging.info(f"Vote denied by {peer} for term {current_term}, their term: {response.term}")
            except grpc.RpcError as e:
                # Track unreachable peers
                unreachable_peers.append(peer)
                
                # Update peer failure tracking
                current_time = time.time()
                self.peer_failure_times[peer] = current_time
                
                if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                    logging.warning(f"Timeout requesting vote from {peer}")
                else:
                    logging.error(f"gRPC error requesting vote from {peer}: {e.code()}: {e.details()}")
            except Exception as e:
                # Track unreachable peers
                unreachable_peers.append(peer)
                
                # Update peer failure tracking
                current_time = time.time()
                self.peer_failure_times[peer] = current_time
                
                logging.error(f"Error sending RequestVote to {peer}: {e}")
        
        # Use the updated quorum size that considers only active peers
        quorum = self.quorum_size()
        
        # More detailed logging about the active cluster state
        total_active = len(active_peers) + 1  # active peers + self
        logging.info(f"Election status: {total_active} active nodes, {len(unreachable_peers)} unreachable nodes")
        logging.info(f"Election results: received {vote_count} votes out of {len(self.peer_addresses) + 1} total nodes")
        logging.info(f"Required quorum: {quorum} votes (based on active nodes)")
        
        with self.lock:
            if vote_count >= quorum:
                # Won election: become leader
                self.role = "leader"
                self.is_leader = True
                self.leadership_established = time.time()
                logging.info(f"Node {self.node_id} became leader for term {self.current_term} (got {vote_count} votes, needed {quorum})")
                
                # Send immediate heartbeats to establish leadership
                # Release lock before sending heartbeats
                self.lock.release()
                try:
                    self.send_heartbeats()
                finally:
                    self.lock.acquire()
            else:
                # Lost election: revert to follower
                logging.info(f"Node {self.node_id} failed election in term {self.current_term} (got {vote_count} votes, needed {quorum})")
                self.role = "follower"
                self.is_leader = False
        
        logging.info("Election complete")
                        
    def send_heartbeats(self):
        """Send heartbeat messages (via AppendEntry RPC with a 'heartbeat' entry) to all peers."""
        heartbeat_entry = {
            "operation": "heartbeat",
            "term": self.current_term,
            "sender": self.node_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # First check and refresh any broken connections
        self.refresh_peer_connections()
        
        # Leader should append its own heartbeat to its log first
        with self.lock:
            self.log.append(heartbeat_entry)
            # Persist to disk immediately to ensure leader's heartbeats are recorded
            self.persist_log_to_disk()
        
        success_count = 0
        for peer in self.peer_addresses:
            # Skip peers that have recently failed (handled by refresh_peer_connections)
            if peer in self.peer_failure_times:
                # Skip using continue to avoid the connection retry flood
                continue
                    
            try:
                # Use the cached stub if available
                if peer in self.peer_stubs:
                    stub = self.peer_stubs[peer]
                else:
                    # If we don't have a stub, this peer is likely failed
                    self.peer_failure_times[peer] = time.time()
                    self.peer_retry_intervals[peer] = 1
                    continue
                
                req = replication_pb2.AppendEntryRequest(entry_json=json.dumps(heartbeat_entry))
                response = stub.AppendEntry(req, timeout=2)  # Reduced timeout for heartbeats
                if response.success:
                    success_count += 1
                    
                    # If the peer reports a higher term, step down as leader
                    if hasattr(response, 'term') and response.term > self.current_term:
                        logging.warning(f"Peer {peer} has higher term {response.term}, stepping down as leader")
                        with self.lock:
                            self.current_term = response.term
                            self.is_leader = False
                            self.role = "follower"
                    
            except grpc.RpcError as e:
                current_time = time.time()
                self.peer_failure_times[peer] = current_time
                if peer not in self.peer_retry_intervals:
                    self.peer_retry_intervals[peer] = 1
                    
                if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                    logging.warning(f"Timeout sending heartbeat to {peer}")
                else:
                    logging.error(f"gRPC error sending heartbeat to {peer}: {e.code()}: {e.details()}")
                # If there's an error with this channel, mark it for refresh next time
                if peer in self.peer_channels:
                    self.peer_channels.pop(peer, None)
                    self.peer_stubs.pop(peer, None)
            except Exception as e:
                current_time = time.time()
                self.peer_failure_times[peer] = current_time
                if peer not in self.peer_retry_intervals:
                    self.peer_retry_intervals[peer] = 1
                    
                logging.error(f"Error sending heartbeat to {peer}: {e}")
                # If there's an error with this channel, mark it for refresh next time
                if peer in self.peer_channels:
                    self.peer_channels.pop(peer, None)
                    self.peer_stubs.pop(peer, None)
                    
        if success_count > 0:
            logging.info(f"Sent heartbeats to {success_count} peers")
        else:
            logging.warning("Failed to send heartbeats to any peers")
                                        
    def election_daemon(self):
        """
        Background thread that monitors heartbeats and triggers elections when needed.
        If this node is leader, it sends heartbeats.
        """
        MIN_ELECTION_TIMEOUT = 5  # minimum seconds before triggering election
        MAX_ELECTION_TIMEOUT = 10  # maximum seconds before triggering election (increased range)
        HEARTBEAT_INTERVAL = 2    # seconds between leader heartbeats
        # Newly started servers wait longer before disrupting
        INITIAL_STARTUP_TIMEOUT = 15  # seconds to wait on startup before first election
        # Periodically prune dead peers
        PEER_CLEANUP_INTERVAL = 20  # seconds between peer list cleanups
        
        last_heartbeat_time = time.time()
        last_peer_cleanup_time = time.time()
        
        # Each server should get a consistent but unique random seed based on its ID
        # This ensures election timeouts are different between servers
        random.seed(int(self.node_id) * 100 + time.time())
        
        while True:
            try:
                time.sleep(1)  # Check conditions every second
                
                with self.lock:
                    current_time = time.time()
                    
                    # Periodically clean up dead peers
                    if current_time - last_peer_cleanup_time > PEER_CLEANUP_INTERVAL:
                        removed_count = self.prune_dead_peers()
                        if removed_count > 0:
                            logging.info(f"Peer cleanup: removed {removed_count} unresponsive peers")
                        last_peer_cleanup_time = current_time
                    
                    # If in initial startup phase, use extended timeout
                    if hasattr(self, 'initial_startup') and self.initial_startup:
                        if current_time - self.startup_time < INITIAL_STARTUP_TIMEOUT:
                            # Skip election checks during initial startup phase
                            continue
                        else:
                            # Initial startup phase completed
                            self.initial_startup = False
                            logging.info("Initial startup phase completed, normal election timeout now applies")
                    
                    # If not leader, check if heartbeat timeout expired
                    if self.role != "leader":
                        # Use consistent but different timeouts per server based on node_id
                        base_timeout = MIN_ELECTION_TIMEOUT + (int(self.node_id) % 3)
                        jitter = random.uniform(0, MAX_ELECTION_TIMEOUT - MIN_ELECTION_TIMEOUT)
                        timeout = base_timeout + jitter
                        
                        time_since_last_heartbeat = current_time - self.last_heartbeat
                        
                        if time_since_last_heartbeat > timeout:
                            logging.info(f"Heartbeat timeout: {time_since_last_heartbeat:.1f}s > {timeout:.1f}s")
                            
                            # Before starting election, check if there's an active valid leader
                            leader_found = False
                            for peer in self.peer_addresses:
                                if peer in self.peer_stubs:
                                    try:
                                        # Try to probe with current term to avoid resetting for stale leaders
                                        probe_entry = {
                                            "operation": "heartbeat",
                                            "term": self.current_term,  # Use current term, not 0
                                            "sender": self.node_id,
                                            "timestamp": datetime.now().isoformat()
                                        }
                                        request = replication_pb2.AppendEntryRequest(
                                            entry_json=json.dumps(probe_entry)
                                        )
                                        response = self.peer_stubs[peer].AppendEntry(request, timeout=1)
                                        
                                        # Only reset if the response is from a REAL leader (higher term)
                                        if hasattr(response, 'term') and response.term > self.current_term:
                                            self.current_term = response.term
                                            self.role = "follower"
                                            self.voted_for = None
                                            self.last_heartbeat = time.time()
                                            leader_found = True
                                            logging.info(f"Found active leader before election, term updated to {response.term}")
                                            break
                                    except Exception as e:
                                        logging.debug(f"Error probing peer {peer}: {str(e)}")
                                        continue
                                            
                            if not leader_found:
                                # Release lock before starting election which will reacquire it
                                self.lock.release()
                                try:
                                    self.start_election()
                                finally:
                                    # Reacquire the lock
                                    self.lock.acquire()
                    
                    # If leader, send heartbeats periodically
                    elif self.role == "leader":
                        if current_time - last_heartbeat_time > HEARTBEAT_INTERVAL:
                            # Release lock before sending heartbeats which may take time
                            self.lock.release()
                            try:
                                self.send_heartbeats()
                                last_heartbeat_time = current_time
                            finally:
                                # Reacquire the lock
                                self.lock.acquire()
            except Exception as e:
                logging.error(f"Error in election daemon: {e}")
                                                                                
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

    def AnnounceNode(self, request, context):
        """Handle announcement from a new server joining the cluster"""
        node_id = request.node_id
        replication_address = request.replication_address
        
        logging.info(f"Received announcement from node {node_id} at {replication_address}")
        
        # Add the new peer to our list
        success = self.rep_store.add_peer(replication_address)
        
        # Return our current peer list to help the new node discover other peers
        return replication_pb2.AnnounceResponse(
            success=success,
            peer_addresses=self.rep_store.peer_addresses
        )

    def AppendEntry(self, request, context):
        try:
            entry = json.loads(request.entry_json)
        except Exception as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid entry format: {str(e)}")
            return replication_pb2.AppendEntryResponse(success=False)

        with self.rep_store.lock:
            if entry.get("operation") == "heartbeat":
                # Get heartbeat information
                incoming_term = entry.get("term", 0)
                incoming_sender = entry.get("sender", "unknown")
                
                # Log heartbeat information at INFO level with more details
                logging.info(f"💓 Heartbeat received: term={incoming_term}, sender={incoming_sender}, "
                        f"my_term={self.rep_store.current_term}, my_role={self.rep_store.role}, "
                        f"leader_status={'I am leader' if self.rep_store.is_leader else 'I am follower'}")
                
                # Always update last heartbeat time unless we're the leader and the term is lower
                if not (self.rep_store.is_leader and incoming_term < self.rep_store.current_term):
                    self.rep_store.last_heartbeat = time.time()
                
                # Only record heartbeat in log if it's from a valid leader
                # (equal or higher term, or if it's from a higher ID in the same term)
                is_valid_leader = (incoming_term > self.rep_store.current_term or 
                                (incoming_term == self.rep_store.current_term and
                                    (not self.rep_store.is_leader or incoming_sender > self.rep_store.node_id)))
                    
                if is_valid_leader:
                    self.rep_store.log.append(entry)
                
                # Handle term-related state changes
                if incoming_term > self.rep_store.current_term:
                    # Higher term: Update term and step down
                    old_term = self.rep_store.current_term
                    self.rep_store.current_term = incoming_term
                    self.rep_store.role = "follower"
                    self.rep_store.is_leader = False
                    self.rep_store.voted_for = None
                    logging.info(f"Updated term from {old_term} to {incoming_term} via heartbeat from {incoming_sender}")
                elif incoming_term == self.rep_store.current_term:
                    # Same term: Check if we need to resolve leader conflict
                    if self.rep_store.is_leader and incoming_sender != self.rep_store.node_id:
                        logging.warning(f"⚠️ Leader conflict: I am leader but received heartbeat from {incoming_sender} in same term {incoming_term}")
                        
                        # Resolve leader conflict by comparing node IDs
                        # Higher node ID wins in case of a tie
                        if incoming_sender > self.rep_store.node_id:
                            self.rep_store.role = "follower"
                            self.rep_store.is_leader = False
                            logging.info(f"Stepped down as leader in term {incoming_term}, yielding to {incoming_sender}")
                elif incoming_term < self.rep_store.current_term and self.rep_store.is_leader:
                    # Lower term and I'm leader: Ignore the heartbeat for leadership decisions
                    logging.info(f"Ignoring heartbeat from {incoming_sender} with lower term {incoming_term}")
                    # Do not update last_heartbeat time in this case
                    
            else:
                # Regular log entry: append and commit.
                self.rep_store.log.append(entry)
                self.rep_store.persist_log_to_disk()
                self.rep_store.commit_entry(entry)
                logging.info(f"Appended entry from leader: {entry}")
                
        # Persist heartbeats periodically to help track leader
        if entry.get("operation") == "heartbeat":
            # Only persist occasionally to avoid disk I/O
            if random.random() < 0.1:  # 10% chance
                self.rep_store.persist_log_to_disk()
                
        return replication_pb2.AppendEntryResponse(success=True, term=self.rep_store.current_term)

    def RequestVote(self, request, context):
        candidate_term = request.term
        candidate_id = request.candidate_id
        
        with self.rep_store.lock:
            # Always step down if we see a higher term
            if candidate_term > self.rep_store.current_term:
                old_term = self.rep_store.current_term
                self.rep_store.current_term = candidate_term
                if self.rep_store.role == "leader":
                    # Check for leadership stability - if we've been leader for less than 10 seconds,
                    # and we have a higher node ID, don't step down so easily
                    leadership_duration = time.time() - getattr(self.rep_store, 'leadership_established', 0)
                    if leadership_duration < 10 and self.rep_store.node_id > candidate_id:
                        logging.info(f"Rejecting vote for {candidate_id} despite higher term {candidate_term} - maintaining stability")
                        return replication_pb2.RequestVoteResponse(vote_granted=False, term=candidate_term)
                    
                    self.rep_store.role = "follower"
                    self.rep_store.is_leader = False
                    logging.info(f"Stepped down from leader due to higher term {candidate_term} (was term {old_term})")
                # Reset voted_for to allow voting in the new term
                self.rep_store.voted_for = None
            
            # Reject vote if candidate's term is stale
            if candidate_term < self.rep_store.current_term:
                logging.info(f"Rejected vote for {candidate_id} in term {candidate_term} (our term is {self.rep_store.current_term})")
                return replication_pb2.RequestVoteResponse(vote_granted=False, term=self.rep_store.current_term)
            
            # If we're in the same term, handle potential tie:
            if candidate_term == self.rep_store.current_term:
                # If we already voted for someone else in this term and it's not this candidate, reject
                if self.rep_store.voted_for is not None and self.rep_store.voted_for != candidate_id:
                    # TIEBREAKER: If we voted for ourselves but candidate has SIGNIFICANTLY higher ID, grant vote anyway
                    # This ensures the ID-based tiebreaking is more decisive
                    if (self.rep_store.voted_for == self.rep_store.node_id and 
                        int(candidate_id) > int(self.rep_store.node_id) + 5):  # Significant difference threshold
                        logging.info(f"Tiebreaker: Overriding own vote for candidate with much higher ID {candidate_id}")
                        self.rep_store.voted_for = candidate_id
                        self.rep_store.role = "follower"  # Step down as candidate if we were one
                        self.rep_store.is_leader = False
                        self.rep_store.last_heartbeat = time.time()  # Reset heartbeat timer
                        return replication_pb2.RequestVoteResponse(vote_granted=True, term=self.rep_store.current_term)
                    else:
                        logging.info(f"Rejected vote for {candidate_id} in term {candidate_term}, already voted for {self.rep_store.voted_for}")
                        return replication_pb2.RequestVoteResponse(vote_granted=False, term=self.rep_store.current_term)
            
            # Grant vote if not voted yet in this term or already voted for this candidate
            self.rep_store.voted_for = candidate_id
            
            # Reset heartbeat to avoid immediate election
            self.rep_store.last_heartbeat = time.time()
            
            # Step down if we're leader or candidate
            if self.rep_store.role != "follower":
                self.rep_store.role = "follower"
                self.rep_store.is_leader = False
            
            logging.info(f"Node {self.rep_store.node_id} voted for candidate {candidate_id} in term {candidate_term}")
            return replication_pb2.RequestVoteResponse(vote_granted=True, term=self.rep_store.current_term)
                
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
        try:
            metadata = dict(context.invocation_metadata())
            session_id = metadata.get('session_id')
            if not session_id:
                logging.error("Authentication error: Missing session ID")
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing session ID")
                return None
            if session_id not in self.user_sessions:
                logging.error(f"Authentication error: Invalid session ID {session_id}")
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session ID")
                return None
            return self.user_sessions[session_id]
        except Exception as e:
            logging.error(f"Authentication error: {str(e)}")
            context.abort(grpc.StatusCode.INTERNAL, "Authentication error")
            return None
        
    def CreateAccount(self, request, context):
        # No authentication needed for account creation
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
        
        # Check leadership status
        if not self.rep_store.is_leader:
            # Try to find the current leader
            leader_info = self._get_leader_info()
            if leader_info:
                leader_port = leader_info['port']
                logging.info(f"Account creation request redirecting to leader at port {leader_port}")
                
                # Add details to help client determine if the leader is actually available
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION, 
                    f"Not the leader. Current leader is node {leader_info['node_id']} at port {leader_port}"
                )
            else:
                logging.warning("Account creation request failed - no responsive leader available")
                context.abort(grpc.StatusCode.UNAVAILABLE, "Not the leader and couldn't find any responsive leader")
            return  # Never reached, just for clarity
                
        # Process the account creation (only leaders get here)
        hashed_password = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
        entry = {
            "operation": "create_account",
            "username": request.username,
            "hashed_password": hashed_password,
            "timestamp": datetime.now().isoformat()
        }
        
        logging.info(f"Processing account creation for {request.username} as leader")
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
                                    
    def _get_leader_info(self):
        """Try to determine the current leader from heartbeat information"""
        most_recent_heartbeat = None
        highest_term = -1
        leader_info = None
        current_time = time.time()
        
        # Show current server state
        logging.info(f"Looking for leader, my term={self.rep_store.current_term}, role={self.rep_store.role}")
        
        # If I am the leader, return myself
        if self.rep_store.is_leader:
            logging.info(f"I am the leader (node {self.rep_store.node_id})")
            return {"node_id": self.rep_store.node_id, "port": int(self.rep_store.node_id)}
        
        # First try to find the leader in the log entries - only consider very recent heartbeats
        # (within last 5 seconds)
        recent_threshold = current_time - 5  # 5 second threshold - more aggressive
        
        for entry in reversed(self.rep_store.log[:50]):  # Look at last 50 entries for efficiency
            if entry.get("operation") == "heartbeat":
                term = entry.get("term", -1)
                sender = entry.get("sender", "unknown")
                
                # Parse the timestamp to check recency - CRITICAL for detecting suspended servers
                try:
                    timestamp = entry.get("timestamp")
                    if timestamp:
                        entry_time = datetime.fromisoformat(timestamp).timestamp()
                        # Skip heartbeats older than our threshold
                        if (current_time - entry_time) > 5:  # 5 seconds is very recent
                            continue
                        
                        # For very recent heartbeats, verify the leader is alive
                        if term >= highest_term:
                            logging.debug(f"Found recent heartbeat from {sender} with term {term}")
                            highest_term = term
                            most_recent_heartbeat = entry
                except (ValueError, TypeError):
                    continue
        
        # Verify the found leader is actually responding
        if most_recent_heartbeat:
            sender = most_recent_heartbeat.get("sender", "unknown")
            try:
                port = int(sender)
                logging.info(f"Found leader from recent log: node_id={sender}, port={port}, term={highest_term}")
                
                # Socket-level health check
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)  # Short timeout
                    result = s.connect_ex(('localhost', port))
                    s.close()
                    
                    if result == 0:  # Connection successful
                        logging.info(f"Verified leader port {port} is open")
                        return {"node_id": sender, "port": port}
                    else:
                        logging.warning(f"Leader port {port} not responding at socket level")
                except Exception as e:
                    logging.warning(f"Socket-level check failed for leader port {port}: {e}")
            except (ValueError, TypeError):
                logging.info(f"Found leader with non-numeric ID: {sender}")
        
        # Socket-level check of all peers to find alive servers
        for peer in self.rep_store.peer_addresses:
            try:
                peer_port = int(peer.split(":")[-1])
                
                # Quick socket check first
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    result = s.connect_ex(('localhost', peer_port))
                    s.close()
                    
                    if result == 0:  # Port is open
                        logging.info(f"Found responsive peer at port {peer_port}")
                        return {"node_id": str(peer_port), "port": peer_port}
                except Exception:
                    continue
            except (ValueError, IndexError):
                continue
                
        logging.warning("Could not find any responsive leader or peer")
        return None

    def _verify_leader_is_alive(self, port):
        """More robust verification if a potential leader is actually alive and responding"""
        # First do a fast socket-level check
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)  # Very short timeout
            
            # Attempt to connect
            result = s.connect_ex(('localhost', port))
            
            if result != 0:
                logging.warning(f"Leader port {port} is not accepting connections (error code: {result})")
                s.close()
                return False
                
            # If connection succeeded, try sending a small payload to check if it's actually processing
            try:
                # Send a minimal test message
                s.send(b'\x00\x00')
                
                # Try to receive a response with a very short timeout
                s.settimeout(0.2)
                try:
                    s.recv(1)
                except socket.timeout:
                    # Expected - we aren't a proper client, but at least the socket didn't error
                    pass
                    
                # Close the socket properly
                s.shutdown(socket.SHUT_RDWR)
                s.close()
            except (socket.timeout, ConnectionRefusedError, BrokenPipeError) as e:
                logging.warning(f"Socket communication failed for port {port}: {e}")
                s.close()
                return False
        except Exception as e:
            logging.warning(f"Socket check error for port {port}: {e}")
            return False
        
        # If socket check passes, try gRPC
        try:
            # Create a temporary channel with aggressive timeouts
            temp_channel = grpc.insecure_channel(
                f'localhost:{port}',
                options=[
                    ('grpc.keepalive_time_ms', 1000),
                    ('grpc.keepalive_timeout_ms', 500),
                    ('grpc.keepalive_permit_without_calls', True),
                    ('grpc.connect_timeout_ms', 500),  # Very short connection timeout
                    ('grpc.max_receive_message_length', 1),  # Minimal message size
                    ('grpc.client_idle_timeout_ms', 500),  # Short idle timeout
                ]
            )
            
            # Use a very short timeout
            try:
                # Simple request with minimal timeout
                dummy_request = chat_pb2.ListAccountsRequest(pattern="*")
                future = temp_stub.ListAccounts.future(dummy_request, timeout=0.3)
                
                # Wait for a very short time
                try:
                    response = future.result(timeout=0.2)
                    logging.info(f"Leader at port {port} responded to request")
                    return True
                except grpc.FutureTimeoutError:
                    # Check if the channel is still valid
                    try:
                        temp_stub = chat_pb2_grpc.ChatServiceStub(temp_channel)
                        state = temp_channel.get_state(try_to_connect=False)
                        if state == grpc.ChannelConnectivity.READY or state == grpc.ChannelConnectivity.IDLE:
                            logging.info(f"Verified leader at port {port} is responsive (channel state: {state})")
                            return True
                    except Exception:
                        pass
                    
                    # Cancel the future and close the channel
                    future.cancel()
                    temp_channel.close()
                    return False
            except grpc.RpcError as e:
                # If we get authentication errors, the server is alive
                if e.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
                    logging.info(f"Leader at port {port} is alive (authentication required)")
                    return True
                
                temp_channel.close()
                return False
            except Exception:
                temp_channel.close()
                return False
        except Exception:
            return False
                    
    def Login(self, request, context):
        # No authentication needed for login
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
        # Check for server discovery metadata
        discovery_requested = False
        for key, value in context.invocation_metadata():
            if key == 'discover_servers' and value.lower() == 'true':
                discovery_requested = True
                break
                
        # If this is a server discovery request, add server list metadata
        if discovery_requested:
            # Add metadata about known servers
            try:
                # Get all known replication addresses
                server_list = json.dumps(self.rep_store.peer_addresses)
                context.set_trailing_metadata([('known_servers', server_list)])
            except Exception as e:
                logging.error(f"Error providing server list metadata: {e}")
        
        # For the basic connectivity check with pattern="*", we don't need authentication
        if request.pattern == '*' and not any(metadata for metadata in context.invocation_metadata()):
            # This is likely a connectivity check from the client
            accounts = self.rep_store.state.get("accounts", {})
            empty_accounts = []
            return chat_pb2.ListAccountsResponse(accounts=empty_accounts)
        
        # For actual account listing, authenticate
        try:
            username = self._authenticate(context)
        except Exception:
            # If authentication fails for a real request, abort
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication required")
            return None
        
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
                return chat_pb2.SendMessageResponse(success=True, message="Message sent", message_id=str(message_id))
            else:
                return chat_pb2.SendMessageResponse(success=False, message="Failed to replicate message")
        else:
            leader_info = self._get_leader_info()
            if leader_info:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION, 
                    f"Not the leader. Current leader is node {leader_info['node_id']} at port {leader_info['port']}"
                )
            else:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader and no leader information available")

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
            leader_info = self._get_leader_info()
            if leader_info:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION, 
                    f"Not the leader. Current leader is node {leader_info['node_id']} at port {leader_info['port']}"
                )
            else:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader and no leader information available")

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
            leader_info = self._get_leader_info()
            if leader_info:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION, 
                    f"Not the leader. Current leader is node {leader_info['node_id']} at port {leader_info['port']}"
                )
            else:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Not the leader and no leader information available")

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
            ('grpc.max_receive_message_length', 1024*1024*10),  # 10MB
            ('grpc.keepalive_time_ms', 10000),  # Send keepalive ping every 10 seconds
            ('grpc.keepalive_timeout_ms', 5000),  # Wait 5 seconds for keepalive ping ack
            ('grpc.keepalive_permit_without_calls', True),  # Allow keepalive pings when no calls
            ('grpc.http2.max_pings_without_data', 0),  # Allow unlimited pings without data
            ('grpc.http2.min_time_between_pings_ms', 10000),  # Minimum time between pings
            ('grpc.http2.min_ping_interval_without_data_ms', 5000),  # Minimum time between pings with no data
        ]
    )
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(rep_store), server)
    replication_pb2_grpc.add_ReplicationServiceServicer_to_server(ReplicationServicer(rep_store), server)
    
    # Listen on both the chat and replication ports
    server.add_insecure_port(f'[::]:{port}')
    server.add_insecure_port(f'[::]:{replication_port}')
    
    server.start()
    logging.info(f"Server started on chat port {port} and replication port {replication_port} as {rep_store.role}")
    
    # Setup signal handlers for graceful shutdown
    import signal
    import sys
    
    def signal_handler(sig, frame):
        logging.info(f"Received signal {sig}, initiating graceful shutdown...")
        
        # Close all open connections in peer_channels
        for peer, channel in list(rep_store.peer_channels.items()):
            try:
                logging.info(f"Closing channel to {peer}")
                channel.close()
            except Exception as e:
                logging.error(f"Error closing channel to {peer}: {e}")
        
        # Clean up listening ports
        logging.info("Stopping gRPC server...")
        server.stop(0)
        
        # Persist log one last time
        rep_store.persist_log_to_disk()
        
        if sig != signal.SIGTSTP:  # Don't exit on SIGTSTP (Ctrl+Z)
            logging.info("Server shutdown complete")
            sys.exit(0)
        else:
            logging.warning("SIGTSTP (Ctrl+Z) received. Please use quit/exit command instead of Ctrl+Z")
            print("\nUse 'quit' or Ctrl+C to exit properly instead of Ctrl+Z")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill
    signal.signal(signal.SIGTSTP, signal_handler)  # Ctrl+Z
    
    # Setup console input for commands
    import threading
    
    def console_input():
        while True:
            cmd = input().strip().lower()
            if cmd in ('quit', 'exit'):
                logging.info("Quit command received, initiating shutdown")
                signal_handler(signal.SIGTERM, None)
                break
            elif cmd == 'status':
                logging.info(f"Server status: {rep_store.role}, term={rep_store.current_term}")
            elif cmd == 'help':
                print("Available commands: quit, exit, status, help")
    
    # Start console input thread
    console_thread = threading.Thread(target=console_input, daemon=True)
    console_thread.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
        
# -------------------------------
# Main
# -------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Replicated GRPC Chat Server with Leader Election")
    parser.add_argument("--port", type=int, default=50051, help="Port for ChatService")
    parser.add_argument("--replication_port", type=int, default=50052, help="Port for ReplicationService")
    parser.add_argument("--leader", action="store_true", help="Run this node as leader initially")
    parser.add_argument("--peers", nargs='*', default=[], help="List of peer replication addresses (e.g., localhost:50052)")
    parser.add_argument("--log_level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    # Configure logging
    numeric_level = getattr(logging, args.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {args.log_level}')
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    print("============================================")
    print("Replicated Chat Server")
    print("============================================")
    print(f"Starting on port: {args.port}")
    print(f"Type 'quit' or press Ctrl+C to exit properly")
    print("DO NOT use Ctrl+Z to suspend - it will cause TCP connection issues")
    print("============================================")
    
    serve(
        port=args.port,
        replication_port=args.replication_port,
        is_leader=args.leader,
        peer_addresses=args.peers
    )