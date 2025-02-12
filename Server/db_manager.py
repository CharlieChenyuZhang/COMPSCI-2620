import sqlite3
import bcrypt
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path="./chat.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # create accounts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS accounts (
                    username TEXT PRIMARY KEY,
                    password BLOB NOT NULL
                )
            ''')
            
            # create messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    read BOOLEAN DEFAULT 0,
                    FOREIGN KEY (sender) REFERENCES accounts (username) ON DELETE CASCADE,
                    FOREIGN KEY (recipient) REFERENCES accounts (username) ON DELETE CASCADE
                )
            ''')
            
            # enable foreign key support
            cursor.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    def store_message(self, sender, recipient, content):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (sender, recipient, content) VALUES (?, ?, ?)",
                (sender, recipient, content)
            )
            conn.commit()
            return cursor.lastrowid

    def get_messages(self, username, other_user=None, count=None, unread_only=False, read_only=False, message_sender=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if unread_only:
                query = """
                    SELECT id, sender, content, timestamp 
                    FROM messages 
                    WHERE recipient = ? AND sender = ? AND read = 0 
                    ORDER BY timestamp DESC
                """
                cursor.execute(query, (username, message_sender))
            else:
                if other_user:
                    base_query = """
                        SELECT id, sender, content, timestamp 
                        FROM messages 
                        WHERE ((sender = ? AND recipient = ?) 
                        OR (sender = ? AND recipient = ?))
                    """
                    if read_only:
                        base_query += " AND read = 1"
                    base_query += " ORDER BY timestamp DESC"
                    
                    params = (username, other_user, other_user, username)
                    if count:
                        cursor.execute(base_query + " LIMIT ?", params + (count,))
                    else:
                        cursor.execute(base_query, params)
                else:
                    return []
                        
            return [{
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'timestamp': row[3]
            } for row in cursor.fetchall()]
                                                            
    def get_message(self, message_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sender, recipient, content, timestamp, read 
                FROM messages 
                WHERE id = ?
                """,
                (message_id,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    'id': result[0],
                    'sender': result[1],
                    'recipient': result[2],
                    'content': result[3],
                    'timestamp': result[4],
                    'read': bool(result[5])
                }
            return None

    def get_unread_messages(self, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sender, content, timestamp 
                FROM messages 
                WHERE recipient = ? AND read = 0 
                ORDER BY timestamp
                """,
                (username,)
            )
            return [{
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'timestamp': row[3]
            } for row in cursor.fetchall()]
    
    def read_messages(self, username, count):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sender, content, timestamp 
                FROM messages 
                WHERE recipient = ? AND read = 0
                ORDER BY timestamp 
                LIMIT ?
                """,
                (username, count)
            )
            messages = [{
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'timestamp': row[3]
            } for row in cursor.fetchall()]
            
            if messages:
                message_ids = [msg['id'] for msg in messages]
                placeholders = ','.join('?' * len(message_ids))
                cursor.execute(
                    f"DELETE FROM messages WHERE id IN ({placeholders})",
                    message_ids
                )
                conn.commit()
                
            return messages

    def get_past_messages(self, username, count):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sender, content, timestamp, read 
                FROM messages 
                WHERE recipient = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (username, count)
            )
            return [{
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'timestamp': row[3],
                'read': bool(row[4])
            } for row in cursor.fetchall()]

    def mark_message_read(self, message_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET read = 1 WHERE id = ?",
                (message_id,)
            )
            conn.commit()

    def mark_messages_read(self, username, message_sender=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET read = 1 WHERE recipient = ? AND sender = ? AND read = 0",
                (username, message_sender)
            )
            conn.commit()

    def delete_message(self, message_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM messages WHERE id = ?",
                (message_id,)
            )
            conn.commit()

    def delete_account(self, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # cascade will automatically delete related messages
            cursor.execute(
                "DELETE FROM accounts WHERE username = ?",
                (username,)
            )
            conn.commit()

    def get_unread_count(self, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient = ? AND read = 0",
                (username,)
            )
            return cursor.fetchone()[0]
        
    def get_unread_count_from_sender(self, recipient, sender):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM messages 
                WHERE recipient = ? AND sender = ? AND read = 0
                """,
                (recipient, sender)
            )
            return cursor.fetchone()[0]
        
    def get_unread_messages(self, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sender, content, timestamp 
                FROM messages 
                WHERE recipient = ? AND read = 0 
                ORDER BY timestamp DESC
                """,
                (username,)
            )
            return [{
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'timestamp': row[3]
            } for row in cursor.fetchall()]

    def get_past_messages(self, username, count):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sender, content, timestamp 
                FROM messages 
                WHERE recipient = ? AND read = 1
                ORDER BY timestamp DESC 
                LIMIT ?
                """,
                (username, count)
            )
            return [{
                'id': row[0],
                'sender': row[1],
                'message': row[2],
                'timestamp': row[3]
            } for row in cursor.fetchall()]

    def create_account(self, username, hashed_password):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO accounts (username, password) VALUES (?, ?)",
                    (username, hashed_password)
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def verify_account(self, username, password):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password FROM accounts WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            
            if result:
                stored_password = result[0]
                try:
                    return bcrypt.checkpw(password.encode('utf-8'), stored_password)
                except ValueError:
                    return False
            return False
        
    def get_account(self, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT username, password FROM accounts WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    'username': result[0],
                    'password': result[1]
                }
            return None

    def list_accounts(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM accounts")
            return [row[0] for row in cursor.fetchall()]

    def account_exists(self, username):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM accounts WHERE username = ?",
                (username,)
            )
            return cursor.fetchone() is not None