from protocol_base import ProtocolBase

class CustomProtocol(ProtocolBase):
    def encode_response(self, response_dict):
        status = response_dict.get('status')
        message = response_dict.get('message', '')
        
        if status == 'success':
            if 'unread_count' in response_dict:
                return f"SUCCESS {response_dict['unread_count']}".encode('utf-8')
            elif 'accounts' in response_dict:
                account_parts = []
                for acc in response_dict['accounts']:
                    account_parts.extend([acc['username'], str(acc['unread_count'])])
                return f"ACCOUNTS {len(response_dict['accounts'])} {' '.join(account_parts)}".encode('utf-8')
            elif 'messages' in response_dict:
                messages = response_dict['messages']
                message_parts = []
                for msg in messages:
                    content = msg['message']
                    message_parts.append(f"{msg['sender']} {len(content)} {content}")
                return f"MESSAGES {len(messages)} {' '.join(message_parts)}".encode('utf-8')
            else:
                return b"SUCCESS"
        else:
            return f"ERROR {message}".encode('utf-8')
        
    def decode_request(self, data):
        try:
            parts = data.decode('utf-8').split()
            if not parts:
                return {'action': None}

            action = parts[0].lower()
            if action == 'create':
                return {
                    'action': 'create',
                    'username': parts[1],
                    'password': parts[2]
                }
            elif action == 'login':
                return {
                    'action': 'login',
                    'username': parts[1],
                    'password': parts[2]
                }
            elif action == 'list':
                return {
                    'action': 'list',
                    'pattern': parts[1],
                    'user_name': parts[2]
                }
            elif action == 'send':
                recipient = parts[1]
                msg_length = int(parts[2])
                message = ' '.join(parts[3:3+msg_length])
                return {
                    'action': 'send',
                    'recipient': recipient,
                    'message': message
                }
            elif action == 'read':
                return {
                    'action': 'read',
                    'count': int(parts[1])
                }
            elif action == 'delete':
                # Support multiple message IDs
                message_ids = [int(mid) for mid in parts[1:]]
                return {
                    'action': 'delete',
                    'message_ids': message_ids
                }
            elif action == 'delete_account':
                return {
                    'action': 'delete_account',
                    'username': parts[1],
                    'password': parts[2]
                }
            else:
                return {'action': None}
        except Exception as e:
            print(f"Error decoding request: {e}")
            return {'action': None}

    def create_response(self, status, message, additional_data=None):
        response = {
            'status': 'success' if status else 'error',
            'message': message
        }
        if additional_data:
            response.update(additional_data)
        return response