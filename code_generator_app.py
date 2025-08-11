# code_generator_app.py

import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import random
import string
from datetime import datetime
import os
import threading
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver
import time
from concurrent.futures import ThreadPoolExecutor
import requests  # Import requests for shutting down the Flask server gracefully

# Flask is used for the web server to handle incoming POST requests.
try:
    from flask import Flask, request, jsonify

    _flask_available = True
except ImportError:
    _flask_available = False
    print("Flask not found. Automatic generation via web server will be disabled.")

# Firebase Admin SDK imports
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    from firebase_admin import exceptions as firebase_exceptions

    _firebase_initialized = False
except ImportError:
    messagebox.showerror("Import Error", "Firebase Admin SDK not found. Please install it: pip install firebase-admin")
    _firebase_initialized = False
    firestore = None

# Thread pool for non-blocking operations like sending emails
executor = ThreadPoolExecutor(max_workers=5)


# Configuration
class GeneratorConfig:
    """
    Stores configuration settings, color palettes, and other constants for the app.
    """
    PRIMARY_BG = "#E3F2FD"
    SECONDARY_BG = "#FFFFFF"
    ACCENT_MAIN = "#1977D2"
    ACCENT_SUCCESS = "#4CAF50"
    ACCENT_DANGER = "#D32F2F"
    TEXT_DARK = "#263238"
    TEXT_LIGHT = "#78909C"
    BORDER_COLOR = "#BBDEFB"
    HEADER_BG = "#1565C0"
    HOVER_COLOR = "#E1F5FE"
    BUTTON_HOVER_BG = "#1565C0"
    TREEVIEW_SELECTED_BG = "#B0BEC5"

    FONT_FAMILY = "Roboto"
    FONT_SIZE_SMALL = 9
    FONT_SIZE_NORMAL = 10
    FONT_SIZE_LARGE = 12
    FONT_SIZE_HEADER = 18

    PAD_X_SMALL = 5
    PAD_Y_SMALL = 5
    PAD_X_NORMAL = 10
    PAD_Y_NORMAL = 10
    PAD_X_LARGE = 15
    PAD_Y_LARGE = 15

    FIREBASE_SERVICE_ACCOUNT_KEY_PATH = "firebase_service_account.json"
    CODE_LENGTH = 64
    CODE_CHARACTERS = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"

    # --- Automatic Generation Settings ---
    # NOTE: You MUST replace these with your actual email credentials.
    EMAIL_SENDER = "your_email@example.com"
    EMAIL_PASSWORD = "your_email_password"
    SMTP_SERVER = "smtp.example.com"  # e.g., "smtp.gmail.com" for Gmail
    SMTP_PORT = 587

    WEB_SERVER_HOST = "0.0.0.0"
    WEB_SERVER_PORT = 5000


