# code_generator_server.py

# Import necessary libraries
import os
import uuid
import random
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor

# Firebase Admin SDK imports
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK
# On Render, you will set your service account key as an environment variable
# or a secret file. Here, we'll try to load from a file, which is good practice
# for local development. For production, the key should be a secret.
try:
    # Use the path to your service account key file
    cred = credentials.Certificate(os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY_PATH", "firebase_service_account.json"))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Failed to initialize Firebase Admin SDK: {e}")
    db = None

# Initialize Flask app
app = Flask(__name__)

# Thread pool for non-blocking operations like sending emails (optional)
executor = ThreadPoolExecutor(max_workers=5)

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

def add_code_to_firestore(code, email, license_type, expiration_date):
    """Adds the generated code to Firestore."""
    if db:
        try:
            codes_collection_ref = db.collection('codes')
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
    return False

@app.route('/generate_code', methods=['POST'])
def generate_code_endpoint():
    """
    HTTP endpoint to generate and store a new license code.
    Receives JSON data with 'license_type' and 'user_email'.
    """
    if not db:
        return jsonify({"error": "Firebase is not initialized."}), 500

    data = request.get_json()
    license_type = data.get("license_type")
    user_email = data.get("user_email")

    if not license_type or not user_email:
        return jsonify({"error": "Missing 'license_type' or 'user_email' in request body."}), 400

    # Generate the code and expiration date
    new_code = generate_random_code()
    expiration_date = calculate_expiration_date(license_type)

    # Add the new code to Firestore
    if add_code_to_firestore(new_code, user_email, license_type, expiration_date):
        return jsonify({
            "message": "Code generated and added to Firestore successfully.",
            "code": new_code
        }), 200
    else:
        return jsonify({"error": "Failed to add code to Firestore."}), 500

# This is for local testing only. Render will use the Procfile.
if __name__ == '__main__':
    app.run(debug=True, port=5000)

