import pytest
import os
import tempfile
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from db_manager import DatabaseManager
from app import ChatServer

sys.path.append(str(Path(__file__).parent.parent.parent))
from config import server_host, server_port

@pytest.fixture
def test_db():
    db_fd, db_path = tempfile.mkstemp()
    db = DatabaseManager(db_path)
    yield db
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def server(test_db):
    server = ChatServer(host=server_host, port=server_port, use_json=True)
    server.db = test_db
    return server

@pytest.fixture
def mock_connection():
    class MockConn:
        def __init__(self):
            self.sent_data = []
            
        def sendall(self, data):
            self.sent_data.append(data)
            
        def getpeername(self):
            return ('127.0.0.1', 54321)
    
    return MockConn()