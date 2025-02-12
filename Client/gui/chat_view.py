import streamlit as st
import logging
from protocol_JSON import chat_client  # Use persistent connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def chat_view():
    logger.info("Rendering chat view")
    st.sidebar.success(f"Logged in as {st.session_state.username}")

    # Fetch and display the list of accounts with unread counts
    logger.info("Fetching list of accounts")
    accounts = chat_client.list_accounts(username=st.session_state.username)
    logger.info(f"Accounts fetched: {accounts}")

    # Ensure session state has necessary structures
    if "user_unread_pair" not in st.session_state:
        st.session_state.user_unread_pair = accounts  # Store unread counts

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = {}  # Store chat history per user

    st.sidebar.subheader("Select a user to chat with")
    for each in st.session_state.user_unread_pair:
        user, unread_count = each['username'], each['unread_count']
        if st.sidebar.button(f"{user} ({unread_count} unread)"):
            logger.info(f"User selected to chat with: {user}")
            st.session_state.selected_user = user
            st.session_state.unread_count = unread_count
            st.session_state.chat_loaded = False

            # Ensure message history is initialized
            if user not in st.session_state.chat_messages:
                st.session_state.chat_messages[user] = []

    selected_user = st.session_state.get("selected_user", None)

    if selected_user:
        logger.info(f"Displaying chat interface for user: {selected_user}")
        st.title(f"Chat with {selected_user}")

        unread_count = next((user['unread_count'] for user in st.session_state.user_unread_pair if user['username'] == selected_user), None)

        num_messages = st.number_input(
            f"Enter the number of unread messages to load (Max: {unread_count}):",
            min_value=0,
            max_value=int(unread_count),
            value=int(unread_count),
            step=1,
        )

        if st.button("Submit"):
            logger.info(f"Fetching {num_messages} messages for {selected_user}")
            new_messages = chat_client.read_messages(num_messages)

            # Store fetched messages separately
            st.session_state.chat_messages[selected_user].extend(new_messages)

            # Reduce unread count
            st.session_state.user_unread_pair[selected_user] -= num_messages
            st.session_state.chat_loaded = True

            st.rerun()

        # Display chat messages
        messages = st.session_state.chat_messages[selected_user]
        for index, message in enumerate(messages):
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                st.write(f"**{message['user']}**: {message['text']}")
            with col2:
                if st.button("Delete", key=f"delete_{selected_user}_{index}"):
                    logger.info(
                        f"Deleting message at index {index} for user {selected_user}"
                    )
                    messages.pop(index)
                    st.session_state.chat_messages[selected_user] = messages
                    st.rerun()

        # Chat input
        user_input = st.text_input("Type your message here...")

        if st.button("Send"):
            if user_input:
                logger.info(
                    f"Sending message from {st.session_state.username} to {selected_user}"
                )

                # Send the message to the server using the persistent connection
                response = chat_client.send_message(selected_user, user_input)

                if response.get("status") == "success":
                    # Append the message to the local chat history
                    st.session_state.chat_messages[selected_user].append(
                        {
                            "user": st.session_state.username,
                            "text": user_input,
                        }
                    )
                    logger.info("Message sent successfully")
                else:
                    st.error("Failed to send message. Please try again.")

                st.rerun()

    else:
        logger.info("No user selected for chat")
        st.write("Please select a user from the sidebar to start chatting.")

    # Logout button
    if st.button("Logout"):
        logger.info(f"User {st.session_state.username} logged out")
        chat_client.logout()  # Close connection properly
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.user_unread_pair = {}
        st.session_state.chat_messages = {}
        st.rerun()

    # Delete account button
    if st.button("Delete Account"):
        logger.info(f"User {st.session_state.username} requested account deletion")
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.user_unread_pair = {}
        st.session_state.chat_messages = {}
        st.rerun()
