import streamlit as st
import logging
from protocol_JSON import ChatClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_chat_client():
    """Retrieve or initialize a chat client for each user session."""
    if "chat_client" not in st.session_state:
        st.session_state.chat_client = ChatClient()
    return st.session_state.chat_client

def login_view():
    """Handles user login UI."""
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        logger.info(f"Login attempt for username: {username}")
        
        if username and password:
            logger.info(f"Attempting to authenticate user: {username}")
            chat_client = get_chat_client()
            response = chat_client.login(username, password)
            logger.debug(f"Server response for login attempt by {username}: {response}")
            
            if response.get("status") == "success":
                logger.info(f"Successful login for user: {username}")
                st.session_state.authenticated = True
                st.session_state.username = username
                st.rerun()
            else:
                logger.warning(f"Failed login attempt for user: {username}")
                st.error(response.get("message", "Invalid username or password."))
        else:
            logger.warning("Login attempt with missing credentials")
            st.error("Please enter both username and password.")
