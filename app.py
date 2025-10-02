import os
import csv
import json
import requests
from flask import Flask, request, render_template, abort
from datetime import datetime
from itertools import zip_longest

# ==============================================================================
# --- 1. CONFIGURATION: UPDATE THESE VALUES ---
# ==============================================================================


# Replace with your actual Pipedrive API key.
PIPEDRIVE_API_TOKEN = '6e737e4f78bff26687bd12190c8b5de2df87c08c'

# Your company's unique domain in Pipedrive.
PIPEDRIVE_COMPANY_DOMAIN = 'whitelabeliq' # e.g., 'whitelabeliq'

# -- Webhook Configuration --
# ACTION: Use a strong, secret token that you will also use in Fathom/Zapier.
WEBHOOK_SECRET_TOKEN = 'sdfaksnfas' # e.g., 'sdfaksnfas'

# *** NEW: Set the domain for internal users that should be ignored ***
# Notes will NOT be added for any attendee with this in their email.
EXCLUDED_DOMAIN = '@whitelabeliq.com'



# -- Server & Logging Configuration --
RAW_LOG_FILE = 'fathom_meeting_log.jsonl'
# *** A SINGLE, COMPREHENSIVE CSV LOG FOR ALL ACTIONS ***
AUDIT_LOG_FILE = 'attendee_audit_log.csv'

app = Flask(__name__)

# ==============================================================================
# --- 2. UNIFIED LOGGING FUNCTION ---
# ==============================================================================

def log_attendee_status(attendee_name, attendee_email, meeting_title, status, person_id='N/A'):
    """Appends the status of each processed attendee to a single CSV audit log."""
    print(f"CSV LOG: Recording status for {attendee_email} as '{status}'")
    file_exists = os.path.isfile(AUDIT_LOG_FILE)
    
    try:
        with open(AUDIT_LOG_FILE, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['timestamp', 'attendee_name', 'attendee_email', 'meeting_title', 'status', 'pipedrive_person_id']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
            
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'attendee_name': attendee_name,
                'attendee_email': attendee_email,
                'meeting_title': meeting_title,
                'status': status,
                'pipedrive_person_id': person_id
            })
    except Exception as e:
        print(f"CRITICAL ERROR: Could not write to audit log file '{AUDIT_LOG_FILE}': {e}")


# ==============================================================================
# --- 3. PIPEDRIVE API FUNCTIONS (No changes needed) ---
# ==============================================================================

def find_person_details_by_email(email):
    """Searches for a person by email and returns their details (id, name, email) as a dict."""
    print(f"PIPEDRIVE: Searching for person with email: {email}")
    url = f"https://{PIPEDRIVE_COMPANY_DOMAIN}.pipedrive.com/v1/persons/search"
    params = {'term': email, 'fields': 'email', 'exact_match': True, 'api_token': PIPEDRIVE_API_TOKEN}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get('data') and data['data'].get('items'):
            person_data = data['data']['items'][0]['item']
            person_id = person_data.get('id')
            person_name = person_data.get('name')
            if person_id:
                print(f"PIPEDRIVE SUCCESS: Found Person '{person_name}' (ID: {person_id})")
                return {'id': person_id, 'name': person_name, 'email': email}
        # This is NOT an error, just means they aren't in Pipedrive. The log will capture this.
        return None
    except requests.exceptions.RequestException as e:
        print(f"PIPEDRIVE API ERROR during search: {e}")
        return None

