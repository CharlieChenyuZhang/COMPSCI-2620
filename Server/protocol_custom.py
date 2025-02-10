from protocol_base import ProtocolBase

class CustomProtocol(ProtocolBase):
    def encode_response(self, response_dict):
        status = response_dict.get('status')
        message = response_dict.get('message', '')
        
        if status == 'success':
            if 'unread_count' in response_dict:
                # Login/Create Account response
                return f"SUCCESS {response_dict['unread_count']}".encode('utf-8')
            elif 'accounts' in response_dict:
                # List accounts response
                accounts = response_dict['accounts']
                return f"ACCOUNTS {len(accounts)} {' '.join(accounts)}".encode('utf-8')
            elif 'messages' in response_dict:
                # Read messages response
                messages = response_dict['messages']
                message_parts = []
                for msg in messages:
                    content = msg['message']
                    message_parts.append(f"{msg['sender']} {len(content)} {content}")
                return f"MESSAGES {len(messages)} {' '.join(message_parts)}".encode('utf-8')
            else:
                # Generic success response
                return b"SUCCESS"
        else:
            # Error response
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
                    'pattern': parts[1] if len(parts) > 1 else '*'
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
                    'action': 'load-unread' if parts[1].lower() == 'unread' else 'load-past',
                    'count': int(parts[2]) if len(parts) > 2 else None,
                    'recipient': parts[3] if len(parts) > 3 else None
                }
            elif action == 'delete':
                return {
                    'action': 'delete',
                    'message_id': int(parts[1])
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