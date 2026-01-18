# app.py
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from pathlib import Path
import json
import threading
import serial

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

        # Initialize general configuration defaults
        self.general_settings = {
            'list_files': 'DIR',
            'change_disk': '',
            'receive_from_remote': 'PCPUT $1',
            'send_to_remote': 'PCGET $1',
            'end_of_line': 'CR'
        }

        # Program state flags
        self.terminal_connected = False
        self.transport_connected = False

        # Load config from file if it exists
        self._load_serial_config()
        self._load_general_config()

        # Initialize variables
        self.serial_connection = None
        self.remote_files = []  # Will be populated after connection
        self.received_data_buffer = ""  # Buffer for collecting serial data

        # Setup GUI components
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_main_layout()

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
    
    def _load_general_config(self):
        """Load general configuration from file if it exists."""
        try:
            config_file = Path.home() / ".cpm_manager" / "general_config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    loaded = json.load(f)
                    # Update only known keys to avoid errors
                    for key in self.general_settings.keys():
                        if key in loaded:
                            self.general_settings[key] = loaded[key]
                self.set_status("General configuration loaded from file")
        except Exception as e:
            self.set_status(f"Failed to load general config: {e}")

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
        # Handle connection according to specification
        try:
            # Open terminal port first
            match self.serial_config['flow']:
                case "DSR/DTR":
                    flow_dsrdtr = True
                    flow_rtscts = False
                    flow_xonxoff = False
                case "NONE":
                    flow_dsrdtr = False
                    flow_rtscts = False
                    flow_xonxoff = False
                case "RTS/CTS":
                    flow_dsrdtr = False
                    flow_rtscts = True
                    flow_xonxoff = False
                case "XON/XOFF":
                    flow_dsrdtr = False
                    flow_rtscts = False
                    flow_xonxoff = True

            self.serial_port = serial.Serial(
                port=self.serial_config['terminal_port'],
                baudrate=int(self.serial_config['speed']),
                bytesize=int(self.serial_config['data']),
                parity=self.serial_config['parity'][0],
                stopbits=float(self.serial_config['stopbits']),
                timeout=0,
                xonxoff=flow_xonxoff,
                rtscts=flow_rtscts,
                dsrdtr=flow_dsrdtr,
            )

            # Set terminal connected flag
            self.terminal_connected = True

            # Start background thread to read incoming data
            self.read_thread = threading.Thread(target=self._read_serial, daemon=True)
            self.read_thread.start()

            # Initialize terminal dialog if not already created
            if not hasattr(self, 'terminal_dialog') or not self.terminal_dialog.top.winfo_exists():
                from gui.terminal_dialog import TerminalDialog  # Import locally to avoid circular imports
                self.terminal_dialog = TerminalDialog(self.root, self)  # Pass 'self' (main app) to terminal for serial access

            # Bring the dialog to front if it exists
            self.terminal_dialog.top.lift()
            self.terminal_dialog.top.focus_force()

            # Enable other buttons after successful connection
            self.copy_to_remote_btn.config(state='normal')
            self.copy_to_host_btn.config(state='normal')
            self.refresh_btn.config(state='normal')

            self.set_status("Terminal port open")

            # Check if transport port is different from terminal port
            if self.serial_config['transport_port'] != self.serial_config['terminal_port']:
                # Try to open transport port
                try:
                    self.transport_port = serial.Serial(
                        port=self.serial_config['transport_port'],
                        baudrate=int(self.serial_config['speed']),
                        bytesize=int(self.serial_config['data']),
                        parity=self.serial_config['parity'][0],
                        stopbits=float(self.serial_config['stopbits']),
                        timeout=1,
                        xonxoff=flow_xonxoff,
                        rtscts=flow_rtscts,
                        dsrdtr=flow_dsrdtr,
                    )
                    self.transport_connected = True
                except Exception as e:
                    messagebox.showerror("Transport Port Error", f"Transport port is unable to be opened:\n{e}")
            else:
                # Same port for both, so transport is connected too
                self.transport_connected = True

        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))

    def _on_disconnect(self):
        """Handle disconnection according to specification."""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                self.terminal_connected = False
            else:
                self.set_status("Terminal port already closed")

            # Check if transport port is different from terminal port and needs closing
            if (self.serial_config['transport_port'] != self.serial_config['terminal_port'] and 
                hasattr(self, 'transport_port') and self.transport_port.is_open):
                self.transport_port.close()
                self.transport_connected = False

            self.set_status("Terminal port closed")

        except Exception as e:
            messagebox.showerror("Disconnection Error", f"Transport port is unable to be closed:\n{e}")

    def _read_serial(self):
        buffer = b""
        while True:
            try:
                # Read available bytes
                new_data = self.serial_port.read(self.serial_port.in_waiting)
                if not new_data:
                    time.sleep(0.01)  # Small delay to prevent busy-waiting

                    decoded = buffer.decode('ascii', 'backslashreplace')
                    buffer = b""
                    if decoded:
                        if hasattr(self, 'terminal_dialog') and self.terminal_dialog.top.winfo_exists():
                            self.terminal_dialog.receive_message(decoded)
                        # Store received data for processing later
                        self.received_data_buffer += decoded
                    continue

                buffer += new_data

                # Split on either \n or \r
                lines = []
                while b'\n' in buffer or b'\r' in buffer:
                    # Find the first occurrence of line ending
                    if b'\n' in buffer:
                        split_pos = buffer.find(b'\n')
                        line = buffer[:split_pos]
                        buffer = buffer[split_pos + 1:]
                    elif b'\r' in buffer:
                        split_pos = buffer.find(b'\r')
                        line = buffer[:split_pos]
                        buffer = buffer[split_pos + 1:]

                        # If next char is \n, consume it too (CRLF case)
                        if buffer.startswith(b'\n'):
                            buffer = buffer[1:]
                    else:
                        break

                    decoded = line.decode('ascii', 'backslashreplace')
                    if decoded:
                        if hasattr(self, 'terminal_dialog') and self.terminal_dialog.top.winfo_exists():
                            self.terminal_dialog.receive_message(decoded)
                        # Store received data for processing later
                        self.received_data_buffer += decoded

                # Optional: handle trailing \r that might be the last character
                if buffer.endswith(b'\r'):
                    line = buffer[:-1]
                    buffer = b""
                    decoded = line.decode('ascii', 'backslashreplace')
                    if decoded:
                        if hasattr(self, 'terminal_dialog') and self.terminal_dialog.top.winfo_exists():
                            self.terminal_dialog.receive_message(decoded)
                        # Store received data for processing later
                        self.received_data_buffer += decoded

            except Exception as e:
                print(f"Serial read error: {e}")
                break

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

    def _extract_remote_filenames(self, data):
        """
        Extract remote filenames from CP/M directory listing using the algorithm
        specified in CPM_FM.md.
        
        Args:
            data (str): Raw text output from CP/M directory command
            
        Returns:
            dict: Dictionary with filenames as keys and True as values
        """
        if not data:
            return {}
            
        # Split into lines
        lines = data.strip().split('\n')
        
        # Process each line according to the algorithm
        filenames = {}
        
        for line in lines:
            # Ignore non-file lines
            if not line.strip() or line.startswith('C>') or 'NO FILE' in line:
                continue
                
            # Identify file listing lines (start with drive letter followed by colon)
            if not line.startswith(('A:', 'B:', 'C:', 'D:', 'E:', 'F:', 'G:', 'H:', 
                                  'I:', 'J:', 'K:', 'L:', 'M:', 'N:', 'O:', 'P:', 
                                  'Q:', 'R:', 'S:', 'T:', 'U:', 'V:', 'W:', 'X:', 
                                  'Y:', 'Z:')):
                continue
                
            # Strip drive identifier
            if ':' in line:
                colon_pos = line.find(':')
                line = line[colon_pos + 1:].strip()
            
            # Split into file entries using " : " as delimiter
            if ' : ' not in line:
                continue
                
            entries = line.split(' : ')
            
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                    
                # Normalize whitespace and parse filename and extension
                tokens = entry.split()
                
                # Skip malformed entries with fewer than two tokens
                if len(tokens) < 2:
                    continue
                
                # Treat the last token as extension, others as filename base
                extension = tokens[-1]
                filename_base = ' '.join(tokens[:-1])
                
                # Construct full filename
                if filename_base and extension:
                    filename = f"{filename_base}.{extension}"
                    filenames[filename] = True
                elif extension:
                    # Handle case where there's only an extension (no base name)
                    filenames[extension] = True
                    
        return filenames

    def _on_refresh(self):
        # Check if terminal is connected before attempting refresh
        if not self.terminal_connected:
            self.set_status("Terminal port not open - cannot read file list")
            self.remote_listbox.delete(0, tk.END)
            return

        try:
            # Clear the received data buffer to start fresh
            self.received_data_buffer = ""
            
            # Send command to remote system
            cmd = self.general_settings['list_files'] + "\r"
            self.serial_port.write(cmd.encode())
            
            # Wait for response with a more robust approach
            time.sleep(0.5)  # Give time for response
            
            # Try to read any available data that might have arrived
            remaining_data = self.serial_port.read(self.serial_port.in_waiting)
            if remaining_data:
                decoded = remaining_data.decode('ascii', 'backslashreplace')
                self.received_data_buffer += decoded
            
            # Process the received data
            if self.received_data_buffer:
                filenames = self._extract_remote_filenames(self.received_data_buffer)
                
                # Update the remote files listbox
                self.remote_listbox.delete(0, tk.END)
                for filename in sorted(filenames.keys()):
                    self.remote_listbox.insert(tk.END, filename)
                
                self.set_status("Remote file list updated")
            else:
                # No data received, clear the listbox
                self.remote_listbox.delete(0, tk.END)
                self.set_status("No remote files found or connection error")
            
        except Exception as e:
            messagebox.showerror("Refresh Error", f"Failed to refresh remote files:\n{e}")

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
                    # Also load general settings if present
                    if 'general_settings' in loaded_config:
                        for key in self.general_settings.keys():
                            if key in loaded_config['general_settings']:
                                self.general_settings[key] = loaded_config['general_settings'][key]
                    self.set_status(f"Settings loaded from: {file_path}")
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load settings:\n{e}")

    def _on_save(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            title="Save Settings",
            filetypes=[("JSON files", "*.json")],
            initialfile="cpm_settings.json"  # Default filename
        )
        if file_path:
            try:
                # Create complete config dict including both serial and general settings
                full_config = {
                    **self.serial_config,
                    'general_settings': self.general_settings
                }
                
                with open(file_path, 'w') as f:
                    json.dump(full_config, f, indent=4)
                self.set_status(f"Settings saved to: {file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save settings:\n{e}")

    def _on_exit(self):
        # Save configurations before exiting
        try:
            # Ensure the config directory exists
            config_dir = Path.home() / ".cpm_manager"
            config_dir.mkdir(exist_ok=True)
            
            # Save serial config
            serial_config_file = config_dir / "serial_config.json"
            with open(serial_config_file, 'w') as f:
                json.dump(self.serial_config, f, indent=4)
                
            # Save general config
            general_config_file = config_dir / "general_config.json"
            with open(general_config_file, 'w') as f:
                json.dump(self.general_settings, f, indent=4)
                
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save configuration on exit:\n{e}")
        
        # Close any open ports
        if hasattr(self, 'serial_port') and self.serial_port.is_open:
            self.serial_port.close()
        if (hasattr(self, 'transport_port') and 
            hasattr(self.transport_port, 'is_open') and 
            self.transport_port.is_open):
            self.transport_port.close()
            
        # Close terminal dialog
        if hasattr(self, 'terminal_dialog'):
            try:
                self.terminal_dialog.top.destroy()
            except:
                pass
        
        self.root.quit()

    def run(self):
        self.root.mainloop()