def add_note_to_person(person_id, note_content):
    """Adds a note to a Person and returns True on success."""
    print(f"PIPEDRIVE: Adding note to Person ID {person_id}")
    url = f"https://{PIPEDRIVE_COMPANY_DOMAIN}.pipedrive.com/v1/notes"
    params = {'api_token': PIPEDRIVE_API_TOKEN}
    payload = {'content': note_content, 'person_id': person_id}
    try:
        response = requests.post(url, params=params, json=payload)
        response.raise_for_status()
        if response.json().get('success'):
            print(f"PIPEDRIVE SUCCESS: Note was added to Person ID {person_id}.")
            return True
        else:
            print(f"PIPEDRIVE ERROR: Failed to add note: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"PIPEDRIVE API ERROR while adding note: {e}")
        return False

# ==============================================================================
# --- 4. FLASK WEB SERVER (Final Logic) ---
# ==============================================================================

def get_attendees_from_payload(payload):
    """Parses invitee strings into a structured list of {'name': str, 'email': str}."""
    attendees_list = []
    names_str = payload.get('invitees', '')
    emails_str = payload.get('invitees_email', '')
    if emails_str and isinstance(emails_str, str):
        names = [name.strip() for name in names_str.split(',')]
        emails = [email.strip() for email in emails_str.split(',')]
        for name, email in zip_longest(names, emails, fillvalue=''):
            if email:
                attendees_list.append({'name': name, 'email': email})
    return attendees_list

@app.route('/webhook', methods=['POST'])
def fathom_webhook_handler():
    """Catches webhook, processes each attendee, and logs their status to the audit CSV."""
    if request.args.get('token') != WEBHOOK_SECRET_TOKEN: abort(403)
    payload = request.json
    if not payload: return 'Empty payload received', 400

    print("\n--- NEW WEBHOOK RECEIVED ---")
    
    # Log raw payload for the demo page
    try:
        raw_log_entry = {'received_at': datetime.now().isoformat(), 'payload': payload}
        with open(RAW_LOG_FILE, 'a', encoding='utf-8') as f: f.write(json.dumps(raw_log_entry) + '\n')
        print(f"WEBHOOK: Logged meeting: \"{payload.get('title', 'N/A')}\"")
    except Exception as e:
        print(f"SERVER CRITICAL ERROR: Could not write to raw log file: {e}")
        return "Internal Server Error", 500

    title = payload.get('title', 'Untitled Meeting')
    recording_url = payload.get('recording_url')
    attendees = get_attendees_from_payload(payload)
    
    if not attendees:
        print("AUDIT: No attendee emails found in payload. Nothing to process.")
        return 'Webhook received, but no attendee emails to process.', 200

    # Construct note content (it's the same for everyone in this meeting)
    note_content = f"<h2>{title}</h2>"
    if recording_url: note_content += f'<p><strong>Recording Link:</strong> <a href="{recording_url}" target="_blank">{recording_url}</a></p>'
    note_content += "<h4>Attendees:</h4><ul>"
    for attendee in attendees: note_content += f"<li>{attendee.get('name', 'N/A')} ({attendee.get('email')})</li>"
    note_content += "</ul>"
    
    print(f"AUDIT: Processing {len(attendees)} attendee(s)...")
    
    for attendee in attendees:
        email = attendee['email']
        name = attendee['name']

        if EXCLUDED_DOMAIN in email:
            print(f"AUDIT: Skipping internal email: {email}")
            continue

        person_details = find_person_details_by_email(email)
        
        if person_details:
            # Attendee FOUND in Pipedrive
            note_added = add_note_to_person(person_details['id'], note_content)
            if note_added:
                log_attendee_status(name, email, title, "Found and Note Added", person_details['id'])
            else:
                # This case is rare but good to handle (e.g., API error during note POST)
                log_attendee_status(name, email, title, "Found but Note Failed", person_details['id'])
        else:
            # Attendee NOT FOUND in Pipedrive
            log_attendee_status(name, email, title, "Not Found in Pipedrive")

    print("--- WEBHOOK PROCESSING COMPLETE ---")
    return 'Webhook received and processed successfully!', 200

@app.route('/')
def show_demo_page():
    """Reads the Fathom log and renders the interactive demo page (no changes here)."""
    meetings = []
    if not os.path.exists(RAW_LOG_FILE):
        return render_template('demo.html', meetings=meetings, error="Log file not found.")
    try:
        with open(RAW_LOG_FILE, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                log_entry = json.loads(line)
                payload = log_entry.get('payload', {})
                timestamp_iso = log_entry.get('received_at', '')
                formatted_time = datetime.fromisoformat(timestamp_iso).strftime('%B %d, %Y at %I:%M %p') if timestamp_iso else 'N/A'
                meetings.append({
                    'id': i, 'title': payload.get('title', 'No Title'),
                    'summary': payload.get('summary', 'No summary available.'),
                    'attendees': get_attendees_from_payload(payload),
                    'recording_url': payload.get('recording_url'), 'logged_at': formatted_time
                })
    except Exception as e:
        return render_template('demo.html', meetings=[], error=f"Error reading log file: {e}")
    return render_template('demo.html', meetings=reversed(meetings))

# ==============================================================================
# --- 5. MAIN EXECUTION ---
# ==============================================================================
if __name__ == '__main__':
    if not os.path.exists('templates'): os.makedirs('templates')
    print("Starting Fathom-Pipedrive Integration Server...")
    app.run(host='0.0.0.0', port=5000, debug=False)
