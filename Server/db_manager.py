import sqlite3
import bcrypt

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
            
            # create messages table for future use
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    read BOOLEAN DEFAULT 0,
                    FOREIGN KEY (sender) REFERENCES accounts (username),
                    FOREIGN KEY (recipient) REFERENCES accounts (username)
                )
            ''')
            
            conn.commit()

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
                return bcrypt.checkpw(password.encode('utf-8'), stored_password)
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