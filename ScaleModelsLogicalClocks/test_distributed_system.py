import unittest
import os
import time
import threading

from distributed_system import VirtualMachine

class TestDistributedSystem(unittest.TestCase):
    def setUp(self):
        # Use ports unlikely to conflict with other services.
        self.vm1_port = 12000
        self.vm2_port = 12001

        # Create two VMs.
        self.vm1 = VirtualMachine(
            vm_id=1,
            host="127.0.0.1",
            port=self.vm1_port,
            other_vms={2: ("127.0.0.1", self.vm2_port)}
        )
        self.vm2 = VirtualMachine(
            vm_id=2,
            host="127.0.0.1",
            port=self.vm2_port,
            other_vms={1: ("127.0.0.1", self.vm1_port)}
        )

        # Start each VM in its own thread.
        self.vm1_thread = threading.Thread(target=self.vm1.start)
        self.vm2_thread = threading.Thread(target=self.vm2.start)
        self.vm1_thread.start()
        self.vm2_thread.start()

        # Wait for the listener threads and connections to establish.
        time.sleep(3)

    def tearDown(self):
        # Stop both VMs.
        self.vm1.stop()
        self.vm2.stop()
        # Allow threads to complete.
        self.vm1_thread.join(timeout=1)
        self.vm2_thread.join(timeout=1)
        # Clean up log files.
        for filename in ("vm_1.log", "vm_2.log"):
            if os.path.exists(filename):
                os.remove(filename)

    def test_send_and_receive(self):
        # Capture initial logical clock of VM1.
        initial_vm1_clock = self.vm1.logical_clock

        # Trigger a send from VM1 to VM2.
        self.vm1.send_message(2)

        # Wait a short while for the message to be processed.
        time.sleep(2)

        # Check that VM1's log file records a SEND event.
        with open("vm_1.log", "r") as f:
            vm1_logs = f.read()
        self.assertIn("SEND", vm1_logs, "VM1 log should contain a SEND event.")

        # Check that VM2's log file records a RECEIVE event.
        with open("vm_2.log", "r") as f:
            vm2_logs = f.read()
        self.assertIn("RECEIVE", vm2_logs, "VM2 log should contain a RECEIVE event.")

        # Check that VM1's logical clock increased.
        self.assertGreater(self.vm1.logical_clock, initial_vm1_clock,
                           "VM1's logical clock should increment after sending a message.")

if __name__ == '__main__':
    unittest.main()
