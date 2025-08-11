# code_generator_server.py
#
# This Flask-based web server listens for requests to automatically
# generate and store license codes in Firebase Firestore. It now uses the
# same code generation logic as the desktop app for consistency, and
# stores the codes in a format that the desktop app's listener can read.

# Import necessary libraries
import os
import random
import string
import json
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
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

# --- CORS Configuration ---
try:
    main_app_url = os.environ.get("MAIN_APP_URL")
    origins_list = [main_app_url] if main_app_url else ["*"]
    CORS(app, origins=origins_list)
    print(f"CORS configured to allow requests from: {origins_list}")
except Exception as e:
    print(f"Failed to configure CORS: {e}. Falling back to allowing all origins.")
    CORS(app, origins=["*"])

# Configuration settings for the code generator server.
class GeneratorConfig:
    """
    Stores configuration settings.
    CODE_LENGTH and CODE_CHARACTERS must match the desktop app for consistency.
    """
    SMTP_SERVER = os.environ.get("SMTP_SERVER")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

    # --- UPDATED: Match the desktop app's code format ---
    GENERATOR_COLLECTION = "license_codes" # This should match the collection name in the desktop app
    CODE_LENGTH = 50
    CODE_CHARACTERS = string.ascii_letters + string.digits + string.punctuation

# Firebase initialization
if firestore:
    try:
        # Load Firebase service account key from the secret file path
        secret_file_path = "/etc/secrets/firebase_service_account.json"
        if os.path.exists(secret_file_path):
            cred = credentials.Certificate(secret_file_path)
            # Check if an app is already initialized to avoid re-initialization
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            _firebase_initialized = True
            print("Firebase Admin SDK initialized successfully from Secret File.")
        else:
            print("Firebase service account secret file not found. Firebase disabled.")
            _firebase_initialized = False
    except Exception as e:
        print(f"Failed to initialize Firebase Admin SDK: {e}")
        _firebase_initialized = False

# --- Code Generation and Email Sending Logic ---
def generate_random_code():
    """
    Generates a random, complex code that matches the format of the desktop app.
    This function is a direct copy of the one in the desktop app.
    """
    return ''.join(random.choice(GeneratorConfig.CODE_CHARACTERS) for _ in range(GeneratorConfig.CODE_LENGTH))


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
@app.route("/", methods=["GET"])
def home():
    """A simple route for the root URL."""
    return "Sales Manager Code Generator is running!", 200

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

    # --- UPDATED: Use the new code generation logic ---
    new_code = generate_random_code()
    expiration_date = calculate_expiration_date(license_type)

    try:
        doc_ref = db.collection(GeneratorConfig.GENERATOR_COLLECTION).document(new_code)
        doc = doc_ref.get()

        if doc.exists:
            # Handle collision by trying again
            print("Warning: Code collision detected. Retrying...")
            return generate_code_endpoint()

        # Store the new code in Firestore with 'automatic' generation method
        doc_ref.set({
            'license_type': license_type,
            'used_globally': False,
            'generation_method': 'automatic',
            'generated_date': firestore.SERVER_TIMESTAMP,
            'used_by_machine_id': None,
            'used_date': None,
            'email': user_email,
            'expiration_date': expiration_date.isoformat(),
            'created_at': datetime.now().isoformat(),
            'status': 'active'
        })
    except Exception as e:
        print(f"Firebase operation failed: {e}")
        return jsonify({"error": "Failed to add code to Firestore."}), 500

    # Send the code via email asynchronously
    subject = "Your Super Sales Manager Code"
    body = f"""
    <html>
        <body>
            <p>Hello,</p>
            <p>Thank you for subscribing to Super Sales Manager. Your unique code is:</p>
            <pre style="background-color: #f1f1f1; padding: 10px; border-radius: 5px; overflow-wrap: break-word;">
                <code style="font-family: monospace; font-size: 14px;">{new_code}</code>
            </pre>
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
