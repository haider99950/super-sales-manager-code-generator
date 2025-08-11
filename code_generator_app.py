# code_generator_app.py
#
# This is the refactored, desktop-only version of the Sales Manager Code Generator.
# It handles manual code generation and provides a real-time view of all license
# codes (both manual and automatic) stored in Firebase Firestore.
# The Flask web server functionality has been removed, as it now resides in a
# separate code_generator_server.py file.

import tkinter as tk
from tkinter import ttk, messagebox
import random
import string
import os

# Firebase Admin SDK imports
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    from firebase_admin import exceptions as firebase_exceptions
    # This flag tracks if Firebase has been initialized to prevent re-initialization
    _firebase_initialized = False
except ImportError:
    messagebox.showerror("Import Error", "Firebase Admin SDK not found. Please install it: pip install firebase-admin")
    _firebase_initialized = False
    firestore = None


# Configuration
class GeneratorConfig:
    """
    Stores configuration settings and color palettes for the app.
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

    # Path to the Firebase service account key file
    FIREBASE_SERVICE_ACCOUNT_KEY_PATH = "firebase_service_account.json"

    # --- REVERTED: Configuration for the original raw code format ---
    CODE_LENGTH = 50
    CODE_CHARACTERS = string.ascii_letters + string.digits + string.punctuation


class SalesManagerCodeGeneratorApp(tk.Tk):
    """
    Main application class for the Sales Manager Code Generator.
    Manages manual generation and a real-time list of all license codes.
    """

    def __init__(self):
        super().__init__()
        self.title("Sales Manager Code Generator")
        self.geometry("1000x750")
        self.minsize(800, 600)
        self.configure(bg=GeneratorConfig.PRIMARY_BG)

        self.db_firestore = None
        self._firebase_listener_stopper = None

        self._initialize_firebase()

        if not self.db_firestore:
            messagebox.showerror("Firebase Error", "Firebase is not initialized. Cannot run the Code Generator.")
            self.destroy()
            return

        self._setup_styles()
        self._setup_ui()
        self._start_firestore_listener()

        # Create a context menu for copying codes
        self.code_context_menu = tk.Menu(self, tearoff=0)
        self.code_context_menu.add_command(label="Copy Code", command=self._copy_selected_code)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _initialize_firebase(self):
        """Initializes Firebase Admin SDK."""
        global _firebase_initialized
        if not _firebase_initialized and firestore:
            try:
                # Find the service account key file
                script_dir = os.path.dirname(os.path.abspath(__file__))
                service_account_path = os.path.join(script_dir, GeneratorConfig.FIREBASE_SERVICE_ACCOUNT_KEY_PATH)

                if not os.path.exists(service_account_path):
                    messagebox.showerror("Firebase Error",
                                         f"Firebase service account key not found at: {service_account_path}\n"
                                         "Please ensure 'firebase_service_account.json' is in the same directory.")
                    return

                # Initialize the app with the service account credentials
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
        self.manual_codes_tree = self._create_codes_treeview(self.manual_codes_tab, "Manually Generated Codes")

        # Tab 3: Automatic Codes List
        self.automatic_codes_tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.automatic_codes_tab, text="Automatic Codes")
        self.automatic_codes_tree = self._create_codes_treeview(self.automatic_codes_tab, "Automatically Generated Codes")

    def _create_codes_treeview(self, parent_frame, title):
        """Helper method to create a Treeview for displaying codes, reducing code duplication."""
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=0)
        parent_frame.grid_rowconfigure(1, weight=1)

        ttk.Label(parent_frame, text=title,
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

        tree = ttk.Treeview(codes_frame,
                            columns=("Code", "Type", "Used Globally", "Used By Machine ID",
                                     "Generated Date", "Used Date"),
                            show="headings", style="Treeview")
        tree.grid(row=0, column=0, sticky="nsew")

        tree.heading("Code", text="Code", anchor="w")
        tree.heading("Type", text="Type", anchor="center")
        tree.heading("Used Globally", text="Used Globally", anchor="center")
        tree.heading("Used By Machine ID", text="Used By Machine ID", anchor="w")
        tree.heading("Generated Date", text="Generated Date", anchor="center")
        tree.heading("Used Date", text="Used Date", anchor="center")

        tree.column("Code", width=250, stretch=tk.YES)
        tree.column("Type", width=80, stretch=tk.NO, anchor="center")
        tree.column("Used Globally", width=100, stretch=tk.NO, anchor="center")
        tree.column("Used By Machine ID", width=200, stretch=tk.YES)
        tree.column("Generated Date", width=150, stretch=tk.NO, anchor="center")
        tree.column("Used Date", width=150, stretch=tk.NO, anchor="center")

        codes_scrollbar = ttk.Scrollbar(codes_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=codes_scrollbar.set)
        codes_scrollbar.grid(row=0, column=1, sticky="ns")

        tree.bind("<Button-3>", self._show_code_context_menu)
        return tree

    def _setup_generate_code_tab(self, parent_frame):
        """Sets up the UI for the 'Generate Code' tab."""
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(0, weight=0)
        parent_frame.grid_rowconfigure(1, weight=0)
        parent_frame.grid_rowconfigure(2, weight=1)

        ttk.Label(parent_frame, text="Generate New License Code",
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
        # Adjusting the width to accommodate the longer code string
        self.generated_code_display = ttk.Entry(control_frame, style="TEntry", state="readonly",
                                                width=GeneratorConfig.CODE_LENGTH + 10)
        self.generated_code_display.grid(row=2, column=1, columnspan=3, padx=GeneratorConfig.PAD_X_NORMAL,
                                         pady=(GeneratorConfig.PAD_Y_NORMAL, GeneratorConfig.PAD_Y_SMALL), sticky="ew")

        parent_frame.grid_rowconfigure(2, weight=1)

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
            # Check for boolean and convert to "Yes"/"No"
            used_globally = "Yes" if code_data.get('used_globally', False) else "No"
            used_by_machine_id = code_data.get('used_by_machine_id', 'N/A')
            generation_method = code_data.get('generation_method', 'manual')  # Default to manual for legacy codes

            # Format timestamps for display
            generated_date_ts = code_data.get('generated_date')
            generated_date = generated_date_ts.strftime("%Y-%m-%d %H:%M:%S") if generated_date_ts else 'N/A'

            used_date_ts = code_data.get('used_date')
            used_date = used_date_ts.strftime("%Y-%m-%d %H:%M:%S") if used_date_ts else 'N/A'

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

        # --- REVERTED: Call the original raw code generator ---
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
                'generation_method': 'manual',
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

    # --- FIX: New function to mark a code as used ---
    def _mark_code_as_used(self, code, machine_id):
        """
        Marks a specific license code as used in Firestore.
        This function should be called by the client application after
        a successful code validation.
        """
        if not self.db_firestore:
            print("Error: Firebase is not connected, cannot mark code as used.")
            return False

        try:
            doc_ref = self.db_firestore.collection('license_codes').document(code)
            doc_ref.update({
                'used_globally': True,
                'used_by_machine_id': machine_id,
                'used_date': firestore.SERVER_TIMESTAMP
            })
            print(f"Code '{code}' successfully marked as used by machine '{machine_id}'.")
            return True
        except firebase_exceptions.FirebaseError as fe:
            print(f"Firebase Error: Failed to mark code as used: {fe}")
            return False
        except Exception as e:
            print(f"Error: Failed to mark code as used: {e}")
            return False

    # --- EXAMPLE: This is an example of how you would integrate the new function ---
    def _check_code_and_update_status(self, code_to_check, current_machine_id):
        """
        Simulated function that checks a code's validity and marks it as used.
        In your actual app, this would be the function called when a user enters a code.
        """
        if not self.db_firestore:
            return False

        try:
            doc_ref = self.db_firestore.collection('license_codes').document(code_to_check)
            doc = doc_ref.get()

            if not doc.exists:
                messagebox.showerror("Validation Failed", "The license code you entered is not valid.")
                return False

            code_data = doc.to_dict()
            if code_data.get('used_globally', False):
                messagebox.showwarning("Code Already Used", "This license code has already been used.")
                return False

            # If the code is valid and unused, mark it as used.
            # This is where we call the new function to update the status.
            if self._mark_code_as_used(code_to_check, current_machine_id):
                messagebox.showinfo("Success", "Your subscription is now active!")
                return True
            else:
                messagebox.showerror("Update Failed", "Could not activate your subscription. Please try again.")
                return False

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during code validation: {e}")
            return False

    def on_closing(self):
        """Handles graceful application exit by stopping the Firestore listener."""
        if self._firebase_listener_stopper:
            self._firebase_listener_stopper.unsubscribe()
            print("Firestore listener stopped.")

        self.destroy()


if __name__ == "__main__":
    app = SalesManagerCodeGeneratorApp()
    app.mainloop()
