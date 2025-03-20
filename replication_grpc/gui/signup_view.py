import streamlit as st
import logging
from grpc_client import ChatClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_chat_client():
    """Retrieve or initialize a chat client for each user session."""
    if "chat_client" not in st.session_state:
        st.session_state.chat_client = ChatClient()
    return st.session_state.chat_client

def signup_view():
    """Handles user sign-up UI."""
    st.subheader("Create a New Account")
    
    new_username = st.text_input("New Username")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    if st.button("Sign Up"):
        logger.info(f"Signup attempt for username: {new_username}")

        if not new_username or not new_password or not confirm_password:
            logger.warning("Signup attempt with missing fields")
            st.error("Please fill in all fields.")
            return

        if new_password != confirm_password:
            logger.warning(f"Password mismatch during signup for username: {new_username}")
            st.error("Passwords do not match!")
            return

        logger.info(f"Attempting to create account for username: {new_username}")
        chat_client = get_chat_client()
        response = chat_client.create_account(new_username, new_password)
        logger.debug(f"Server response for {new_username}: {response}")

        if response.get("status") == "success":
            logger.info(f"Successfully created account for username: {new_username}")
            st.success(f"Account created for {new_username}! You can now log in.")
            st.session_state.authenticated = True
            st.session_state.username = new_username
            st.rerun()
        else:
            error_msg = response.get("message", "Failed to create account.")
            logger.error(f"Failed to create account for {new_username}: {error_msg}")
            st.error(error_msg)
