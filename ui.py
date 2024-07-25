import streamlit as st
import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from log_analysis import download_file, check_log_values, get_limits_from_sheet, extract_sysid_thismav, \
    extract_date_time_from_filename
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io

SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/spreadsheets.readonly']
ROOT_FOLDER_ID = '1dOD1aA8HWB9Rjus7nG9Phld3LjoZ6YZG'
SHEET_ID = '1NxM6OrX-y2tthbvLe6DRv_pFR1PgX1l3y4QP1jBAmOo'


def authenticate_google():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def list_items(service, folder_id, mime_type):
    query = f"'{folder_id}' in parents and mimeType='{mime_type}' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    return {item['name']: item['id'] for item in items}


def get_aircraft_info(service, sheet_id, sysid_thismav):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range="System ID!A:C").execute()
    values = result.get('values', [])

    for row in values[1:]:  # Skip header row
        if len(row) > 2 and row[2] and int(row[2]) == int(sysid_thismav):
            return row[0], row[1]  # Return Aircraft Model and Aircraft Name

    return None, None


def create_pdf(aircraft_model, aircraft_name, log_date, log_time, analysis_results):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30,
                            bottomMargin=18)
    elements = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Small', fontSize=8, leading=10))

    elements.append(Paragraph("Log Analysis Report", styles['Title']))
    elements.append(Spacer(1, 0.25 * inch))
    elements.append(Paragraph(f"Aircraft Model: {aircraft_model}", styles['Normal']))
    elements.append(Paragraph(f"Aircraft Name: {aircraft_name}", styles['Normal']))
    elements.append(Paragraph(f"Log Date: {log_date}", styles['Normal']))
    if log_time:
        elements.append(Paragraph(f"Log Time: {log_time}", styles['Normal']))
    elements.append(Spacer(1, 0.25 * inch))

    # Convert DataFrame to a list of lists and ensure all values are strings
    data = [analysis_results.columns.tolist()]
    for _, row in analysis_results.iterrows():
        data.append([str(cell) for cell in row])

    # Calculate column widths based on content
    col_widths = [max(len(str(row[i])) for row in data) * 5 for i in range(len(data[0]))]

    # Limit the maximum width of each column
    max_width = 100
    col_widths = [min(width, max_width) for width in col_widths]

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer


def main_app():
    st.title("Log Analysis Tool")

    creds = authenticate_google()
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)

    root_folder_id = ROOT_FOLDER_ID
    folders = list_items(drive_service, root_folder_id, 'application/vnd.google-apps.folder')
    selected_folder = st.selectbox("Select Folder", list(folders.keys()))

    if selected_folder:
        sub_folders = list_items(drive_service, folders[selected_folder], 'application/vnd.google-apps.folder')
        selected_sub_folder = st.selectbox("Select Sub Folder", list(sub_folders.keys()))

        if selected_sub_folder:
            log_files = list_items(drive_service, sub_folders[selected_sub_folder], 'application/octet-stream')
            log_file_options = list(log_files.keys())
            selected_log_file = st.selectbox("Select Log File", log_file_options)

            sheet_names = ['Log analyzer Backend - Bullet', 'Log analyzer Backend - Fighter',
                           'Log analyzer Backend - Aeroswift']
            selected_sheet = st.selectbox("Select Sheet", sheet_names)

            if selected_log_file and selected_sheet:
                if st.button("Analyze"):
                    file_id = log_files[selected_log_file]
                    with st.spinner("Downloading log file..."):
                        log_file_path = os.path.join(os.path.expanduser("~"), "Downloads", selected_log_file)
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


if __name__ == "__main__":
    main_app()