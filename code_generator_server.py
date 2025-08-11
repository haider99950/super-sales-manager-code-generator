# code_generator_server.py

# Import necessary libraries
import os
import uuid
import random
import string
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS # Import Flask-CORS to handle cross-origin requests
from concurrent.futures import ThreadPoolExecutor

# Email libraries
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Firebase Admin SDK imports
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    _firebase_initialized = False
except ImportError:
    print("Firebase Admin SDK not found. Please install it: pip install firebase-admin")
    _firebase_initialized = False
    firestore = None

# Thread pool for non-blocking operations like sending emails
executor = ThreadPoolExecutor(max_workers=5)

# --- App Initialization and Configuration ---
app = Flask(__name__)
# Allow cross-origin requests from your main app's URL
CORS(app, resources={r"/*": {"origins": os.environ.get("MAIN_APP_URL")}})

# Configuration settings for the code generator server.
class GeneratorConfig:
    SMTP_SERVER = os.environ.get("SMTP_SERVER")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
    GENERATOR_COLLECTION = "generated_codes"
    CODE_LENGTH = 16

# Firebase initialization
if firestore:
    try:
        # Load the Firebase service account key from the environment variable as a JSON string
        firebase_service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")
        if firebase_service_account_json:
            service_account_info = json.loads(firebase_service_account_json)
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            _firebase_initialized = True
            print("Firebase Admin SDK initialized successfully.")
        else:
            print("FIREBASE_SERVICE_ACCOUNT_KEY environment variable not set. Firebase disabled.")
    except Exception as e:
        print(f"Failed to initialize Firebase Admin SDK: {e}")
        _firebase_initialized = False

# --- Code Generation and Email Sending Logic ---
def generate_random_code(length=16, prefix="L"):
    """Generates a random alphanumeric code."""
    # Add a unique UUID part and a random string part
    code_uuid = str(uuid.uuid4()).replace('-', '')
    code_random = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    return f"{prefix}-{code_random}-{code_uuid[:8]}".upper()

def calculate_expiration_date(license_type):
    """Calculates the expiration date based on license type."""
    if license_type == "monthly":
        # Add 30 days for a monthly plan
        return datetime.now() + timedelta(days=30)
    elif license_type == "annual":
        # Add 365 days for an annual plan
        return datetime.now() + timedelta(days=365)
    else:
        # Default to a short trial period if type is unknown
        return datetime.now() + timedelta(days=7)

def store_code_in_firestore(code, email, license_type, expiration_date):
    """Stores the generated code in Firestore."""
    if not _firebase_initialized:
        print("Firestore not initialized, skipping database storage.")
        return False
    try:
        codes_collection_ref = db.collection(GeneratorConfig.GENERATOR_COLLECTION)
        doc_ref = codes_collection_ref.document() # Let Firestore generate the document ID
        doc_ref.set({
            'code': code,
            'email': email,
            'license_type': license_type,
            'expiration_date': expiration_date.isoformat(),
            'created_at': datetime.now().isoformat(),
            'status': 'active'
        })
        print(f"Code added to Firestore: {code}")
        return True
    except Exception as e:
        print(f"Firebase operation failed: {e}")
        return False

def send_email_async(to_email, subject, body):
    """Sends an email in a non-blocking way using a thread pool."""
    executor.submit(_send_email, to_email, subject, body)

def _send_email(to_email, subject, body):
    """Helper function to send the email."""
    if not all([GeneratorConfig.SMTP_SERVER, GeneratorConfig.SMTP_USERNAME, GeneratorConfig.SMTP_PASSWORD, GeneratorConfig.SENDER_EMAIL]):
        print("SMTP configuration is incomplete. Cannot send email.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = GeneratorConfig.SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(GeneratorConfig.SMTP_SERVER, GeneratorConfig.SMTP_PORT)
        server.starttls()
        server.login(GeneratorConfig.SMTP_USERNAME, GeneratorConfig.SMTP_PASSWORD)
        server.sendmail(GeneratorConfig.SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
        print(f"Successfully sent email to {to_email}.")
    except Exception as e:
        print(f"Failed to send email to {to_email}. Error: {e}")

# --- Flask Routes ---
@app.route('/generate_code', methods=['POST'])
def generate_code_endpoint():
    """
    HTTP endpoint to generate and store a new license code.
    Receives JSON data with 'license_type' and 'user_email'.
    """
    if not _firebase_initialized:
        return jsonify({"error": "Firebase is not initialized."}), 500

    data = request.get_json()
    license_type = data.get("license_type")
    user_email = data.get("user_email")

    if not license_type or not user_email:
        return jsonify({"error": "Missing 'license_type' or 'user_email' in request body."}), 400

    # Generate the code and expiration date
    new_code = generate_random_code()
    expiration_date = calculate_expiration_date(license_type)

    # Store the new code in Firestore
    if not store_code_in_firestore(new_code, user_email, license_type, expiration_date):
         return jsonify({"error": "Failed to add code to Firestore."}), 500

    # Send the code via email asynchronously
    subject = "Your Super Sales Manager Code"
    body = f"""
    <html>
        <body>
            <p>Hello,</p>
            <p>Thank you for subscribing to Super Sales Manager. Your unique code is:</p>
            <h2 style="color: #4f46e5; font-weight: bold;">{new_code}</h2>
            <p>This code is used to activate your subscription features in the application.</p>
            <p>Best regards,<br>The Super Sales Manager Team</p>
        </body>
    </html>
    """
    send_email_async(user_email, subject, body)

    return jsonify({
        "message": "Code generated, added to Firestore, and email sent.",
        "code": new_code
    }), 200

# --- Health Check Route for Render ---
@app.route('/health', methods=['GET'])
def health_check():
    """A simple health check endpoint."""
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    app.run(debug=True, port=os.environ.get("PORT", 5001))
