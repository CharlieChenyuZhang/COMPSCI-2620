import pytest

@pytest.fixture
def setup_users(server, mock_connection):
    users = [('sender', 'testpass'), ('recipient', 'testpass')]
    connections = {}
    
    for username, password in users:
        # create account with proper hashing
        server.handle_create_account({
            'action': 'create',
            'username': username,
            'password': password
        })
        conn = type(mock_connection)()
        
        # set up login state
        server.handle_login({
            'action': 'login',
            'username': username,
            'password': password
        }, conn)
        
        # map connections both ways
        server.user_connections[conn] = username
        server.active_connections[username] = conn
        connections[username] = conn
        
    return connections

def test_send_message(server, setup_users):
    sender_conn = setup_users['sender']
    
    # test successful message send
    request = {
        'action': 'send',
        'recipient': 'recipient',
        'message': 'test message'
    }
    response = server.handle_send_message(request, sender_conn)
    assert response['status'] == 'success'
    assert 'message_id' in response
    
    # test sending to non-existent user
    request['recipient'] = 'nonexistent'
    response = server.handle_send_message(request, sender_conn)
    assert response['status'] == 'error'
    
    # test sending to self
    request['recipient'] = 'sender'
    response = server.handle_send_message(request, sender_conn)
    assert response['status'] == 'error'

def test_load_messages(server, setup_users):
    """Test message loading functionality"""
    sender_conn = setup_users['sender']
    recipient_conn = setup_users['recipient']
    
    # Make sure connections are properly mapped
    server.user_connections[sender_conn] = 'sender'
    server.user_connections[recipient_conn] = 'recipient'
    server.active_connections['sender'] = sender_conn
    server.active_connections['recipient'] = recipient_conn
    
    # Send test messages
    messages = ['message1', 'message2', 'message3']
    sent_message_ids = []
    
    # Turn off both users being online to ensure messages stay unread
    server.active_connections.clear()
    
    for msg in messages:
        response = server.handle_send_message({
            'action': 'send',
            'recipient': 'recipient',
            'message': msg
        }, sender_conn)
        assert response['status'] == 'success'
        sent_message_ids.append(response['message_id'])
    
    # Restore online status
    server.active_connections['sender'] = sender_conn
    server.active_connections['recipient'] = recipient_conn
    
    # Test loading unread messages for recipient
    response = server.handle_load_messages({
        'action': 'load-unread',
        'recipient': 'sender'  # Add recipient parameter
    }, recipient_conn)
    
    assert response['status'] == 'success'
    assert len(response['messages']) == len(messages)
    
    # Verify message contents
    received_messages = [msg['message'] for msg in response['messages']]
    assert set(received_messages) == set(messages)
    
    # Verify messages are marked as read
    for msg_id in sent_message_ids:
        msg = server.db.get_message(msg_id)
        if msg:  # Message might be deleted if using snapchat style
            assert msg['read'] == 1
                    
@pytest.fixture
def setup_users(server, mock_connection):
    users = [('sender', 'testpass'), ('recipient', 'testpass')]
    connections = {}
    
    for username, password in users:
        # create account with proper hashing
        server.handle_create_account({
            'action': 'create',
            'username': username,
            'password': password
        })
        conn = type(mock_connection)()
        server.handle_login({
            'action': 'login',
            'username': username,
            'password': password
        }, conn)
        server.user_connections[conn] = username 
        connections[username] = conn
        
    return connections

def test_send_message(server, setup_users):
    sender_conn = setup_users['sender']
    
    # test successful message send
    request = {
        'action': 'send',
        'recipient': 'recipient',
        'message': 'test message'
    }
    response = server.handle_send_message(request, sender_conn)
    assert response['status'] == 'success'
    assert 'message_id' in response
    
def test_send_message(server, setup_users):
    sender_conn = setup_users['sender']
    
    # test successful message send
    request = {
        'action': 'send',
        'recipient': 'recipient',
        'message': 'test message'
    }
    response = server.handle_send_message(request, sender_conn)
    assert response['status'] == 'success'
    assert 'message_id' in response