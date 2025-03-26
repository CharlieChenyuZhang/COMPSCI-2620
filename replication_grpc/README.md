# how to run

## frontend

`streamlit run app.py`

## backend

### 3-server example

on one machine
`python grpc_server.py --port 50051 --replication_port 50052 --leader --peers localhost:50062 localhost:50072`

on other machines (or different terminals)
`python grpc_server.py --port 50061 --replication_port 50062 --peers localhost:50052 localhost:50072`

and

`python grpc_server.py --port 50071 --replication_port 50072 --peers localhost:50052 localhost:50062`

Explanation.
--replication_port:
This sets the port for the ReplicationService, which is responsible for inter-replica communication. In the first command, this is port 50062, and in the second, port 50072. The replication service manages the replication of log entries to ensure persistence and fault tolerance.

--peers:
This parameter lists the addresses (host:port) of peer replicas that this server should communicate with for replication purposes.

(Bonus)
If you want to add additional servers you can run the following commands (they are added without needing the original 3)

# Server 4

`python grpc_server.py --port 50081 --replication_port 50082 --peers localhost:50052 localhost:50062 localhost:50072`

# Server 5

`python grpc_server.py --port 50091 --replication_port 50092 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082`

# Server 6

`python grpc_server.py --port 50101 --replication_port 50102 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082 localhost:50092`

# Server 7

`python grpc_server.py --port 50111 --replication_port 50112 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082 localhost:50092 localhost:50102`

# Server 8

`python grpc_server.py --port 50121 --replication_port 50122 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082 localhost:50092 localhost:50102 localhost:50112`

# Server 9

`python grpc_server.py --port 50131 --replication_port 50132 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082 localhost:50092 localhost:50102 localhost:50112 localhost:50122`

# Server 10

`python grpc_server.py --port 50141 --replication_port 50142 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082 localhost:50092 localhost:50102 localhost:50112 localhost:50122 localhost:50132`

# Server 11

`python grpc_server.py --port 50151 --replication_port 50152 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082 localhost:50092 localhost:50102 localhost:50112 localhost:50122 localhost:50132 localhost:50142`

### 5-server exampel

Leader (Server 1):

`python grpc_server.py --port 50051 --replication_port 50052 --leader --peers localhost:50062 localhost:50072 localhost:50082 localhost:50092`

Follower (Server 2):

`python grpc_server.py --port 50061 --replication_port 50062 --peers localhost:50052 localhost:50072 localhost:50082 localhost:50092`

Follower (Server 3):

`python grpc_server.py --port 50071 --replication_port 50072 --peers localhost:50052 localhost:50062 localhost:50082 localhost:50092`

Follower (Server 4):

`python grpc_server.py --port 50081 --replication_port 50082 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50092`

Follower (Server 5):

`python grpc_server.py --port 50091 --replication_port 50092 --peers localhost:50052 localhost:50062 localhost:50072 localhost:50082`

## unit test

run `python tests/test_client.py`

```
..INFO:grpc_client:Successfully connected to localhost:50051
...INFO:grpc_client:Logging out and cleaning up
INFO:grpc_client:Stopping subscription thread
...
----------------------------------------------------------------------
Ran 8 tests in 0.007s

OK
```

or run `python tests/test_server.py`

```
........
Ran 9 tests in 1.880s

OK
```
