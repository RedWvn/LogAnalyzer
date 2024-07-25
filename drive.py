# drive.py
import os  # Add this import
import pickle
import base64
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# OAuth 2.0 setup
SCOPES = ['https://www.googleapis.com/auth/drive']
TOKEN_PATH = 'token.pickle'
CREDENTIALS_PATH = 'credentials.json'

# Decode the Base64 credentials and write to 'credentials.json'
base64_credentials = os.getenv('GOOGLE_CREDENTIALS_BASE64')
if base64_credentials:
    with open(CREDENTIALS_PATH, 'wb') as f:
        f.write(base64.b64decode(base64_credentials))

def authenticate_gdrive(auth_code=None):
    creds = None

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        flow = Flow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        # Use your local redirect URI for testing
        flow.redirect_uri = 'http://localhost:8501'

        if auth_code:
            try:
                flow.fetch_token(code=auth_code)
                creds = flow.credentials

                # Save the credentials for the next run
                with open(TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                raise Exception(f"Failed to fetch token: {e}")
        else:
            auth_url, _ = flow.authorization_url(prompt='consent')
            return auth_url  # Return the URL for the user to visit

    service = build('drive', 'v3', credentials=creds)
    return service

def list_items(service, folder_id, mime_type=None):
    # Example function to list items in a folder
    query = f"'{folder_id}' in parents"
    if mime_type:
        query += f" and mimeType='{mime_type}'"
    results = service.files().list(q=query, pageSize=10, fields="files(id, name)").execute()
    return results.get('files', [])

def download_file(service, file_id, destination):
    request = service.files().get_media(fileId=file_id)
    with open(destination, 'wb') as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")
    return destination
