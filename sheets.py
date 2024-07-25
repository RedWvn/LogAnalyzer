from googleapiclient.discovery import build

def build_sheets_service(credentials):
    return build('sheets', 'v4', credentials=credentials)

def get_sheet_data(service, sheet_id, range_name):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = result.get('values', [])
    return values

def get_aircraft_info(service, sheet_id, sysid_thismav):
    range_name = 'Aircraft List!A2:C'
    values = get_sheet_data(service, sheet_id, range_name)
    for row in values:
        if row[0] == sysid_thismav:
            return row[1], row[2]
    return None, None
