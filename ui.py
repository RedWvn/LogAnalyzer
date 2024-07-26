import streamlit as st
import os
import tempfile
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from log_analysis import download_file, check_log_values, get_limits_from_sheet, extract_sysid_thismav, \
    extract_date_time_from_filename
from drive import get_authorization_url, get_credentials, build_drive_service, list_items
from sheets import build_sheets_service
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io

ROOT_FOLDER_ID = st.secrets["ROOT_FOLDER_ID"]
SHEET_ID = st.secrets["SHEET_ID"]

def create_pdf(aircraft_model, aircraft_name, date, time, analysis_results):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []

    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']

    elements.append(Paragraph("Log Analysis Report", title_style))
    elements.append(Spacer(1, 0.25*inch))
    
    if aircraft_model and aircraft_name:
        elements.append(Paragraph(f"Aircraft: {aircraft_model} - {aircraft_name}", subtitle_style))
    if date and time:
        elements.append(Paragraph(f"Log Date: {date} {time}", subtitle_style))
    
    elements.append(Spacer(1, 0.25*inch))

    data = [["Parameter", "Min Value", "Max Value", "Status"]]
    for param, values in analysis_results.items():
        data.append([param, values['min'], values['max'], values['status']])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

def main_app():
    st.title("Log Analysis Tool")

    # Check if we have stored credentials
    if 'credentials' not in st.session_state:
        # Check if we're handling a callback from OAuth
        params = st.experimental_get_query_params()
        if 'code' in params:
            try:
                code = params['code'][0]
                credentials = get_credentials(code)
                st.session_state['credentials'] = credentials
                # Clear the URL parameters
                st.experimental_set_query_params()
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Error during authorization: {str(e)}")
                st.session_state.pop('oauth_state', None)
        else:
            # If not, start the OAuth flow
            auth_url, state = get_authorization_url()
            st.session_state['oauth_state'] = state
            st.markdown(f"[Click here to authorize the application]({auth_url})")
    
    if 'credentials' in st.session_state:
        credentials = st.session_state['credentials']
        drive_service = build_drive_service(credentials)
        sheets_service = build_sheets_service(credentials)
        root_folder_id = ROOT_FOLDER_ID
        folders = {folder['name']: folder for folder in list_items(drive_service, root_folder_id, 'application/vnd.google-apps.folder')}
        selected_folder = st.selectbox("Select Folder", list(folders.keys()))

        if selected_folder:
            sub_folders = {folder['name']: folder for folder in list_items(drive_service, folders[selected_folder]['id'], 'application/vnd.google-apps.folder')}
            selected_sub_folder = st.selectbox("Select Sub Folder", list(sub_folders.keys()))

            if selected_sub_folder:
                log_files = {file['name']: file for file in list_items(drive_service, sub_folders[selected_sub_folder]['id'], 'application/octet-stream')}
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
                                    aircraft_model, aircraft_name = get_aircraft_info(sheets_service, SHEET_ID, sysid_thismav)
                                    st.write(f"Aircraft Model: {aircraft_model}")
                                    st.write(f"Aircraft Name: {aircraft_name}")
                        
                                date, time = extract_date_time_from_filename(selected_log_file)
                                if date:
                                    st.write(f"Log Date: {date}")
                                if time:
                                    st.write(f"Log Time: {time}")
                        
                                analysis_results = check_log_values(log_file_path, limits)
                                if isinstance(analysis_results, pd.DataFrame) and not analysis_results.empty:
                                    st.write("Analysis Results:")
                                    st.dataframe(analysis_results)
                                else:
                                    st.warning("No analysis results were produced. The log file might be empty or not contain the expected data.")
                        
                                # Create PDF download button
                                if isinstance(analysis_results, pd.DataFrame) and not analysis_results.empty:
                                    pdf_buffer = create_pdf(aircraft_model, aircraft_name, date, time, analysis_results)
                                    st.download_button(
                                        label="Download PDF Report",
                                        data=pdf_buffer,
                                        file_name="log_analysis_report.pdf",
                                        mime="application/pdf"
                                    )
                            except Exception as e:
                                st.error(f"Error analyzing log file: {str(e)}")
                                st.exception(e)  # This will display the full traceback in the Streamlit app
                        
                                                # Clean up the temporary file
                                                os.unlink(log_file_path)

if __name__ == "__main__":
    main_app()
