import streamlit as st
import protocol_JSON
import logging
from constants import Actions, ResponseStatus, ResponseFields

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def login_view():
    """Handles user login UI."""
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        logger.info(f"Login attempt for username: {username}")
        
        if username and password:
            logger.info(f"Attempting to authenticate user: {username}")
            response = protocol_JSON.login(username, password)
            logger.debug(f"Server response for login attempt by {username}: {response}")
            
            if response.get(ResponseFields.STATUS) == ResponseStatus.SUCCESS:
                logger.info(f"Successful login for user: {username}")
                st.session_state.authenticated = True
                st.session_state.username = username
                st.rerun()
            else:
                logger.warning(f"Failed login attempt for user: {username}")
                st.error(response.get(ResponseFields.MESSAGE, "Invalid username or password."))
        else:
            logger.warning("Login attempt with missing credentials")
            st.error("Please enter both username and password.")
