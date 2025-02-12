import tkinter as tk
from tkinter import messagebox
import logging
from protocol_JSON import ChatClient  # Ensure this module is correctly implemented

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class SignupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sign Up")
        self.root.geometry("300x250")

        self.chat_client = ChatClient()  # Create ChatClient instance

        tk.Label(root, text="New Username:").pack(pady=5)
        self.new_username_entry = tk.Entry(root)
        self.new_username_entry.pack(pady=5)

        tk.Label(root, text="New Password:").pack(pady=5)
        self.new_password_entry = tk.Entry(root, show="*")
        self.new_password_entry.pack(pady=5)

        tk.Label(root, text="Confirm Password:").pack(pady=5)
        self.confirm_password_entry = tk.Entry(root, show="*")
        self.confirm_password_entry.pack(pady=5)

        self.signup_button = tk.Button(root, text="Sign Up", command=self.signup)
        self.signup_button.pack(pady=10)

    def signup(self):
        new_username = self.new_username_entry.get()
        new_password = self.new_password_entry.get()
        confirm_password = self.confirm_password_entry.get()

        logger.info(f"Signup attempt for username: {new_username}")

        if not new_username or not new_password or not confirm_password:
            logger.warning("Signup attempt with missing fields")
            messagebox.showwarning("Error", "Please fill in all fields.")
            return

        if new_password != confirm_password:
            logger.warning(f"Password mismatch during signup for username: {new_username}")
            messagebox.showerror("Error", "Passwords do not match!")
            return

        logger.info(f"Attempting to create account for username: {new_username}")
        response = self.chat_client.create_account(new_username, new_password)
        logger.debug(f"Server response for {new_username}: {response}")

        if response.get("status") == "success":
            logger.info(f"Successfully created account for username: {new_username}")
            messagebox.showinfo("Success", f"Account created for {new_username}! You can now log in.")
            self.root.destroy()  # Close signup window after success
        else:
            error_msg = response.get("message", "Failed to create account.")
            logger.error(f"Failed to create account for {new_username}: {error_msg}")
            messagebox.showerror("Error", error_msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = SignupApp(root)
    root.mainloop()
