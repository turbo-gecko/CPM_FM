import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Any

class ConfigDialog(tk.Toplevel):
    """
    Base class for Configuration Dialogs.
    """
    def __init__(self, parent, title: str, settings: Dict[str, Any], fields: list, callback):
        super().__init__(parent)
        self.title(title)
        self.settings = settings
        self.fields = fields
        self.callback = callback
        self.result = None

        self.grid_columnconfigure(1, weight=1)
        self.create_widgets()
        
        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)

    def create_widgets(self):
        self.entries = {}
        for i, field in enumerate(self.fields):
            lbl = tk.Label(self, text=field['label'], anchor='w')
            lbl.grid(row=i, column=0, padx=10, pady=5, sticky='w')
            
            if field['type'] == 'dropdown':
                var = tk.StringVar(value=self.settings.get(field['key'], field['default']))
                widget = tk.OptionMenu(self, var, *field['options'])
                self.entries[field['key']] = var
            else:
                var = tk.StringVar(value=self.settings.get(field['key'], field['default']))
                widget = tk.Entry(self, textvariable=var)
                self.entries[field['key']] = var
            
            widget.grid(row=i, column=1, padx=10, pady=5, sticky='e')

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=len(self.fields), column=0, columnspan=2, pady=15)
        
        tk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def save(self):
        new_settings = {key: var.get() for key, var in self.entries.items()}
        self.callback(new_settings)
        self.destroy()

class SerialConfigDialog(ConfigDialog):
    """
    Specialized dialog for Serial Configuration as per App_Requirements.md.
    """
    def __init__(self, parent, settings, current_ports, callback):
        # Define fields based on Requirements
        fields = [
            {'key': 'terminal_port', 'label': 'Terminal Port', 'type': 'dropdown', 'options': current_ports, 'default': 'COM1'},
            {'key': 'transport_port', 'label': 'Transfer Port', 'type': 'dropdown', 'options': current_ports, 'default': 'COM1'},
            {'key': 'speed', 'label': 'Speed', 'type': 'dropdown', 'options': ['300', '1200', '2400', '4800', '9600', '14400', '19200', '38400', '57600', '115200', '230400', '460800', '921600'], 'default': '115200'},
            {'key': 'data', 'label': 'Data Bits', 'type': 'dropdown', 'options': ['7', '8'], 'default': '8'},
            {'key': 'parity', 'label': 'Parity', 'type': 'dropdown', 'options': ['NONE', 'ODD', 'EVEN', 'MARK', 'SPACE'], 'default': 'NONE'},
            {'key': 'stopbits', 'label': 'Stop Bits', 'type': 'dropdown', 'options': ['1', '2'], 'default': '1'},
            {'key': 'flow', 'label': 'Flow Control', 'type': 'dropdown', 'options': ['NONE', 'XON/XOFF', 'RTS/CTS', 'DSR/DTR'], 'default': 'NONE'},
            {'key': 'msec_char', 'label': 'msec/char', 'type': 'text', 'default': '0'},
            {'key': 'msec_line', 'label': 'msec/line', 'type': 'text', 'default': '0'},
        ]
        super().__init__(parent, "Serial Config", settings, fields, callback)

class GeneralConfigDialog(ConfigDialog):
    """
    Specialized dialog for General Configuration as per App_Requirements.md.
    """
    def __init__(self, parent, settings, callback):
        fields = [
            {'key': 'list_files_cmd', 'label': 'List Files', 'type': 'text', 'default': 'DIR'},
            {'key': 'change_disk_cmd', 'label': 'Change Disk', 'type': 'text', 'default': ''},
            {'key': 'recv_remote_cmd', 'label': 'Receive from Remote', 'type': 'text', 'default': 'PCPUT $1'},
            {'key': 'send_remote_cmd', 'label': 'Send to Remote', 'type': 'text', 'default': 'PCGET $1'},
            {'key': 'eol', 'label': 'End of Line', 'type': 'dropdown', 'options': ['CR', 'LF', 'CRLF'], 'default': 'CR'},
        ]
        super().__init__(parent, "General Config", settings, fields, callback)
