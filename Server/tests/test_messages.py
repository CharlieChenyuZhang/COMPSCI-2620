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
    sender_conn = setup_users['sender']
    recipient_conn = setup_users['recipient']
    
    # make sure connections are properly mapped
    server.user_connections[sender_conn] = 'sender'
    server.user_connections[recipient_conn] = 'recipient'
    server.active_connections['sender'] = sender_conn
    server.active_connections['recipient'] = recipient_conn
    
    # send test messages
    messages = ['message1', 'message2', 'message3']
    for msg in messages:
        server.handle_send_message({
            'action': 'send',
            'recipient': 'recipient',
            'message': msg
        }, sender_conn)
    
    # test loading unread messages for recipient
    response = server.handle_load_messages({
        'action': 'load-unread'  # no need to specify recipient for unread messages
    }, recipient_conn)
    
    assert response['status'] == 'success'
    assert len(response['messages']) == len(messages)
    
    # verify message contents
    received_messages = [msg['message'] for msg in response['messages']]
    assert set(received_messages) == set(messages)
    
    # test loading past messages after they're marked as read
    server.db.mark_messages_read('recipient')  # mark messages as read
    
    response = server.handle_load_messages({
        'action': 'load-past',
        'recipient': 'sender',  # need recipient for past messages
        'count': 2
    }, recipient_conn)
    
    assert response['status'] == 'success'
    assert len(response['messages']) == 2  # should get exactly 2 messages as requested
        
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