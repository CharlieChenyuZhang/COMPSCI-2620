import os
import socket
import threading
import queue
import time
import random
import datetime
import sys
import multiprocessing

class VirtualMachine:
    def __init__(self, vm_id, host, port, other_vms, experiment_mode, output_folder):
        """
        vm_id: Unique integer identifier for the VM.
        host: Host address (e.g., "127.0.0.1").
        port: Port number on which to bind the server socket.
        other_vms: A dictionary mapping other vm_id's to (host, port).
        experiment_mode: 1 or 2. In mode 1 the clock rate is 1-6 ticks/sec and random event is 1-10.
                         In mode 2, clock rate is 4-6 and random event is 1-6.
        output_folder: Folder in which the VM log file will be stored.
        """
        self.vm_id = vm_id
        self.host = host
        self.port = port
        self.other_vms = other_vms  # Other VMs: {vm_id: (host, port)}
        self.experiment_mode = experiment_mode
        # Choose clock rate based on experiment mode.
        if self.experiment_mode == 1:
            self.clock_rate = random.randint(1, 6)
        elif self.experiment_mode == 2:
            self.clock_rate = random.randint(4, 6)
        elif self.experiment_mode == 3:
            self.clock_rate = random.randint(1, 6)
        elif self.experiment_mode == 4:
            self.clock_rate = random.randint(4, 6)
        else:
            self.clock_rate = random.randint(1, 6)
        self.logical_clock = 0
        self.msg_queue = queue.Queue()
        self.running = True
        # Log file will be saved inside the given output folder.
        self.log_filename = os.path.join(output_folder, f"vm_{vm_id}.log")
        self.server_socket = None
        self.client_sockets = {}  # Outgoing connections: {vm_id: socket}
        self.lock = threading.Lock()  # To synchronize clock updates

    def start(self):
        """Starts the VM: launches the listener, connects to other VMs, and begins the main loop."""
        threading.Thread(target=self.start_listener, daemon=True).start()
        # Allow some time for the listener to start.
        time.sleep(2)
        self.connect_to_others()
        threading.Thread(target=self.main_loop, daemon=True).start()
        print(f"VM {self.vm_id} started with clock rate {self.clock_rate} ticks/sec.")

    def start_listener(self):
        """Starts a TCP server socket and spawns a thread for each incoming connection."""
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
                self.logical_clock += 1  # Increment for the send event (Lamport rule)
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
         - Otherwise, generate a random number and:
           - If 1: send to one randomly chosen other VM.
           - If 2: send to a specific other VM.
           - If 3: send to both other VMs.
           - Otherwise: treat the tick as an internal event.
        """
        tick_interval = 1.0 / self.clock_rate
        while self.running:
            tick_start = time.time()
            if not self.msg_queue.empty():
                try:
                    sender_id, msg_timestamp = self.msg_queue.get_nowait()  # Non-blocking dequeue.
                    with self.lock:
                        self.logical_clock = max(self.logical_clock, msg_timestamp) + 1
                    self.log_event("RECEIVE", f"from VM {sender_id}")
                except queue.Empty:
                    pass
            else:
                # Use different random ranges depending on experiment mode.
                if self.experiment_mode == 1:
                    r = random.randint(1, 10)
                elif self.experiment_mode == 2:
                    r = random.randint(1, 6)
                elif self.experiment_mode == 3:
                    r = random.randint(1, 4)
                elif self.experiment_mode == 4:
                    r = random.randint(1, 10)
                else:
                    r = random.randint(1, 10)

                if r == 1:
                    # Send to one randomly chosen other VM.
                    target = random.choice(list(self.other_vms.keys()))
                    self.send_message(target)
                elif r == 2:
                    # Send to a specific other VM.
                    other_ids = list(self.other_vms.keys())
                    target = max(other_ids) if other_ids else None
                    if target is not None:
                        self.send_message(target)
                elif r == 3:
                    # Send to both other VMs.
                    for target in self.other_vms.keys():
                        self.send_message(target)
                else:
                    # Internal event: simply update the logical clock.
                    with self.lock:
                        self.logical_clock += 1
                    self.log_event("INTERNAL", "Internal event")
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


def vm_process_main(vm_id, host, port, other_vms, experiment_mode, output_folder, time_to_run):
    """
    Helper function to run a single VM in a separate process.
    It starts the VM, lets it run for 'time_to_run' seconds, then stops it.
    """
    vm = VirtualMachine(vm_id, host, port, other_vms, experiment_mode, output_folder)
    vm.start()
    time.sleep(time_to_run)
    vm.stop()


def run_simulation(experiment_mode, run_number, time_to_run=60, num_vms=3, base_port=10000):
    """
    Runs a simulation with a given experiment mode and run number.
    The logs are saved in a folder named "experiment_{experiment_mode}_run_{run_number}".
    Now, each VM is run in its own process.
    """
    output_folder = f"experiment_{experiment_mode}_run_{run_number}"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    processes = []
    for i in range(num_vms):
        # Prepare configuration for other VMs (excluding self).
        other_vms = {j: ("127.0.0.1", base_port + j) for j in range(num_vms) if j != i}
        p = multiprocessing.Process(
            target=vm_process_main,
            args=(i, "127.0.0.1", base_port + i, other_vms, experiment_mode, output_folder, time_to_run)
        )
        processes.append(p)
        p.start()

    print(f"Simulation of {num_vms} VMs started for experiment {experiment_mode} run {run_number}. Running for {time_to_run} seconds...")
    
    # Wait for all VM processes to finish.
    for p in processes:
        p.join()
    
    print(f"Simulation for experiment {experiment_mode} run {run_number} ended.\n")


if __name__ == "__main__":
    # Default settings: experiment 1, run 1, single run mode.
    experiment_mode = 1
    run_number = 1
    batch_mode = False

    # Simple command-line argument parsing.
    # Examples:
    #   python vm.py --experiment=2 --run=3      (runs experiment 2, run 3)
    #   python vm.py --experiment=1 --batch        (runs experiment 1 five times)
    for arg in sys.argv[1:]:
        if arg.startswith("--experiment="):
            try:
                experiment_mode = int(arg.split("=")[1])
            except ValueError:
                experiment_mode = 1
        elif arg.startswith("--run="):
            try:
                run_number = int(arg.split("=")[1])
            except ValueError:
                run_number = 1
        elif arg == "--batch":
            batch_mode = True

    time_to_run = 60  # seconds for each simulation run

    if batch_mode:
        # Run five simulation runs in a row.
        for run in range(1, 6):
            run_simulation(experiment_mode, run, time_to_run)
            # Optional: wait a moment between runs to free ports, etc.
            time.sleep(2)
    else:
        run_simulation(experiment_mode, run_number, time_to_run)
