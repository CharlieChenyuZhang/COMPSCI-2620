import streamlit as st
import logging
from protocol_JSON import list_accounts  # or from protocol_custom import list_accounts

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def chat_view():
    logger.info("Rendering chat view")
    st.sidebar.success(f"Logged in as {st.session_state.username}")
    
    # Fetch and display the list of accounts with unread counts
    logger.info("Fetching list of accounts")
    accounts = list_accounts()
    logger.info(f"Accounts fetched: {accounts}")
    st.session_state.user_chats = accounts

    st.sidebar.subheader("Select a user to chat with")
    for user, unread_count in st.session_state.user_chats.items():
        if st.sidebar.button(f"{user} ({unread_count} unread)"):
            logger.info(f"User selected to chat with: {user}")
            st.session_state.selected_user = user

    selected_user = st.session_state.get("selected_user", None)

    if selected_user:
        logger.info(f"Displaying chat interface for user: {selected_user}")
        st.title(f"Chat with {selected_user}")

        # Display chat messages
        messages = st.session_state.user_chats[selected_user]
        for index, message in enumerate(messages):
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                st.write(f"**{message['user']}**: {message['text']}")
            with col2:
                if st.button("Delete", key=f"delete_{index}"):
                    logger.info(f"Deleting message at index {index} for user {selected_user}")
                    messages.pop(index)
                    st.session_state.user_chats[selected_user] = messages
                    st.rerun()

        # Chat input
        user_input = st.text_input("Type your message here...")

        if st.button("Send"):
            if user_input:
                logger.info(f"Sending message from {st.session_state.username} to {selected_user}")
                messages.append({"user": st.session_state.username, "text": user_input})
                st.session_state.user_chats[selected_user] = messages
                st.rerun()
    else:
        logger.info("No user selected for chat")
        st.write("Please select a user from the sidebar to start chatting.")

    # Logout button
    if st.button("Logout"):
        logger.info(f"User {st.session_state.username} logged out")
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.user_chats = {}
        st.rerun()

    # Add this code block after the existing Logout button code
    if st.button("Delete Account"):
        logger.info(f"User {st.session_state.username} requested account deletion")
        # Perform any necessary account deletion logic here
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.user_chats = {}
        st.rerun()