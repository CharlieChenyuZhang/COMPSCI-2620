import pytest

def test_create_account(server):
    # test successful creation
    request = {
        'action': 'create',
        'username': 'testuser',
        'password': 'testpass'
    }
    response = server.handle_create_account(request)
    assert response['status'] == 'success'
    assert response['unread_count'] == 0
    
    # test duplicate creation
    response = server.handle_create_account(request)
    assert response['status'] == 'error'
    assert 'exists' in response['message'].lower()

def test_login(server, mock_connection):
    """Test login functionality"""
    # create test account first
    server.handle_create_account({
        'action': 'create',
        'username': 'testuser',
        'password': 'testpass'
    })
    
    # test successful login
    request = {
        'action': 'login',
        'username': 'testuser',
        'password': 'testpass'
    }
    response = server.handle_login(request, mock_connection)
    assert response['status'] == 'success'
    assert 'testuser' in server.active_connections
    
    # test wrong password
    request['password'] = 'wrongpass'
    response = server.handle_login(request, mock_connection)
    assert response['status'] == 'error'
    
def test_list_accounts(server):
    # create test accounts
    usernames = ['user1', 'user2', 'testuser']
    for username in usernames:
        server.handle_create_account({
            'action': 'create',
            'username': username,
            'password': 'testpass'
        })
    
    # test listing all accounts
    response = server.handle_list_accounts({'pattern': '*'})
    assert response['status'] == 'success'
    assert set(response['accounts']) == set(usernames)
    
    # test pattern matching
    response = server.handle_list_accounts({'pattern': 'user.*'})
    assert response['status'] == 'success'
    assert set(response['accounts']) == {'user1', 'user2'}

def test_delete_account(server, mock_connection):
    # create and login test account
    username = 'deleteuser'
    password = 'testpass'
    server.handle_create_account({
        'action': 'create',
        'username': username,
        'password': password
    })
    
    # test account deletion
    request = {
        'action': 'delete_account',
        'username': username,
        'password': password
    }
    response = server.handle_delete_account(request, mock_connection)
    assert response['status'] == 'success'
    
    # verify account is deleted
    assert not server.db.account_exists(username)