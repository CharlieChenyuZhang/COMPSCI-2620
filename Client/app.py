import streamlit as st
from gui.login_view import login_view
from gui.signup_view import signup_view
from gui.chat_view import chat_view

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.messages = []  # Store chat messages

# Show login & signup if not authenticated
if not st.session_state.authenticated:
    st.title("Login & Sign Up")

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        login_view()
    with signup_tab:
        signup_view()
else:
    chat_view()  # Show only chat after login
