import streamlit as st
import logging
from protocol_JSON import ChatClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def get_chat_client():
    """Retrieve or initialize a chat client for each user session."""
    if "chat_client" not in st.session_state:
        st.session_state.chat_client = ChatClient()
    return st.session_state.chat_client

def chat_view():
    chat_client = get_chat_client()
    
    st.sidebar.success(f"Logged in as {st.session_state.username}")

    # Fetch and display the list of accounts with unread counts
    logger.info("Fetching list of accounts")
    accounts = chat_client.list_accounts(username=st.session_state.username)
    logger.info(f"{st.session_state.username} - Accounts fetched: {accounts}")

    # Ensure session state has necessary structures
    st.session_state.user_unread_pair = accounts  # Store unread counts

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = {}  # Store chat history per user

    st.sidebar.subheader("Select a user to chat with")
    if st.sidebar.button("Reload"):
        accounts = chat_client.list_accounts(username=st.session_state.username)
        st.session_state.user_unread_pair = accounts
        st.rerun()
    
    for each in st.session_state.user_unread_pair:
        user, unread_count = each['username'], each['unread_count']
        if st.sidebar.button(f"{user} ({unread_count} unread)"):
            logger.info(f"{st.session_state.username} - User selected to chat with: {user}")
            st.session_state.selected_user = user
            st.session_state.unread_count = unread_count
            st.session_state.chat_loaded = False

            # Ensure message history is initialized
            if user not in st.session_state.chat_messages:
                st.session_state.chat_messages[user] = []

    selected_user = st.session_state.get("selected_user", None)

    # corner case when user just got removed from the list of users
    is_user_exist = any(user['username'] == selected_user for user in st.session_state.user_unread_pair)
    if selected_user and is_user_exist:
        st.title(f"{st.session_state.username} -> {selected_user}")

        unread_count = next((user['unread_count'] for user in st.session_state.user_unread_pair if user['username'] == selected_user), None)

        # num_messages = st.number_input(
        #     f"Enter the number of unread messages to load (Max: {unread_count}):",
        #     min_value=0,
        #     max_value=int(unread_count),
        #     value=int(unread_count),
        #     step=1,
        # )
        num_messages = unread_count

        if st.button("Load all unread messages"):
            logger.info(f"{st.session_state.username} - Fetching {num_messages} messages for {selected_user}")
            new_messages = chat_client.read_messages(num_messages)

            # Store fetched messages separately
            if new_messages.get("status") == "error":
                st.error(new_messages.get("message"))
                st.rerun()
            else:
                messages = new_messages.get("messages", [])
                # Ensure selected_user is in chat_messages
                if selected_user not in st.session_state.chat_messages:
                    st.session_state.chat_messages[selected_user] = []
                
                # Extend the chat history with new messages
                st.session_state.chat_messages[selected_user].extend(messages)
                
                # Display the messages
                for msg in st.session_state.chat_messages[selected_user]:
                    st.write(f"{msg['sender']}: {msg['message']}")

            # Reduce unread count
            for user in st.session_state.user_unread_pair:
                if user['username'] == selected_user:
                    user['unread_count'] = max(0, user['unread_count'] - num_messages)
                    break
            # st.session_state.user_unread_pair[selected_user]['unread_count'] -= num_messages
            st.session_state.chat_loaded = True

            st.rerun()

        # Display chat messages
        if selected_user:
            messages = st.session_state.chat_messages[selected_user]
            for index, message in enumerate(messages):
                col1, col2 = st.columns([0.8, 0.2])
                with col1:
                    st.write(f"**{message['sender']}**: {message['message']}")
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
                logger.info(f"{st.session_state.username} - send_message response {response}")
                if response.get("status") == "success":
                    # Append the message to the local chat history
                    st.session_state.chat_messages[selected_user].append(
                        {
                            "sender": st.session_state.username,
                            "message": user_input,
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
        logger.info(f"{st.session_state.username} - User {st.session_state.username} logged out")
        chat_client.logout()  # Close connection properly
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.selected_user = None
        st.session_state.unread_count = 0
        st.session_state.chat_loaded = False
        st.session_state.user_unread_pair = {}
        st.session_state.chat_messages = {}
        st.rerun()

    # Delete account button
    # --- Delete account section ---
    st.markdown("---")
    st.subheader("Delete Your Account")
    delete_password = st.text_input("Enter your password to confirm deletion:", type="password")
    if st.button("Delete Account"):
        if not delete_password:
            st.error("Please enter your password to confirm account deletion.")
        else:
            logger.info(f"{st.session_state.username} - User requested account deletion")
            # Call the protocol_JSON.py to delete the account (username + password)
            response = chat_client.delete_account(st.session_state.username, delete_password)
            logger.info(f"{st.session_state.username} - delete_account response {response}")


            chat_client.logout()  # Close connection
            st.session_state.authenticated = False
            st.session_state.username = None
            st.session_state.user_unread_pair = {}
            st.session_state.chat_messages = {}
            st.rerun()
            
