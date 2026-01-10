# app.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from pathlib import Path
import json

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CP/M File Manager")
        self.root.geometry("1000x600")

        # Initialize serial configuration defaults
        self.serial_config = {
            'terminal_port': 'COM99',      # Default terminal port
            'transport_port': 'COM1',     # Default transport port (assumed)
            'speed': 19200,               # Optional: if you plan to add speed later
            'data': 8,                    # Optional: 7, 8
            'parity': 'NONE',             # Optional: NONE, EVEN, ODD
            'stopbits': 1,                # Optional: 1 or 2
            'flow': 'NONE',               # Optional: NONE, XON/XOFF, RTS/CTS, DSR/DTR
            'msec_char': 0,               # Optional: character delay in milli-seconds
            'msec_line': 0,               # Optional: line delay in milli-seconds
        }

        # Load config from file if it exists
        self._load_serial_config()

        # Initialize variables
        self.serial_connection = None
        self.remote_files = []  # Will be populated after connection

        # Setup GUI components
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_main_layout()

    def _setup_menu_bar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load", command=self._on_load)
        file_menu.add_command(label="Save", command=self._on_save)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Config menu
        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(
            label="Serial", command=self._open_serial_config)
        config_menu.add_command(
            label="General", command=self._open_general_config)
        menubar.add_cascade(label="Config", menu=config_menu)

    def _setup_status_bar(self):
        """Setup the status bar at the bottom of the window."""
        self.status_bar = ttk.Label(
            self.root,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Arial", 10)
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def set_status(self, message):
        """Public method to update the status bar text from other modules."""
        self.status_bar.config(text=message)

    def _setup_main_layout(self):
        # Placeholder: file lists and buttons not shown in citations
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Host Files Listbox (left)
        host_label = ttk.Label(main_frame, text="Host Files")
        host_label.grid(row=0, column=0, sticky="w")

        self.host_cd_btn = ttk.Button(main_frame, text="Change Directory",
                                             command=self._on_host_cd, state='enabled')
        self.host_cd_btn.grid(row=1, column=0, pady=(0,0), sticky="w")
        
        self.host_listbox = tk.Listbox(
            main_frame, selectmode=tk.EXTENDED, height=25, width=40)
        self.host_listbox.grid(row=2, column=0, padx=(0, 10), sticky="nsew")
        dir = os.getcwd()
        self._refresh_host_files(dir)

        # Button Column (center)
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=1, padx=10, pady=(0,0), sticky="ns")

        self.connect_btn = ttk.Button(
            button_frame, text="Connect", command=self._on_connect)
        self.connect_btn.pack(pady=(0, 10), fill=tk.X)

        self.copy_to_remote_btn = ttk.Button(button_frame, text="Copy to Remote ->",
                                             command=self._on_copy_to_remote, state='disabled')
        self.copy_to_remote_btn.pack(pady=10, fill=tk.X)

        self.copy_to_host_btn = ttk.Button(button_frame, text="<- Copy to Host",
                                           command=self._on_copy_to_host, state='disabled')
        self.copy_to_host_btn.pack(pady=10, fill=tk.X)

        self.refresh_btn = ttk.Button(button_frame, text="Refresh",
                                      command=self._on_refresh, state='disabled')
        self.refresh_btn.pack(pady=10, fill=tk.X)

        self.terminal_btn = ttk.Button(
            button_frame, text="Terminal", command=self._on_terminal)
        self.terminal_btn.pack(pady=(0, 10), fill=tk.X)

        # Remote Files Listbox (right)
        remote_label = ttk.Label(main_frame, text="Remote Files")
        remote_label.grid(row=0, column=2, sticky="w", padx=(10,0))

        self.remote_cd_btn = ttk.Button(main_frame, text="Change Drive",
                                             command=self._on_remote_cd, state='enabled')
        self.remote_cd_btn.grid(row=1, column=2, padx=(10, 0), pady=(0, 0), sticky="w")

        self.remote_listbox = tk.Listbox(
            main_frame, selectmode=tk.EXTENDED, height=25, width=40)
        self.remote_listbox.grid(row=2, column=2, padx=(10, 0), sticky="nsew")

        # Configure grid weights
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0)
        main_frame.columnconfigure(2, weight=1)
        main_frame.rowconfigure(0, weight=0)
        main_frame.rowconfigure(1, weight=0)
        main_frame.rowconfigure(2, weight=1)

    def _refresh_host_files(self, selected_dir):
        """Populate host files listbox with directory contents."""
        #messagebox.showinfo("Directory selected",
        #                    selected_dir)
        self.host_listbox.delete(0, tk.END)
        dir = os.listdir(selected_dir)
        for item in dir:
            file_path = Path(selected_dir) / item
            if file_path.is_file():
                self.host_listbox.insert(tk.END, item)

    def _on_connect(self):
        # Stub: to be implemented with serial connection logic
        messagebox.showinfo("Connect", "Connect button clicked (stub).")
        # Enable other buttons after successful connection
        self.copy_to_remote_btn.config(state='normal')
        self.copy_to_host_btn.config(state='normal')
        self.refresh_btn.config(state='normal')

    def _on_host_cd(self):
        # Stub: to be implemented with X-Modem logic
        # Open the directory selection dialog
        selected_dir = filedialog.askdirectory(title="Select Directory")
        if selected_dir:  # If user didn't cancel the dialog
            self._refresh_host_files(selected_dir)
        
    def _on_remote_cd(self):
        # Stub: to be implemented with X-Modem logic
        messagebox.showinfo("Change Drive",
                            "Change Remote Drive clicked (stub).")

    def _on_copy_to_remote(self):
        # Stub: to be implemented with X-Modem logic
        messagebox.showinfo("Copy to Remote", "Copy to Remote clicked (stub).")

    def _on_copy_to_host(self):
        # Stub: to be implemented with X-Modem logic
        messagebox.showinfo("Copy to Host", "Copy to Host clicked (stub).")

    def _on_refresh(self):
        dir = os.listdir(os.getcwd())
        self._refresh_host_files(dir)
        messagebox.showinfo("Refresh", "Refresh button clicked (stub).")

    def _on_terminal(self):
        """Open Terminal Dialog."""
        from gui.terminal_dialog import TerminalDialog  # Import locally to avoid circular imports
        self.terminal_dialog = TerminalDialog(self.root, self)
        self.root.wait_window(self.terminal_dialog.top)

    def _open_serial_config(self):
        """Open Serial Configuration Dialog."""
        from gui.serial_config_dialog import SerialConfigDialog  # Import locally to avoid circular imports
        dialog = SerialConfigDialog(self.root, self)
        self.root.wait_window(dialog.top)

    def _open_general_config(self):
        """Open General Configuration Dialog."""
        from gui.general_config_dialog import GeneralConfigDialog  # Import locally
        dialog = GeneralConfigDialog(self.root, self)
        self.root.wait_window(dialog.top)

    def _on_load(self):
        file_path = filedialog.askopenfilename(
            title="Load Serial Settings",
            filetypes=[("JSON files", "*.json")]
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Validate and update only known keys
                    for key in self.serial_config.keys():
                        if key in loaded_config:
                            self.serial_config[key] = loaded_config[key]
                    self.set_status(f"Serial settings loaded from: {file_path}")
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load settings:\n{e}")

    def _load_serial_config(self):
        """Load serial configuration from file if it exists."""
        try:
            config_file = Path.home() / ".cpm_manager" / "serial_config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    # Update only known keys to avoid errors
                    for key in self.serial_config.keys():
                        if key in loaded:
                            self.serial_config[key] = loaded[key]
                self.set_status("Serial configuration loaded from file")
        except Exception as e:
            self.set_status(f"Failed to load config: {e}")
    
    def _on_save(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            title="Save Serial Settings",
            filetypes=[("JSON files", "*.json")],
            initialfile="serial_settings.json"  # Default filename
        )
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.serial_config, f, indent=4)
                self.set_status(f"Serial settings saved to: {file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save settings:\n{e}")

    def _on_exit(self):
        self.terminal_dialog.top.destroy()
        self.root.quit()

    def run(self):
        self.root.mainloop()
