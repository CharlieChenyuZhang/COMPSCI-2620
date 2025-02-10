Custom Wire Protocol
Account Creation and Login:
Request: CREATE <username> <hashed_password> or LOGIN <username> <hashed_password>
Response: SUCCESS <unread_count> or ERROR <message>

List Accounts:
Request: LIST <pattern>
Response: ACCOUNTS <count> <username1> <username2> ...

Send Message:
Request: SEND <recipient> <message_length> <message>
Response: SUCCESS or ERROR <message>

Read Messages:
Request: READ <count>
Response: MESSAGES <count> <sender1> <message1_length> <message1> ...

Delete Message:
Request: DELETE <message_id>
Response: SUCCESS or ERROR <message>

Delete Account:
Request: DELETE_ACCOUNT <username> <hashed_password>
Response: SUCCESS or ERROR <message>

JSON-Based Protocol
Account Creation and Login:
Request: {"action": "create", "username": "<username>", "password": "<hashed_password>"} or {"action": "login", "username": "<username>", "password": "<hashed_password>"}
Response: {"status": "success", "unread_count": <count>} or {"status": "error", "message": "<error_message>"}

List Accounts:
Request: {"action": "list", "pattern": "<pattern>"}
Response: {"status": "success", "accounts": ["<username1>", "<username2>", ...]}

Send Message:
Request: {"action": "send", "recipient": "<recipient>", "message": "<message>"}
Response: {"status": "success"} or {"status": "error", "message": "<error_message>"}

Read Messages:
Request: {"action": "read", "count": <count>}
Response: {"status": "success", "messages": [{"sender": "<sender1>", "message": "<message1>"}, ...]}

Delete Message:
Request: {"action": "delete", "message_id": "<message_id>"}
Response: {"status": "success"} or {"status": "error", "message": "<error_message>"}

Delete Account:
Request: {"action": "delete_account", "username": "<username>", "password": "<hashed_password>"}
Response: {"status": "success"} or {"status": "error", "message": "<error_message>"}
