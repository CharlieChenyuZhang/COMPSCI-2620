import socket
import threading
import queue
import time
import random
import datetime
import sys

class VirtualMachine:
    def __init__(self, vm_id, host, port, other_vms):
        """
        vm_id: Unique integer identifier for the VM.
        host: Host address (e.g., "127.0.0.1").
        port: Port number on which to bind the server socket.
        other_vms: A dictionary mapping other vm_id's to (host, port).
        """
        self.vm_id = vm_id
        self.host = host
        self.port = port
        self.other_vms = other_vms  # Other VMs: {vm_id: (host, port)}
        self.clock_rate = random.randint(1, 6)
        self.logical_clock = 0
        self.msg_queue = queue.Queue()
        self.running = True
        self.log_filename = f"vm_{vm_id}.log"
        self.server_socket = None
        self.client_sockets = {}  # Outgoing connections: {vm_id: socket}
        self.lock = threading.Lock()  # To synchronize clock updates

    def start(self):
        """Starts the VM: the listener, connects to others, and begins the main loop."""
        threading.Thread(target=self.start_listener, daemon=True).start()
        # Wait a moment for the listener to be ready before connecting to others.
        time.sleep(2)
        self.connect_to_others()
        threading.Thread(target=self.main_loop, daemon=True).start()
        print(f"VM {self.vm_id} started with clock rate {self.clock_rate} ticks/sec.")

    def start_listener(self):
        """Starts a TCP server socket and spawns a handler for each connection."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self.handle_connection, args=(conn,), daemon=True).start()
            except Exception as e:
                print(f"VM {self.vm_id} listener error: {e}")
                break

    def handle_connection(self, conn):
        """Handles an incoming connection and enqueues received messages."""
        with conn:
            file_obj = conn.makefile('r')
            for line in file_obj:
                line = line.strip()
                if line:
                    # Expected message format: "sender_id:timestamp"
                    parts = line.split(":")
                    if len(parts) == 2:
                        try:
                            sender_id = int(parts[0])
                            msg_timestamp = int(parts[1])
                            self.msg_queue.put((sender_id, msg_timestamp))
                        except ValueError:
                            continue

    def connect_to_others(self):
        """Connects to every other VM using their provided host and port."""
        for other_id, (other_host, other_port) in self.other_vms.items():
            connected = False
            while not connected and self.running:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((other_host, other_port))
                    self.client_sockets[other_id] = s
                    connected = True
                except Exception:
                    time.sleep(1)
        print(f"VM {self.vm_id} connected to VMs: {list(self.client_sockets.keys())}")

    def send_message(self, target_id):
        """Sends a message to the target VM, updating the logical clock."""
        if target_id in self.client_sockets:
            with self.lock:
                self.logical_clock += 1  # Lamport clock increment for send event
                timestamp = self.logical_clock
            message = f"{self.vm_id}:{timestamp}\n"
            try:
                self.client_sockets[target_id].sendall(message.encode())
                self.log_event("SEND", f"to VM {target_id}")
            except Exception as e:
                print(f"VM {self.vm_id} failed to send to VM {target_id}: {e}")

    def log_event(self, event_type, extra_info=""):
        """Logs an event with the system time, event type, and current logical clock."""
        system_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if event_type == "RECEIVE":
            queue_length = self.msg_queue.qsize()
            log_message = f"{system_time} - {event_type} {extra_info} | Queue length: {queue_length} | Logical clock: {self.logical_clock}\n"
        else:
            log_message = f"{system_time} - {event_type} {extra_info} | Logical clock: {self.logical_clock}\n"
        with open(self.log_filename, "a") as f:
            f.write(log_message)

    def main_loop(self):
        """
        On every clock tick:
         - If a message is in the queue, process one (update clock using max(received, local)+1)
         - Otherwise, generate a random number (1-10) and:
           - If 1: send to one randomly chosen other VM.
           - If 2: send to the other VM (if exactly two exist).
           - If 3: send to both other VMs.
           - Otherwise: treat as an internal event.
        """
        tick_interval = 1.0 / self.clock_rate
        while self.running:
            tick_start = time.time()
            if not self.msg_queue.empty():
                try:
                    sender_id, msg_timestamp = self.msg_queue.get_nowait() # non-blocking way to retrieve an item from a queue.Queue
                    with self.lock:
                        self.logical_clock = max(self.logical_clock, msg_timestamp) + 1
                    self.log_event("RECEIVE", f"from VM {sender_id}")
                except queue.Empty:
                    pass
            else:
                r = random.randint(1, 10)
                if r == 1:
                    # Send to one randomly chosen other VM.
                    target = random.choice(list(self.other_vms.keys()))
                    self.send_message(target)
                elif r == 2:
                    # Send to a specific other VM.
                    other_ids = list(self.other_vms.keys())
                    # If there are two, choose the one with the larger id.
                    target = max(other_ids) if other_ids else None
                    if target is not None:
                        self.send_message(target)
                elif r == 3:
                    # Send to both other VMs.
                    for target in self.other_vms.keys():
                        self.send_message(target)
                else:
                    # Internal event: update logical clock.
                    with self.lock:
                        self.logical_clock += 1
                    self.log_event("INTERNAL", "Internal event")
            # Maintain clock tick rate.
            tick_duration = time.time() - tick_start
            if tick_duration < tick_interval:
                time.sleep(tick_interval - tick_duration)

    def stop(self):
        """Stops the VM and cleans up sockets."""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        for s in self.client_sockets.values():
            s.close()

if __name__ == "__main__":
    time_to_run = 60 # seconds
    
    # Run either as a single VM (with command-line parameters) or spawn a simulation of 3 VMs.
    if len(sys.argv) > 1:
        # Expected arguments: vm_id port other_vm_info...
        # other_vm_info format: id:host:port (e.g., 1:127.0.0.1:10001)
        vm_id = int(sys.argv[1])
        port = int(sys.argv[2])
        other_vms = {}
        for arg in sys.argv[3:]:
            parts = arg.split(":")
            if len(parts) == 3:
                other_id = int(parts[0])
                other_host = parts[1]
                other_port = int(parts[2])
                other_vms[other_id] = (other_host, other_port)
        vm = VirtualMachine(vm_id, "127.0.0.1", port, other_vms)
        vm.start()
        try:
            # Run for time_to_run seconds (or until interrupted).
            time.sleep(time_to_run)
        except KeyboardInterrupt:
            pass
        vm.stop()
    else:
        # Simulation: create 3 VMs with ports 10000, 10001, and 10002.
        num_vms = 3
        base_port = 10000
        vms = []
        vm_configs = {}
        for i in range(num_vms):
            vm_configs[i] = ("127.0.0.1", base_port + i)
        for i in range(num_vms):
            # Prepare configuration for other VMs (excluding self).
            other_vms = {j: vm_configs[j] for j in vm_configs if j != i}
            vm = VirtualMachine(i, "127.0.0.1", vm_configs[i][1], other_vms)
            vms.append(vm)
            threading.Thread(target=vm.start, daemon=True).start()
        print(f"Simulation of 3 VMs started. Running for {time_to_run} seconds...")
        try:
            time.sleep(time_to_run)
        except KeyboardInterrupt:
            pass
        for vm in vms:
            vm.stop()
        print("Simulation ended.")
