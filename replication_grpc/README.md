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
