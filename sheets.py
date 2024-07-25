from googleapiclient.discovery import build

def build_sheets_service(credentials):
    return build('sheets', 'v4', credentials=credentials)

def get_sheet_data(service, sheet_id, range_name):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = result.get('values', [])
    return values

def list_items(service, folder_id, mime_type):
    query = f"'{folder_id}' in parents and mimeType='{mime_type}' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])
    return items
