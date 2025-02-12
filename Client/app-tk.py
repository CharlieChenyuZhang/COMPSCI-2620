import tkinter as tk
from tkinter import messagebox
from tk-gui.login_view import LoginApp
from tk-gui.signup_view import SignupApp
# from tk-gui.chat_view_tk import ChatApp  # Assuming you have a Chat GUI

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Application")
        self.root.geometry("400x300")

        self.authenticated = False
        self.username = None

        self.show_main_menu()

    def show_main_menu(self):
        """Displays the main login/signup menu."""
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(self.root, text="Welcome to Chat App", font=("Arial", 14)).pack(pady=20)

        login_button = tk.Button(self.root, text="Login", command=self.open_login)
        login_button.pack(pady=10)

        signup_button = tk.Button(self.root, text="Sign Up", command=self.open_signup)
        signup_button.pack(pady=10)

    def open_login(self):
        """Opens the login window."""
        login_window = tk.Toplevel(self.root)
        login_app = LoginApp(login_window, self)

    def open_signup(self):
        """Opens the signup window."""
        signup_window = tk.Toplevel(self.root)
        signup_app = SignupApp(signup_window, self)

    def on_login_success(self, username):
        """Callback when login is successful."""
        self.authenticated = True
        self.username = username
        # self.show_chat_view()

    # def show_chat_view(self):
    #     """Displays the chat window after login."""
    #     for widget in self.root.winfo_children():
    #         widget.destroy()

    #     chat_app = ChatApp(self.root, self.username)

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()
