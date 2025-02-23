import grpc
import chat_pb2
import chat_pb2_grpc

class ChatClient:
    def __init__(self, host='localhost', port=50051):
        self.channel = grpc.insecure_channel(f'{host}:{port}')
        self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)

    def create_account(self, username, password):
        request = chat_pb2.CreateAccountRequest(username=username, password=password)
        response = self.stub.CreateAccount(request)
        return response

    def login(self, username, password):
        request = chat_pb2.LoginRequest(username=username, password=password)
        response = self.stub.Login(request)
        return response

    # Implement other methods similarly...

if __name__ == '__main__':
    client = ChatClient()
    response = client.create_account('user1', 'password1')
    print(response) 