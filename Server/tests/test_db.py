import pytest
import bcrypt

def test_account_operations(test_db):
    username = 'testuser'
    # use encoded password since we're testing the raw database interface
    password = bcrypt.hashpw('testpass'.encode('utf-8'), bcrypt.gensalt())
    
    # test account creation
    assert test_db.create_account(username, password)
    assert test_db.account_exists(username)
    
    # test account verification - pass raw string to match interface
    assert not test_db.verify_account(username, 'wrongpass')
    assert test_db.verify_account(username, 'testpass')
    
def test_message_operations(test_db):
    """Test database message operations"""
    # create test users
    test_db.create_account('sender', b'pass1')
    test_db.create_account('recipient', b'pass2')
    
    # test message storage
    msg_id = test_db.store_message('sender', 'recipient', 'test message')
    assert msg_id is not None
    
    # test message retrieval
    message = test_db.get_message(msg_id)
    assert message['sender'] == 'sender'
    assert message['content'] == 'test message'
    
    # test message deletion
    test_db.delete_message(msg_id)
    assert test_db.get_message(msg_id) is None