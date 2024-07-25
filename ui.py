import streamlit as st
import os
import tempfile
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from log_analysis import download_file, check_log_values, get_limits_from_sheet, extract_sysid_thismav, \
    extract_date_time_from_filename
from drive import get_authorization_url, get_credentials, build_drive_service
from sheets import build_sheets_service
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io

ROOT_FOLDER_ID = st.secrets["ROOT_FOLDER_ID"]
SHEET_ID = st.secrets["SHEET_ID"]

def main_app():
    st.title("Log Analysis Tool")

    # Check if we have stored credentials
    if 'credentials' not in st.session_state:
        # If not, start the OAuth flow
        auth_url = get_authorization_url()
        st.write(f"Please visit this URL to authorize the application: {auth_url}")
        auth_code = st.text_input("Enter the authorization code:")
        if auth_code:
            credentials = get_credentials(auth_code)
            st.session_state['credentials'] = credentials
    
    if 'credentials' in st.session_state:
        credentials = st.session_state['credentials']
        drive_service = build_drive_service(credentials)
        sheets_service = build_sheets_service(credentials)

        root_folder_id = ROOT_FOLDER_ID
        folders = list_items(drive_service, root_folder_id, 'application/vnd.google-apps.folder')
        selected_folder = st.selectbox("Select Folder", list(folders.keys()))

        if selected_folder:
            sub_folders = list_items(drive_service, folders[selected_folder]['id'], 'application/vnd.google-apps.folder')
            selected_sub_folder = st.selectbox("Select Sub Folder", list(sub_folders.keys()))

            if selected_sub_folder:
                log_files = list_items(drive_service, sub_folders[selected_sub_folder]['id'], 'application/octet-stream')
                log_file_options = list(log_files.keys())
                selected_log_file = st.selectbox("Select Log File", log_file_options)

                sheet_names = ['Log analyzer Backend - Bullet', 'Log analyzer Backend - Fighter',
                               'Log analyzer Backend - Aeroswift']
                selected_sheet = st.selectbox("Select Sheet", sheet_names)

                if selected_log_file and selected_sheet:
                    if st.button("Analyze"):
                        file_id = log_files[selected_log_file]['id']
                        with st.spinner("Downloading log file..."):
                            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                                log_file_path = temp_file.name
                                try:
                                    download_file(drive_service, file_id, log_file_path)
                                except Exception as e:
                                    st.error(f"Error downloading log file: {e}")
                                    return

                        with st.spinner("Retrieving limits from Google Sheets..."):
                            try:
                                limits = get_limits_from_sheet(sheets_service, SHEET_ID, selected_sheet)
                                st.write(f"Limits retrieved: {limits}")
                            except Exception as e:
                                st.error(f"Error retrieving limits: {e}")
                                return

                        with st.spinner("Analyzing log file..."):
                            try:
                                sysid_thismav = extract_sysid_thismav(log_file_path)
                                st.write(f"SYSID_THISMAV: {sysid_thismav}")

                                aircraft_model, aircraft_name = None, None
                                if sysid_thismav:
                                    aircraft_model, aircraft_name = get_aircraft_info(sheets_service, SHEET_ID,
                                                                                      sysid_thismav)
                                    st.write(f"Aircraft Model: {aircraft_model}")
                                    st.write(f"Aircraft Name: {aircraft_name}")

                                date, time = extract_date_time_from_filename(selected_log_file)
                                if date:
                                    st.write(f"Log Date: {date}")
                                if time:
                                    st.write(f"Log Time: {time}")

                                analysis_results = check_log_values(log_file_path, limits)
                                st.write("Analysis Results:")
                                st.dataframe(analysis_results)

                                # Create PDF download button
                                pdf_buffer = create_pdf(aircraft_model, aircraft_name, date, time, analysis_results)
                                st.download_button(
                                    label="Download PDF Report",
                                    data=pdf_buffer,
                                    file_name="log_analysis_report.pdf",
                                    mime="application/pdf"
                                )

                            except Exception as e:
                                st.error(f"Error analyzing log file: {str(e)}")
                                raise  # This will print the full traceback in the Streamlit app

                        # Clean up the temporary file
                        os.unlink(log_file_path)

if __name__ == "__main__":
    main_app()
