import streamlit as st
from gui.login_view import login_view
from gui.signup_view import signup_view
from gui.chat_view import chat_view

def main():
    st.title("gRPC Chat Client")

    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.messages = []

    # Show login & signup if not authenticated
    if not st.session_state.authenticated:
        login_tab, signup_tab = st.tabs(["Login", "Sign Up"])
        with login_tab:
            login_view()
        with signup_tab:
            signup_view()
    else:
        chat_view()

if __name__ == "__main__":
    main() 