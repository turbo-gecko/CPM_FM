# CP/M File Manager - Design Document

## Purpose of the program
The program is to enable the transfer of files between the host system and a remote CP/M system using serial communications using a simple, cross platform GUI in Python.

# Requirements

## Look and Feel
The GUI shall have a menu bar with the following structure:
- File
    - Load
    - Save
    - Exit
- Config
    - Serial
    - General

### Main Program Look and Feel
The main program shall consist of the following:
- Menu bar at the top.
- Status bar at the bottom.
- The 'Host Files' multi-select widget on the left hand side that displays the files in the current working folder of the host system.
- The 'Remote Files' multi-select widget on the right hand side that displays the files in the current working folder of the remote system.
- In between the host and remote widgets shall be the following buttons:
    - Connect
    - Copy to Remote
    - Copy to Host
    - Refresh

## Configuration

### Serial Configuration
When the 'Config>Serial' menu option is chosen, a modal dialog shall be presented to enable the user to modify the following items:
- Comm Port: This shal be a a drop down list.
    - Enumerate through the installed serial ports on the host and populate the list with the serial ports found.
- Speed: This shall be a drop down list of the following speeds. The default shall be 115200.
    - 300
    - 1200
    - 2400
    - 4800
    - 9600
    - 14400
    - 19200
    - 38400
    - 57600
    - 115200
    - 230400
    - 460800
    - 921600
- Data: This shall be a drop down list of the following data bits. The default shall be 8.
    - 7
    - 8
- Parity: This shall be a drop down list of the following parity. The default shall be none.
    - none
    - odd
    - even
    - mark
    - space
- Stop Bits: This shall be a drop down list of the following stop bits. The default shall be 1.
    - 1
    - 2
- Flow Control: This shall be a drop down list of the following flow control options. The default shall be NONE.
    - NONE
    - XON/XOFF
    - RTS/CTS
    - DSR/DTR
- Transmit Delay: This shall be a group of the following items
    - msec/char: This shall be a text field that defaults to 0. It shall be limited to numbers between the values of 0 and 255.
    - msec/line: This shall be a text field that defaults to 0. It shall be limited to numbers between the values of 0 and 255.

### General Configuration
When the 'Config>General' menu option is chosen, a modal dialog shall be presented to enable the user to modify the following configuration items:
- Commands: This shall be a group of the following items:
    - Receive: This shall be a text field limited to 253 characters.
    - Send: This shall be a text field limited to 253 characters.

## Status Bar
The status bar shall be a single line text label with a maximum of 127 characters.

## Buttons
### Connect
This shall be enabled at startup and the function that handles the button click shall an empty stub.

### Copy to Remote
This shall be disabled at startup and the function that handles the button click shall an empty stub.

### Copy to Host
This shall be disabled at startup and the function that handles the button click shall an empty stub.

### Refresh
This shall be disabled at startup and the function that handles the button click shall an empty stub.

## Host Files
This shall be populated with the file contents of the current working directory on the host.

## Host Files
This shall be unpopulated at start up.

## File Transfers
The file transfers shall be in both directions, i.e., host to remote and remote to host.
The file transfer protocol shall be X-Modem.


## Project Structure
CPM_FM/
├── .vscode/
│   └── settings.json                     # Optional: Python interpreter path, linter settings
├── src/
│   ├── cpm_fm/
│   │   ├── __init__.py                   # Makes it a package
│   │   ├── main.py                       # Entry point: runs the GUI app
│   │   ├── gui/
│   │   │   ├── __init__.py
│   │   │   └── app.py                    # Contains App class (as above)
│   │   ├── serial/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py             # Serial port handler (to be implemented)
│   │   │   └── xmodem.py                 # X-Modem protocol implementation (stubbed)
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── settings.py               # Loads/saves config from/to JSON file
│   │   │   └── defaults.py               # Default values for all configuration items
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── file_utils.py             # Helper functions: list files, validate names, etc.
├── tests/                                # Unit tests (pytest)
│   ├── __init__.py
│   ├── test_serial_connection.py
│   ├── test_xmodem.py
│   └── test_config.py
├── requirements.txt                      # Dependencies (e.g., pyserial, tkinter)
└── README.md                             # Project overview and usage instructions

