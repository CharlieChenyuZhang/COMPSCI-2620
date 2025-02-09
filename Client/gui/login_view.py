import streamlit as st

def login_view():
    """Handles user login UI."""
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username and password:  # Mock authentication
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.user_chats = {
                "Alice": [
                    {"user": "Alice", "text": "Hey there!"},
                    {"user": "Chenyu", "text": "Hi Alice, how's it going?"},
                    {"user": "Alice", "text": "Pretty good! Just working on a project."}
                ],
                "Bob": [
                    {"user": "Bob", "text": "Hello! How are you?"},
                    {"user": "Chenyu", "text": "Hey Bob, I'm doing well. What about you?"},
                    {"user": "Bob", "text": "I'm great! Just enjoying my day."}
                ],
                "Charlie": [
                    {"user": "Charlie", "text": "Nice to meet you!"},
                    {"user": "Chenyu", "text": "Nice to meet you too, Charlie! What do you do?"},
                    {"user": "Charlie", "text": "I work as a software engineer. How about you?"}
                ],
            }
            st.rerun()
        else:
            st.error("Invalid username or password.")
