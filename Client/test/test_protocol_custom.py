import unittest
from unittest.mock import patch, MagicMock
from protocol_custom import CustomChatClient

class TestCustomChatClient(unittest.TestCase):
    def setUp(self):
        self.client = CustomChatClient()

    @patch('Client.protocol_custom.socket.socket')
    def test_connect(self, mock_socket):
        self.client.connect()
        mock_socket.return_value.connect.assert_called_once_with((self.client.server_host, self.client.server_port))
        self.assertTrue(self.client.connected)

    @patch('Client.protocol_custom.socket.socket')
    def test_disconnect(self, mock_socket):
        self.client.connect()
        self.client.disconnect()
        mock_socket.return_value.close.assert_called_once()
        self.assertFalse(self.client.connected)

    @patch('Client.protocol_custom.socket.socket')
    def test_send_request(self, mock_socket):
        mock_socket.return_value.recv.return_value = b'SUCCESS'
        response = self.client.send_request("TEST REQUEST")
        self.assertEqual(response, "SUCCESS")

    @patch('Client.protocol_custom.CustomChatClient.send_request')
    def test_create_account(self, mock_send_request):
        mock_send_request.return_value = "SUCCESS"
        response = self.client.create_account("user", "pass")
        self.assertEqual(response, "SUCCESS")

    @patch('Client.protocol_custom.CustomChatClient.send_request')
    def test_login(self, mock_send_request):
        mock_send_request.return_value = "SUCCESS"
        response = self.client.login("user", "pass")
        self.assertEqual(response, "SUCCESS")

    @patch('Client.protocol_custom.CustomChatClient.send_request')
    def test_send_message(self, mock_send_request):
        mock_send_request.return_value = "SUCCESS"
        response = self.client.send_message("recipient", "message")
        self.assertEqual(response, "SUCCESS")

    @patch('Client.protocol_custom.CustomChatClient.send_request')
    def test_read_messages(self, mock_send_request):
        mock_send_request.return_value = "MESSAGES 0"
        response = self.client.read_messages(10)
        self.assertEqual(response, "MESSAGES 0")

    @patch('Client.protocol_custom.CustomChatClient.send_request')
    def test_list_accounts(self, mock_send_request):
        mock_send_request.return_value = "ACCOUNTS 0"
        response = self.client.list_accounts()
        self.assertEqual(response, {})

    @patch('Client.protocol_custom.CustomChatClient.send_request')
    def test_delete_account(self, mock_send_request):
        mock_send_request.return_value = "SUCCESS"
        response = self.client.delete_account("user", "pass")
        self.assertEqual(response, "SUCCESS")

    def test_logout(self):
        with patch.object(self.client, 'disconnect') as mock_disconnect:
            self.client.logout()
            mock_disconnect.assert_called_once()

if __name__ == '__main__':
    unittest.main() 