import streamlit as st
from ui import main_app
import os

# Set page config
st.set_page_config(page_title="Log Analysis Tool", layout="wide")

# Set up environment variables
os.environ['GOOGLE_CLIENT_ID'] = st.secrets["GOOGLE_CLIENT_ID"]
os.environ['GOOGLE_CLIENT_SECRET'] = st.secrets["GOOGLE_CLIENT_SECRET"]
os.environ['GOOGLE_REDIRECT_URI'] = st.secrets["GOOGLE_REDIRECT_URI"]

def main():
    main_app()

if __name__ == "__main__":
    main()
