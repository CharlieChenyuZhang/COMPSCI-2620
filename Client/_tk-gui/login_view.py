import tkinter as tk
from tkinter import messagebox
import logging
from protocol_JSON import ChatClient
# from protocol_Custom import ChatClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class LoginApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Login")
        self.root.geometry("300x200")

        self.chat_client = ChatClient()  # Create ChatClient instance

        tk.Label(root, text="Username:").pack(pady=5)
        self.username_entry = tk.Entry(root)
        self.username_entry.pack(pady=5)

        tk.Label(root, text="Password:").pack(pady=5)
        self.password_entry = tk.Entry(root, show="*")
        self.password_entry.pack(pady=5)

        self.login_button = tk.Button(root, text="Login", command=self.login)
        self.login_button.pack(pady=10)

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        logger.info(f"Login attempt for username: {username}")

        if not username or not password:
            logger.warning("Login attempt with missing credentials")
            messagebox.showwarning("Error", "Please enter both username and password.")
            return

        response = self.chat_client.login(username, password)
        logger.debug(f"Server response for login attempt by {username}: {response}")

        if response.get("status") == "success":
            logger.info(f"Successful login for user: {username}")
            messagebox.showinfo("Success", "Login successful!")
            self.root.destroy()  # Close the login window after success
        else:
            logger.warning(f"Failed login attempt for user: {username}")
            messagebox.showerror("Error", response.get("message", "Invalid username or password."))

if __name__ == "__main__":
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()
