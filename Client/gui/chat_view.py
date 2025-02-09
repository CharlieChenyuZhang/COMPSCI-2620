import streamlit as st

def chat_view():
    st.sidebar.success(f"Logged in as {st.session_state.username}")

    # Fake user list in sidebar
    st.sidebar.subheader("Select a user to chat with")
    for user in st.session_state.user_chats.keys():
        if st.sidebar.button(user):
            st.session_state.selected_user = user

    selected_user = st.session_state.get("selected_user", None)

    if selected_user:
        # Display chat interface
        st.title(f"Chat with {selected_user}")

        # Display chat messages
        messages = st.session_state.user_chats[selected_user]
        for message in messages:
            st.write(f"**{message['user']}**: {message['text']}")

        # Chat input
        user_input = st.text_input("Type your message here...")

        if st.button("Send"):
            if user_input:
                messages.append({"user": st.session_state.username, "text": user_input})
                st.session_state.user_chats[selected_user] = messages
                st.rerun()
    else:
        st.write("Please select a user from the sidebar to start chatting.")

    # Logout button
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.user_chats = {}
        st.rerun()