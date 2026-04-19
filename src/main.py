import sys
import os

# Add the project root to sys.path to allow 'from src...' imports when running main.py directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import filedialog, messagebox
from src.gui.config_dialogs import SerialConfigDialog, GeneralConfigDialog
from src.gui.terminal_window import TerminalWindow
from src.terminal.serial_manager import SerialManager
from src.terminal.cpm_parser import CPMParser
from src.terminal.xmodem import XModem
from src.utils.config_handler import ConfigHandler
import threading
import time

class MainApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CP/M File Manager")
        self.geometry("800x500")

        # Core Components
        self.serial_mgr = SerialManager()
        self.config_handler = ConfigHandler()
        self.settings = {}
        
        # UI State
        self.terminal_win = None
        self.host_dir = os.getcwd()
        self._remote_capture_buffer = ""
        self._capture_active = False

        self.setup_menu()
        self.setup_layout()
        self.setup_status_bar()
        
        # Load default config
        self.load_config("serial_settings.json")

    def setup_menu(self):
        menubar = tk.Menu(self)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load", command=self.menu_load)
        file_menu.add_command(label="Save", command=self.menu_save)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit_app)
        menubar.add_cascade(label="File", menu=file_menu)

        config_menu = tk.Menu(menubar, tearoff=0)
        config_menu.add_command(label="Serial", command=self.menu_serial_config)
        config_menu.add_command(label="General", command=self.menu_general_config)
        menubar.add_cascade(label="Config", menu=config_menu)

        self.config(menu=menubar)

    def setup_layout(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Side: Host Files
        host_frame = tk.LabelFrame(main_frame, text="Host Files")
        host_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Button(host_frame, text="Change Directory", command=self.change_host_dir).pack(fill=tk.X)
        self.host_list = tk.Listbox(host_frame, selectmode=tk.MULTIPLE)
        self.host_list.pack(fill=tk.BOTH, expand=True)
        self.refresh_host_files()

        # Middle: Action Buttons
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(side=tk.LEFT, padx=10)
        
        self.btn_connect = tk.Button(btn_frame, text="Connect", command=self.do_connect)
        self.btn_connect.pack(fill=tk.X, pady=2)
        
        self.btn_disconnect = tk.Button(btn_frame, text="Disconnect", command=self.do_disconnect)
        self.btn_disconnect.pack(fill=tk.X, pady=2)
        
        tk.Button(btn_frame, text="Copy to Remote", command=self.do_copy_to_remote).pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="Copy to Host", command=self.do_copy_to_host).pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="Refresh", command=self.refresh_remote_files).pack(fill=tk.X, pady=2)
        tk.Button(btn_frame, text="Terminal", command=self.show_terminal).pack(fill=tk.X, pady=2)

        # Right Side: Remote Files
        remote_frame = tk.LabelFrame(main_frame, text="Remote Files")
        remote_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Button(remote_frame, text="Update", command=self.refresh_remote_files).pack(fill=tk.X)
        self.remote_list = tk.Listbox(remote_frame, selectmode=tk.MULTIPLE)
        self.remote_list.pack(fill=tk.BOTH, expand=True)

    def setup_status_bar(self):
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(self, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor='w')
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def set_status(self, text: str):
        self.status_var.set(text[:127])

    def refresh_host_files(self):
        self.host_list.delete(0, tk.END)
        try:
            files = [f for f in os.listdir(self.host_dir) if os.path.isfile(os.path.join(self.host_dir, f))]
            for f in files:
                self.host_list.insert(tk.END, f)
        except Exception as e:
            self.set_status(f"Error reading host files: {e}")

    def change_host_dir(self):
        path = filedialog.askdirectory(initialdir=self.host_dir)
        if path:
            self.host_dir = path
            self.refresh_host_files()

    def show_terminal(self):
        if not self.terminal_win:
            self.terminal_win = TerminalWindow(self, self.handle_terminal_send)
            self.serial_mgr.on_data_received = self.handle_terminal_recv
        else:
            self.terminal_win.deiconify()

    def handle_terminal_send(self, text):
        if self.serial_mgr.terminal_connected:
            # Append EOL based on settings
            eol = self.settings.get('eol', 'CR')
            eol_char = {'CR': '\r', 'LF': '\n', 'CRLF': '\r\n'}.get(eol, '\r')
            
            # Prevent double-terminators if already appended (e.g. in _do_refresh_remote_logic)
            if not text.endswith(eol_char):
                text += eol_char

            self.serial_mgr.send_data('terminal', text)
            if self.terminal_win and self.terminal_win.var_local_echo.get():
                self.terminal_win.write_text(f"\n{text}")
        else:
            self.set_status("Terminal port not open - cannot send")

    def handle_terminal_recv(self, text):
        if self.terminal_win:
            self.terminal_win.write_text(text)
        if self._capture_active:
            self._remote_capture_buffer += text

    def do_connect(self):
        if self.serial_mgr.open_port('terminal', self.settings):
            self.set_status("Terminal port open")
            term_port = self.settings.get('terminal_port')
            trans_port = self.settings.get('transport_port')
            if term_port != trans_port:
                if not self.serial_mgr.open_port('transport', self.settings):
                    messagebox.showerror("Error", "Transport port is unable to be opened")
            else:
                self.serial_mgr.transport_connected = True
        else:
            messagebox.showerror("Error", "Terminal port is unable to be opened")

    def do_disconnect(self):
        self.serial_mgr.close_ports()
        self.set_status("Terminal port closed")

    def refresh_remote_files(self):
        if not self.serial_mgr.terminal_connected:
            self.set_status("Terminal port not open - cannot read file list")
            self.remote_list.delete(0, tk.END)
            return
        threading.Thread(target=self._do_refresh_remote_logic, daemon=True).start()

    def _do_refresh_remote_logic(self):
        self.set_status("Updating remote file list...")
        self._remote_capture_buffer = ""
        self._capture_active = True
        cmd = self.settings.get('list_files_cmd', 'DIR')
        eol = self.settings.get('eol', 'CR')
        eol_char = {'CR': '\r', 'LF': '\n', 'CRLF': '\r\n'}.get(eol, '\r')
        self.handle_terminal_send(cmd + eol_char)
        time.sleep(1.5)
        self._capture_active = False
        files_dict = CPMParser.parse_dir_output(self._remote_capture_buffer)
        self.after(0, self._update_remote_list_ui, files_dict)

    def _update_remote_list_ui(self, files_dict):
        self.remote_list.delete(0, tk.END)
        for filename in sorted(files_dict.keys()):
            self.remote_list.insert(tk.END, filename)
        self.set_status("Remote file list updated")

    def do_copy_to_remote(self):
        if not self.serial_mgr.transport_connected:
            messagebox.showerror("Error", "Transport port not connected")
            return
        
        selection = self.host_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a file to upload")
            return
        
        filename = self.host_list.get(selection[0])
        filepath = os.path.join(self.host_dir, filename)
        
        threading.Thread(target=self._transfer_to_remote, args=(filepath,), daemon=True).start()

    def _transfer_to_remote(self, filepath):
        self.set_status(f"Uploading {os.path.basename(filepath)}...")
        try:
            ser = self.serial_mgr.transport_port
            xm = XModem(ser)
            if xm.send_file(filepath):
                self.after(0, lambda: self.set_status(f"Successfully uploaded {os.path.basename(filepath)}"))
            else:
                self.after(0, lambda: messagebox.showerror("X-Modem Error", "Transfer failed"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def do_copy_to_host(self):
        if not self.serial_mgr.transport_connected:
            messagebox.showerror("Error", "Transport port not connected")
            return
        
        selection = self.remote_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a file to download")
            return
            
        filename = self.remote_list.get(selection[0])
        save_path = os.path.join(self.host_dir, filename)
        
        threading.Thread(target=self._transfer_to_host, args=(save_path,), daemon=True).start()

    def _transfer_to_host(self, save_path):
        self.set_status(f"Downloading {os.path.basename(save_path)}...")
        try:
            ser = self.serial_mgr.transport_port
            xm = XModem(ser)
            if xm.receive_file(save_path):
                self.after(0, lambda: self.set_status(f"Successfully downloaded {os.path.basename(save_path)}"))
            else:
                self.after(0, lambda: messagebox.showerror("X-Modem Error", "Transfer failed"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def load_config(self, filename):
        self.settings = self.config_handler.load_json(filename)
        self.set_status(f"Loaded config: {filename}")

    def menu_load(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if path:
            self.load_config(path)

    def menu_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if path:
            if self.config_handler.save_json(path, self.settings):
                self.set_status(f"Saved config to {path}")

    def menu_serial_config(self):
        ports = ["COM1", "COM2", "COM3", "COM4", "COM5", "COM99"]
        def update_settings(new_set):
            self.settings.update(new_set)
            self.set_status("Serial settings updated")
        SerialConfigDialog(self, self.settings, ports, update_settings)

    def menu_general_config(self):
        def update_settings(new_set):
            self.settings.update(new_set)
            self.set_status("General settings updated")
        GeneralConfigDialog(self, self.settings, update_settings)

    def quit_app(self):
        self.serial_mgr.close_ports()
        self.destroy()

if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()
