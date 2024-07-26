import os
import io
from pymavlink import mavutil
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import re
from datetime import datetime


def download_file(service, file_id, file_path):
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(file_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")


def get_limits_from_sheet(service, sheet_id, sheet_name):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=f"{sheet_name}!A:F").execute()
    values = result.get('values', [])

    limits = {}
    for row in values[1:]:  # Skip header row
        if row[0].lower() == 'true':  # Check if the parameter should be analyzed
            msg_type = row[1]
            param_name = row[2]
            min_value = float(row[3])
            max_value = float(row[4])
            comment = row[5] if len(row) > 5 else ''
            limits[f"{msg_type}.{param_name}"] = (min_value, max_value, comment)
    return limits


def check_log_values(log_file_path, limits):
    results = []
    try:
        mlog = mavutil.mavlink_connection(log_file_path, dialect='ardupilotmega')
        param_max_min = {param: {'max': float('-inf'), 'min': float('inf')} for param in limits}

        msg_count = 0
        while True:
            msg = mlog.recv_match()
            if not msg:
                break

            msg_count += 1
            if msg_count % 1000 == 0:
                st.write(f"Processed {msg_count} messages...")

            for param, (min_val, max_val, comment) in limits.items():
                try:
                    msg_type, param_name = param.split('.')
                    if msg.get_type() == msg_type and hasattr(msg, param_name):
                        value = getattr(msg, param_name)
                        param_max_min[param]['max'] = max(param_max_min[param]['max'], value)
                        param_max_min[param]['min'] = min(param_max_min[param]['min'], value)
                except Exception as e:
                    st.write(f"Error processing {param}: {e}")

        for param, (min_val, max_val, comment) in limits.items():
            max_value = param_max_min[param]['max']
            min_value = param_max_min[param]['min']
            if min_value < min_val or max_value > max_val:
                status = "Out of range"
            else:
                status = "OK"
            results.append({
                "Msg type": param.split('.')[0],
                "Parameter name": param.split('.')[1],
                "Max value": max_value,
                "Min value": min_value,
                "Range": f"({min_val}, {max_val})",
                "Comments": status if status == "OK" else comment
            })

    except Exception as e:
        st.error(f"Error reading log file: {e}")

    if not results:
        st.warning("No parameters found in log file that match the limits from the sheet.")

    return pd.DataFrame(results)


def extract_sysid_thismav(bin_log_file):
    mlog = mavutil.mavlink_connection(bin_log_file)

    sysid_thismav = None
    while True:
        msg = mlog.recv_match(type='PARM', blocking=True)
        if not msg:
            break
        if msg.Name == 'SYSID_THISMAV':
            sysid_thismav = msg.Value
            break

    return sysid_thismav


def extract_date_time_from_filename(filename):
    pattern = r'(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}-\d{2}))?'
    match = re.search(pattern, filename)

    if match:
        date = match.group(1)
        time = match.group(2)

        if time:
            time = time.replace('-', ':')

        return date, time

    return None, None
