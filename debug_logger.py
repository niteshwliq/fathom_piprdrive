from flask import Flask, request
from datetime import datetime
import json

app = Flask(__name__)

# The name of our new, detailed log file.
DEBUG_LOG_FILE = 'catch_all_log.txt'

# This is a special "catch-all" route.
# It accepts GET, POST, PUT, DELETE on ANY path.
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    """
    Catches ALL incoming requests, logs everything, and returns a success message.
    """
    # Create a string to hold all the debug information.
    log_output = f"--- Request Received at {datetime.now().isoformat()} ---\n"
    
    # Log the method and full path
    log_output += f"Method: {request.method}\n"
    log_output += f"Path: /{path}\n"
    
    # Log any URL parameters (like '?token=...')
    log_output += f"Query Args: {dict(request.args)}\n"
    
    # Log all the headers sent with the request
    log_output += f"Headers: {dict(request.headers)}\n"
    
    # Log the raw body of the request
    body = request.get_data(as_text=True)
    log_output += f"Body:\n{body}\n"
    
    log_output += "--- End of Request ---\n\n"

    # Print to console and append to the log file
    print(log_output)
    with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_output)
        
    # Always return a '200 OK' so Zapier thinks it succeeded.
    return "Request logged successfully!", 200

if __name__ == '__main__':
    # Start the server. You can use the same port.
    app.run(host='0.0.0.0', port=5000)