class SalesManagerCodeGeneratorApp(tk.Tk):
    """
    Main application class for the Sales Manager Code Generator.
    Allows manual and automatic generation and management of license codes
    in Firebase Firestore, with separate tabs for each.
    """

    def __init__(self):
        super().__init__()
        self.title("Sales Manager Code Generator")
        self.geometry("1000x750")
        self.minsize(800, 600)
        self.configure(bg=GeneratorConfig.PRIMARY_BG)

        self.db_firestore = None
        self._firebase_listener_stopper = None
        self._web_server_thread = None
        self.web_server_status_label = None

        self._initialize_firebase()

        if not self.db_firestore:
            messagebox.showerror("Firebase Error", "Firebase is not initialized. Cannot run the Code Generator.")
            self.destroy()
            return

        self._setup_styles()
        self._setup_ui()
        self._start_firestore_listener()

        if _flask_available:
            self._start_web_server()

        # Create a context menu for copying codes
        self.code_context_menu = tk.Menu(self, tearoff=0)
        self.code_context_menu.add_command(label="Copy Code", command=self._copy_selected_code)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _initialize_firebase(self):
        """Initializes Firebase Admin SDK."""
        global _firebase_initialized
        if not _firebase_initialized and firestore:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                service_account_path = os.path.join(script_dir, GeneratorConfig.FIREBASE_SERVICE_ACCOUNT_KEY_PATH)

                if not os.path.exists(service_account_path):
                    messagebox.showerror("Firebase Error",
                                         f"Firebase service account key not found at: {service_account_path}\n"
                                         "Please ensure 'firebase_service_account.json' is in the same directory as this script.")
                    return

                cred = credentials.Certificate(service_account_path)
                if not firebase_admin._apps:
                    firebase_admin.initialize_app(cred)
                self.db_firestore = firestore.client()
                _firebase_initialized = True
                print("Firebase initialized successfully for Code Generator.")
            except Exception as e:
                messagebox.showerror("Firebase Error", f"Failed to initialize Firebase: {e}")
                self.db_firestore = None

    def _setup_styles(self):
        """Applies consistent styling to Tkinter widgets."""
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=GeneratorConfig.PRIMARY_BG, foreground=GeneratorConfig.TEXT_DARK,
                        font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_NORMAL))
        style.configure("TFrame", background=GeneratorConfig.SECONDARY_BG)
        style.configure("TLabel", background=GeneratorConfig.SECONDARY_BG, foreground=GeneratorConfig.TEXT_DARK)
        style.configure("TEntry", fieldbackground=GeneratorConfig.SECONDARY_BG, foreground=GeneratorConfig.TEXT_DARK,
                        bordercolor=GeneratorConfig.BORDER_COLOR, relief="flat", borderwidth=1,
                        padding=[GeneratorConfig.PAD_X_SMALL, GeneratorConfig.PAD_Y_SMALL])
        style.map("TEntry", fieldbackground=[("focus", GeneratorConfig.HOVER_COLOR)],
                  bordercolor=[("focus", GeneratorConfig.ACCENT_MAIN)])

        style.configure("Modern.TButton",
                        background=GeneratorConfig.ACCENT_MAIN, foreground=GeneratorConfig.SECONDARY_BG,
                        font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_NORMAL, 'bold'),
                        borderwidth=0, relief="flat",
                        padding=[GeneratorConfig.PAD_X_LARGE, GeneratorConfig.PAD_Y_NORMAL])
        style.map("Modern.TButton", background=[("active", GeneratorConfig.BUTTON_HOVER_BG)],
                  foreground=[("active", GeneratorConfig.SECONDARY_BG)], relief=[("pressed", "groove")])

        style.configure("Success.Modern.TButton", background=GeneratorConfig.ACCENT_SUCCESS)
        style.map("Success.Modern.TButton", background=[("active", "#388E3C")])

        style.configure("Danger.Modern.TButton", background=GeneratorConfig.ACCENT_DANGER)
        style.map("Danger.Modern.TButton", background=[("active", "#C62828")])

        style.configure("Treeview",
                        background=GeneratorConfig.SECONDARY_BG,
                        foreground=GeneratorConfig.TEXT_DARK,
                        fieldbackground=GeneratorConfig.SECONDARY_BG,
                        bordercolor=GeneratorConfig.BORDER_COLOR,
                        rowheight=25)
        style.map("Treeview", background=[("selected", GeneratorConfig.TREEVIEW_SELECTED_BG)])

        style.configure("Treeview.Heading",
                        background=GeneratorConfig.ACCENT_MAIN,
                        foreground=GeneratorConfig.SECONDARY_BG,
                        font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_NORMAL + 1, 'bold'))

        style.configure("TNotebook", background=GeneratorConfig.PRIMARY_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=GeneratorConfig.ACCENT_MAIN,
                        foreground=GeneratorConfig.SECONDARY_BG,
                        font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_NORMAL, 'bold'),
                        padding=[GeneratorConfig.PAD_X_LARGE, GeneratorConfig.PAD_Y_NORMAL],
                        relief="flat")
        style.map("TNotebook.Tab",
                  background=[("selected", GeneratorConfig.HEADER_BG), ("active", GeneratorConfig.BUTTON_HOVER_BG)],
                  foreground=[("selected", GeneratorConfig.SECONDARY_BG), ("active", GeneratorConfig.SECONDARY_BG)])

    def _setup_ui(self):
        """Sets up the main user interface with tab navigation."""
        main_frame = ttk.Frame(self, padding=(GeneratorConfig.PAD_X_LARGE, GeneratorConfig.PAD_Y_LARGE), style="TFrame")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=GeneratorConfig.PAD_X_NORMAL,
                           pady=GeneratorConfig.PAD_Y_NORMAL)

        # Tab 1: Manual Code Generation
        self.generate_code_tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.generate_code_tab, text="Generate Code (Manual)")
        self._setup_generate_code_tab(self.generate_code_tab)

        # Tab 2: Manual Codes List
        self.manual_codes_tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.manual_codes_tab, text="Manual Codes")
        self._setup_manual_codes_tab(self.manual_codes_tab)

        # Tab 3: Automatic Codes List
        self.automatic_codes_tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.automatic_codes_tab, text="Automatic Codes")
        self._setup_automatic_codes_tab(self.automatic_codes_tab)

    def _setup_generate_code_tab(self, parent_frame):
        """Sets up the UI for the 'Generate Code' tab."""
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=0)
        parent_frame.grid_rowconfigure(1, weight=0)
        parent_frame.grid_rowconfigure(2, weight=1)

        ttk.Label(parent_frame, text="Generate New License Code (Manual)",
                  font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_HEADER, 'bold'),
                  foreground=GeneratorConfig.ACCENT_MAIN, background=GeneratorConfig.SECONDARY_BG).grid(row=0, column=0,
                                                                                                        pady=(
                                                                                                            GeneratorConfig.PAD_Y_LARGE,
                                                                                                            GeneratorConfig.PAD_Y_NORMAL),
                                                                                                        sticky="ew")

        control_frame = ttk.LabelFrame(parent_frame, text="Code Generation Options", style="TFrame",
                                       padding=(GeneratorConfig.PAD_X_LARGE, GeneratorConfig.PAD_Y_LARGE))
        control_frame.grid(row=1, column=0, padx=GeneratorConfig.PAD_X_NORMAL, pady=GeneratorConfig.PAD_Y_NORMAL,
                           sticky="ew")
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_columnconfigure(1, weight=1)
        control_frame.grid_columnconfigure(2, weight=1)
        control_frame.grid_columnconfigure(3, weight=1)

        ttk.Label(control_frame, text="License Type:", style="TLabel").grid(row=0, column=0,
                                                                            padx=GeneratorConfig.PAD_X_NORMAL,
                                                                            pady=GeneratorConfig.PAD_Y_NORMAL,
                                                                            sticky="w")
        self.license_type_var = tk.StringVar(value="monthly")
        monthly_radio = ttk.Radiobutton(control_frame, text="Monthly", variable=self.license_type_var, value="monthly")
        monthly_radio.grid(row=0, column=1, padx=(0, GeneratorConfig.PAD_X_NORMAL), pady=GeneratorConfig.PAD_Y_NORMAL,
                           sticky="w")
        annual_radio = ttk.Radiobutton(control_frame, text="Annual", variable=self.license_type_var, value="annual")
        annual_radio.grid(row=0, column=2, padx=(0, GeneratorConfig.PAD_X_NORMAL), pady=GeneratorConfig.PAD_Y_NORMAL,
                          sticky="w")

        generate_button = ttk.Button(control_frame, text="Generate & Add Code to Firebase",
                                     command=lambda: self._generate_and_add_code_manual(self.license_type_var.get()),
                                     style="Success.Modern.TButton")
        generate_button.grid(row=1, column=0, columnspan=4, pady=GeneratorConfig.PAD_Y_NORMAL, sticky="ew")

        ttk.Label(control_frame, text="Generated Code:", style="TLabel").grid(row=2, column=0,
                                                                              padx=GeneratorConfig.PAD_X_NORMAL,
                                                                              pady=(GeneratorConfig.PAD_Y_NORMAL,
                                                                                    GeneratorConfig.PAD_Y_SMALL),
                                                                              sticky="w")
        self.generated_code_display = ttk.Entry(control_frame, style="TEntry", state="readonly",
                                                width=GeneratorConfig.CODE_LENGTH + 10)
        self.generated_code_display.grid(row=2, column=1, columnspan=3, padx=GeneratorConfig.PAD_X_NORMAL,
                                         pady=(GeneratorConfig.PAD_Y_NORMAL, GeneratorConfig.PAD_Y_SMALL), sticky="ew")

        self.web_server_status_label = ttk.Label(control_frame, text="Web Server: Inactive",
                                                 font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_NORMAL,
                                                       'italic'), foreground="red",
                                                 background=GeneratorConfig.SECONDARY_BG)
        self.web_server_status_label.grid(row=3, column=0, columnspan=4, pady=(GeneratorConfig.PAD_Y_NORMAL, 0),
                                          sticky="ew")

        parent_frame.grid_rowconfigure(2, weight=1)

    def _setup_manual_codes_tab(self, parent_frame):
        """Sets up the UI for the 'Manual Codes' tab."""
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=0)
        parent_frame.grid_rowconfigure(1, weight=1)

        ttk.Label(parent_frame, text="Manually Generated Codes",
                  font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_HEADER, 'bold'),
                  foreground=GeneratorConfig.ACCENT_MAIN, background=GeneratorConfig.SECONDARY_BG).grid(row=0, column=0,
                                                                                                        pady=(
                                                                                                            GeneratorConfig.PAD_Y_LARGE,
                                                                                                            GeneratorConfig.PAD_Y_NORMAL),
                                                                                                        sticky="ew")

        codes_frame = ttk.LabelFrame(parent_frame, text="License Code Details", style="TFrame",
                                     padding=(GeneratorConfig.PAD_X_LARGE, GeneratorConfig.PAD_Y_LARGE))
        codes_frame.grid(row=1, column=0, padx=GeneratorConfig.PAD_X_NORMAL, pady=GeneratorConfig.PAD_Y_NORMAL,
                         sticky="nsew")
        codes_frame.grid_rowconfigure(0, weight=1)
        codes_frame.grid_columnconfigure(0, weight=1)

        self.manual_codes_tree = ttk.Treeview(codes_frame,
                                              columns=("Code", "Type", "Used Globally", "Used By Machine ID",
                                                       "Generated Date", "Used Date"),
                                              show="headings", style="Treeview")
        self.manual_codes_tree.grid(row=0, column=0, sticky="nsew")

        self.manual_codes_tree.heading("Code", text="Code", anchor="w")
        self.manual_codes_tree.heading("Type", text="Type", anchor="center")
        self.manual_codes_tree.heading("Used Globally", text="Used Globally", anchor="center")
        self.manual_codes_tree.heading("Used By Machine ID", text="Used By Machine ID", anchor="w")
        self.manual_codes_tree.heading("Generated Date", text="Generated Date", anchor="center")
        self.manual_codes_tree.heading("Used Date", text="Used Date", anchor="center")

        self.manual_codes_tree.column("Code", width=250, stretch=tk.YES)
        self.manual_codes_tree.column("Type", width=80, stretch=tk.NO, anchor="center")
        self.manual_codes_tree.column("Used Globally", width=100, stretch=tk.NO, anchor="center")
        self.manual_codes_tree.column("Used By Machine ID", width=200, stretch=tk.YES)
        self.manual_codes_tree.column("Generated Date", width=150, stretch=tk.NO, anchor="center")
        self.manual_codes_tree.column("Used Date", width=150, stretch=tk.NO, anchor="center")

        codes_scrollbar = ttk.Scrollbar(codes_frame, orient="vertical", command=self.manual_codes_tree.yview)
        self.manual_codes_tree.configure(yscrollcommand=codes_scrollbar.set)
        codes_scrollbar.grid(row=0, column=1, sticky="ns")

        self.manual_codes_tree.bind("<Button-3>", self._show_code_context_menu)

    def _setup_automatic_codes_tab(self, parent_frame):
        """Sets up the UI for the 'Automatic Codes' tab."""
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=0)
        parent_frame.grid_rowconfigure(1, weight=1)

        ttk.Label(parent_frame, text="Automatically Generated Codes",
                  font=(GeneratorConfig.FONT_FAMILY, GeneratorConfig.FONT_SIZE_HEADER, 'bold'),
                  foreground=GeneratorConfig.ACCENT_MAIN, background=GeneratorConfig.SECONDARY_BG).grid(row=0, column=0,
                                                                                                        pady=(
                                                                                                            GeneratorConfig.PAD_Y_LARGE,
                                                                                                            GeneratorConfig.PAD_Y_NORMAL),
                                                                                                        sticky="ew")

        codes_frame = ttk.LabelFrame(parent_frame, text="License Code Details", style="TFrame",
                                     padding=(GeneratorConfig.PAD_X_LARGE, GeneratorConfig.PAD_Y_LARGE))
        codes_frame.grid(row=1, column=0, padx=GeneratorConfig.PAD_X_NORMAL, pady=GeneratorConfig.PAD_Y_NORMAL,
                         sticky="nsew")
        codes_frame.grid_rowconfigure(0, weight=1)
        codes_frame.grid_columnconfigure(0, weight=1)

        self.automatic_codes_tree = ttk.Treeview(codes_frame,
                                                 columns=("Code", "Type", "Used Globally", "Used By Machine ID",
                                                          "Generated Date", "Used Date"),
                                                 show="headings", style="Treeview")
        self.automatic_codes_tree.grid(row=0, column=0, sticky="nsew")

        self.automatic_codes_tree.heading("Code", text="Code", anchor="w")
        self.automatic_codes_tree.heading("Type", text="Type", anchor="center")
        self.automatic_codes_tree.heading("Used Globally", text="Used Globally", anchor="center")
        self.automatic_codes_tree.heading("Used By Machine ID", text="Used By Machine ID", anchor="w")
        self.automatic_codes_tree.heading("Generated Date", text="Generated Date", anchor="center")
        self.automatic_codes_tree.heading("Used Date", text="Used Date", anchor="center")

        self.automatic_codes_tree.column("Code", width=250, stretch=tk.YES)
        self.automatic_codes_tree.column("Type", width=80, stretch=tk.NO, anchor="center")
        self.automatic_codes_tree.column("Used Globally", width=100, stretch=tk.NO, anchor="center")
        self.automatic_codes_tree.column("Used By Machine ID", width=200, stretch=tk.YES)
        self.automatic_codes_tree.column("Generated Date", width=150, stretch=tk.NO, anchor="center")
        self.automatic_codes_tree.column("Used Date", width=150, stretch=tk.NO, anchor="center")

        codes_scrollbar = ttk.Scrollbar(codes_frame, orient="vertical", command=self.automatic_codes_tree.yview)
        self.automatic_codes_tree.configure(yscrollcommand=codes_scrollbar.set)
        codes_scrollbar.grid(row=0, column=1, sticky="ns")

        self.automatic_codes_tree.bind("<Button-3>", self._show_code_context_menu)

    def _start_web_server(self):
        """Initializes and starts the Flask web server in a separate thread."""
        self.web_server_status_label.config(
            text=f"Web Server: Running on http://{GeneratorConfig.WEB_SERVER_HOST}:{GeneratorConfig.WEB_SERVER_PORT}",
            foreground="green")

        self.flask_app = Flask(__name__)

        @self.flask_app.route('/generate_code', methods=['POST'])
        def generate_code_endpoint():
            """Endpoint for external services to request a new license code."""
            try:
                data = request.get_json()
                license_type = data.get('license_type')
                user_email = data.get('user_email')

                if not license_type or not user_email:
                    return jsonify({"error": "Missing 'license_type' or 'user_email' in request."}), 400

                # Use self.after to schedule the code generation on the main Tkinter thread
                # This is crucial for thread safety with Tkinter widgets
                self.after(0, lambda: self._generate_and_add_code_automatic(license_type, user_email))

                return jsonify({"status": "Code generation request received and is being processed."}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.flask_app.route('/shutdown', methods=['POST'])
        def shutdown_server():
            """Endpoint to shut down the Flask server gracefully."""
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()
            return 'Server shutting down...'

        def run_server():
            """Wrapper function to run the Flask app and catch potential startup errors."""
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            try:
                self.flask_app.run(host=GeneratorConfig.WEB_SERVER_HOST, port=GeneratorConfig.WEB_SERVER_PORT)
            except Exception as e:
                # Update the UI on the main thread if the server fails to start
                self.after(0, lambda: self.web_server_status_label.config(text=f"Web Server: Error - {e}",
                                                                          foreground="red"))

        self._web_server_thread = threading.Thread(target=run_server, daemon=True)
        self._web_server_thread.start()

    def _start_firestore_listener(self):
        """Starts the real-time listener for license code changes in Firestore."""
        if self.db_firestore:
            # The on_snapshot callback is executed in a background thread by the SDK.
            # We must use self.after() to safely update Tkinter widgets from this thread.
            self._firebase_listener_stopper = self.db_firestore.collection('license_codes').on_snapshot(
                self._on_firestore_snapshot)
            print("Firestore listener started.")
        else:
            print("Firestore not initialized, cannot start listener.")

    def _on_firestore_snapshot(self, col_snapshot, changes, read_time):
        """Callback for Firestore real-time updates."""
        self.after(0, self._update_codes_tree_from_snapshot, col_snapshot)

    def _update_codes_tree_from_snapshot(self, col_snapshot):
        """Updates the Treeviews with the latest data from the Firestore snapshot."""
        # Clear existing items from both trees
        for item in self.manual_codes_tree.get_children():
            self.manual_codes_tree.delete(item)
        for item in self.automatic_codes_tree.get_children():
            self.automatic_codes_tree.delete(item)

        # Re-populate with current data from the snapshot, separating by generation method
        for doc in col_snapshot:
            code_data = doc.to_dict()
            code = doc.id
            license_type = code_data.get('license_type', 'N/A')
            used_globally = "Yes" if code_data.get('used_globally', False) else "No"
            used_by_machine_id = code_data.get('used_by_machine_id', 'N/A')
            generation_method = code_data.get('generation_method', 'manual')  # Default to manual for legacy codes

            # Format timestamps for display
            generated_date_ts = code_data.get('generated_date')
            if generated_date_ts and hasattr(generated_date_ts, 'strftime'):
                generated_date = generated_date_ts.strftime("%Y-%m-%d %H:%M:%S")
            elif generated_date_ts:
                generated_date = str(generated_date_ts)
            else:
                generated_date = 'N/A'

            used_date_ts = code_data.get('used_date')
            if used_date_ts and hasattr(used_date_ts, 'strftime'):
                used_date = used_date_ts.strftime("%Y-%m-%d %H:%M:%S")
            elif used_date_ts:
                used_date = str(used_date_ts)
            else:
                used_date = 'N/A'

            if generation_method == 'manual':
                self.manual_codes_tree.insert("", "end", values=(code, license_type, used_globally, used_by_machine_id,
                                                                 generated_date, used_date))
            elif generation_method == 'automatic':
                self.automatic_codes_tree.insert("", "end",
                                                 values=(code, license_type, used_globally, used_by_machine_id,
                                                         generated_date, used_date))

    def _generate_random_code(self):
        """Generates a random, complex code."""
        return ''.join(random.choice(GeneratorConfig.CODE_CHARACTERS) for _ in range(GeneratorConfig.CODE_LENGTH))

    def _generate_and_add_code_manual(self, license_type):
        """Handles manual code generation and adds it to Firestore."""
        if not self.db_firestore:
            messagebox.showerror("Error", "Firebase is not connected.")
            return

        new_code = self._generate_random_code()

        try:
            doc_ref = self.db_firestore.collection('license_codes').document(new_code)
            doc = doc_ref.get()
            if doc.exists:
                messagebox.showwarning("Code Exists",
                                       "A code with this value already exists. Trying to generate another.")
                # Recursively try again with a new code
                self._generate_and_add_code_manual(license_type)
                return

            doc_ref.set({
                'license_type': license_type,
                'used_globally': False,
                'generation_method': 'manual',  # Key addition for separation
                'generated_date': firestore.SERVER_TIMESTAMP,
                'used_by_machine_id': None,
                'used_date': None
            })
            messagebox.showinfo("Success", f"Code generated and added: {new_code}")
            # Update the display on the GUI
            self.generated_code_display.config(state="normal")
            self.generated_code_display.delete(0, tk.END)
            self.generated_code_display.insert(0, new_code)
            self.generated_code_display.config(state="readonly")
        except firebase_exceptions.FirebaseError as fe:
            messagebox.showerror("Firebase Error", f"Firebase operation failed: {fe}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add code to Firebase: {e}")

    def _generate_and_add_code_automatic(self, license_type, user_email):
        """Handles automatic code generation from a web request, adds to Firestore, and sends an email."""
        if not self.db_firestore:
            print("Firebase is not connected, cannot fulfill automatic request.")
            return

        new_code = self._generate_random_code()

        try:
            doc_ref = self.db_firestore.collection('license_codes').document(new_code)
            doc_ref.set({
                'license_type': license_type,
                'used_globally': False,
                'generation_method': 'automatic',  # Key addition for separation
                'generated_date': firestore.SERVER_TIMESTAMP,
                'used_by_machine_id': None,
                'used_date': None
            })
            print(f"Automatically generated code for {user_email}: {new_code}")

            # Send email in a separate thread to avoid blocking the main UI
            executor.submit(self._send_email_notification, user_email, new_code, license_type)

            messagebox.showinfo("Automatic Generation",
                                f"New {license_type} code generated for {user_email} and sent to their email.")
        except firebase_exceptions.FirebaseError as fe:
            messagebox.showerror("Firebase Error", f"Automatic generation failed: {fe}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed during automatic generation process: {e}")

    def _send_email_notification(self, to_email, code, license_type):
        """Sends an email with the newly generated license code."""
        sender_email = GeneratorConfig.EMAIL_SENDER
        sender_password = GeneratorConfig.EMAIL_PASSWORD

        if not sender_email or not sender_password:
            print("Email configuration is incomplete. Cannot send email.")
            return

        message = MIMEMultipart("alternative")
        message["Subject"] = "Your New Sales Manager App License Code"
        message["From"] = sender_email
        message["To"] = to_email

        html = f"""
        <html>
          <body>
            <p>Hello,</p>
            <p>Thank you for your purchase! Here is your new <b>{license_type}</b> license code for the Sales Manager App:</p>
            <h3 style="background-color: #f0f0f0; padding: 10px; border-radius: 5px; text-align: center;">{code}</h3>
            <p>This code is now active and ready to be used.</p>
            <p>Regards,<br>Sales Manager App Team</p>
          </body>
        </html>
        """
        message.attach(MIMEText(html, "html"))

        try:
            # Use SSL/TLS for secure communication
            with smtplib.SMTP(GeneratorConfig.SMTP_SERVER, GeneratorConfig.SMTP_PORT) as server:
                server.starttls()  # Secure the connection
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, to_email, message.as_string())
            print(f"Email successfully sent to {to_email}")
        except Exception as e:
            print(f"Failed to send email to {to_email}: {e}")
            messagebox.showerror("Email Error", f"Failed to send email: {e}")

    def _show_code_context_menu(self, event):
        """Displays the right-click context menu for copying codes."""
        tree = event.widget
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            try:
                self.code_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.code_context_menu.grab_release()

    def _copy_selected_code(self):
        """Copies the selected license code to the clipboard."""
        # Determine which treeview has focus
        if self.manual_codes_tree.focus():
            selected_tree = self.manual_codes_tree
        elif self.automatic_codes_tree.focus():
            selected_tree = self.automatic_codes_tree
        else:
            messagebox.showwarning("No Selection", "Please select a code to copy.")
            return

        selected_item = selected_tree.focus()
        if selected_item:
            code = selected_tree.item(selected_item, "values")[0]
            self.clipboard_clear()
            self.clipboard_append(code)
            messagebox.showinfo("Copied", f"Code '{code}' copied to clipboard.")

    def on_closing(self):
        """Handles graceful application exit, stopping the Firestore listener and web server."""
        if self._firebase_listener_stopper:
            self._firebase_listener_stopper.unsubscribe()
            print("Firestore listener stopped.")

        if _flask_available and self._web_server_thread and self._web_server_thread.is_alive():
            try:
                # Use a POST request to the shutdown endpoint to stop the Flask server
                requests.post(f"http://localhost:{GeneratorConfig.WEB_SERVER_PORT}/shutdown")
                print("Web server shutdown requested.")
                self._web_server_thread.join(timeout=3)
            except Exception as e:
                print(f"Failed to gracefully shut down web server: {e}")

        executor.shutdown(wait=False)
        self.destroy()


if __name__ == "__main__":
    app = SalesManagerCodeGeneratorApp()
    app.mainloop()
