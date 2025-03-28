# Design Exercise 3

There are 2 files.

- vm.py
- distributede_system.py

## how to run - distributed_system.py

Processes implementation.

This file save the log files for each of the VMs to the current folder.

1.  Simulation Mode (Multiple VMs in One Process)
    If you run the script without any command-line arguments, it will start a simulation with three virtual machines. Each machine will bind to a unique port (10000, 10001, 10002) and run concurrently in separate threads.

        `python distributed_system.py`

2.  Standalone Mode (Run Each VM Separately)

    ```
    python distributed_system.py <vm_id> <port> <other_vm_info...>
    ```

    e.g.
    For VM 0:

    ```
    python distributed_system.py 0 10000 1:127.0.0.1:10001 2:127.0.0.1:10002
    ```

    For VM 1:

    ```
    python distributed_system.py 1 10001 0:127.0.0.1:10000 2:127.0.0.1:10002
    ```

    For VM 2:

    ```
    python distributed_system.py 2 10002 0:127.0.0.1:10000 1:127.0.0.1:10001
    ```

distributed_system.py -- This file save the log files for each of the VMs to the current folder.

## how to run - vm.py

This file generates 5 runs per experiment and put it to the experiment*{exp_id}\_run*{run_id} accordingly.

```
python vm.py --experiment=2 --run=3      (runs experiment 2, run 3)
```

```
python vm.py --experiment=1 --batch      (runs experiment 1 five times)
```

## how to run the test

For the unittest, we only test the distributed_system.py since this is the main logic. vm.py just added the extra logic to run multiple runs and write to files.

```
python -m unittest test_distributed_system.py
```

Below is the result

```
VM 2 connected to VMs: [1]
VM 1 connected to VMs: [2]
VM 2 started with clock rate 6 ticks/sec.
VM 1 started with clock rate 6 ticks/sec.
VM 1 listener error: [Errno 53] Software caused connection abort
VM 2 listener error: [Errno 53] Software caused connection abort
.
----------------------------------------------------------------------
Ran 1 test in 5.008s

OK
```
