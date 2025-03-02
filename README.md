# COMPSCI-2620

COMPSCI 2620 Distributed Computing

Engineering Notebook:
https://docs.google.com/document/d/1pJsdxNyj0JfCWV2ZRaI3XJYShZaj2NPJFMj62kgvS14/edit?usp=sharing

## set up environment

Set up `Conda Virtual Environments`

- `conda create --name cs262-venv python=3.9`
- `conda activate cs262-venv`
- `pip install -r requirements.txt`

# Design Exercise 1

## if you change chat.proto

run this command to regenerate chat_pb2_grpc.py and chat_pb2.py and remember to place it inside the gRPC folder.
`python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat.proto`

## how to run Client

`cd Client`
`streamlit run app.py`

## how to run Server

`cd Server`
`python3 app.py`

# Design Exercise 2 - gRPC implementatino

## how to run Client

`cd gRPC`
`streamlit run app.py`

## how to run Server

`cd gRPC`
`python grpc_server.py`

## how to run test cases in gRPC implementation

`cd gRPC/tests`
`python -m unittest test_client`
`python -m unittest test_server`

Then, you will see something like this

```
❯ python -m unittest test_client
......INFO:grpc_client:Logging out and cleaning up
INFO:grpc_client:Stopping subscription thread
...
----------------------------------------------------------------------
Ran 9 tests in 0.007s

OK
```

or this for the server

```
❯ python -m unittest test_server
ERROR:root:Invalid session ID: invalid-session-id
ERROR:root:Authentication error: StatusCode.UNAUTHENTICATED: Invalid session
.ERROR:root:Missing session ID in request
ERROR:root:Authentication error: StatusCode.UNAUTHENTICATED: Missing session ID
.INFO:root:Successfully authenticated user: testuser
.......
----------------------------------------------------------------------
Ran 9 tests in 0.297s

OK
```

## Screenshot

### log in view

<img width="832" alt="Screenshot 2025-02-12 at 11 54 51 AM" src="https://github.com/user-attachments/assets/f0af6fdf-6b0b-47c8-8e66-f492fefb1a28" />

### sign up view

<img width="829" alt="Screenshot 2025-02-12 at 11 54 58 AM" src="https://github.com/user-attachments/assets/e05bb42d-f7ce-47ce-ab70-39b8874899ae" />

### without selecting a user to chat

<img width="855" alt="Screenshot 2025-02-12 at 11 55 04 AM" src="https://github.com/user-attachments/assets/6e8a8c29-e758-45ef-aa3d-a0e970ea7832" />

### after selecting a user to chat

<img width="849" alt="Screenshot 2025-02-12 at 11 55 10 AM" src="https://github.com/user-attachments/assets/70f1c06f-8a4b-4ea0-a3b3-c87fc573d56d" />

# Design Exercise 3

There are 2 files.

## how to run - distributed_system.py

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
