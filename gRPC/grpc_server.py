import grpc
from concurrent import futures
import chat_pb2
import chat_pb2_grpc
from db_manager import DatabaseManager

class ChatService(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self):
        self.db = DatabaseManager()

    def CreateAccount(self, request, context):
        if self.db.account_exists(request.username):
            return chat_pb2.CreateAccountResponse(
                status="error",
                message="Account already exists"
            )
        hashed_password = self.db.hash_password(request.password)
        if self.db.create_account(request.username, hashed_password):
            return chat_pb2.CreateAccountResponse(
                status="success",
                message="Account created successfully"
            )
        return chat_pb2.CreateAccountResponse(
            status="error",
            message="Failed to create account"
        )

    def Login(self, request, context):
        if not self.db.account_exists(request.username):
            return chat_pb2.LoginResponse(
                status="error",
                message="Account does not exist"
            )
        if not self.db.verify_account(request.username, request.password):
            return chat_pb2.LoginResponse(
                status="error",
                message="Incorrect password"
            )
        return chat_pb2.LoginResponse(
            status="success",
            message="Login successful"
        )

    # TODO: Implement other methods similarly...

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve() 