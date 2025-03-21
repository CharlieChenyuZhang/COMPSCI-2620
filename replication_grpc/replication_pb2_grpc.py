# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

import replication_pb2 as replication__pb2

GRPC_GENERATED_VERSION = '1.70.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in replication_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class ReplicationServiceStub(object):
    """RPC for replicating log entries (and heartbeat messages)
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.AppendEntry = channel.unary_unary(
                '/replication.ReplicationService/AppendEntry',
                request_serializer=replication__pb2.AppendEntryRequest.SerializeToString,
                response_deserializer=replication__pb2.AppendEntryResponse.FromString,
                _registered_method=True)
        self.RequestVote = channel.unary_unary(
                '/replication.ReplicationService/RequestVote',
                request_serializer=replication__pb2.RequestVoteRequest.SerializeToString,
                response_deserializer=replication__pb2.RequestVoteResponse.FromString,
                _registered_method=True)


class ReplicationServiceServicer(object):
    """RPC for replicating log entries (and heartbeat messages)
    """

    def AppendEntry(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def RequestVote(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_ReplicationServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'AppendEntry': grpc.unary_unary_rpc_method_handler(
                    servicer.AppendEntry,
                    request_deserializer=replication__pb2.AppendEntryRequest.FromString,
                    response_serializer=replication__pb2.AppendEntryResponse.SerializeToString,
            ),
            'RequestVote': grpc.unary_unary_rpc_method_handler(
                    servicer.RequestVote,
                    request_deserializer=replication__pb2.RequestVoteRequest.FromString,
                    response_serializer=replication__pb2.RequestVoteResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'replication.ReplicationService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('replication.ReplicationService', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class ReplicationService(object):
    """RPC for replicating log entries (and heartbeat messages)
    """

    @staticmethod
    def AppendEntry(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/replication.ReplicationService/AppendEntry',
            replication__pb2.AppendEntryRequest.SerializeToString,
            replication__pb2.AppendEntryResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def RequestVote(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/replication.ReplicationService/RequestVote',
            replication__pb2.RequestVoteRequest.SerializeToString,
            replication__pb2.RequestVoteResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
