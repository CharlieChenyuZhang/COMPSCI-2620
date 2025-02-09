import streamlit as st

def signup_view():
    """Handles user sign-up UI."""
    st.subheader("Create a New Account")
    new_username = st.text_input("New Username")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    if st.button("Sign Up"):
        if new_password != confirm_password:
            st.error("Passwords do not match!")
        elif new_username and new_password:
            st.success(f"Account created for {new_username}! You can now log in.")
        else:
            st.error("Please fill in all fields.")
