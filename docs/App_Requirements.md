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

### Main Program GUI
The main program shall consist of the following:
- Menu bar at the top.
- Status bar at the bottom.
- The 'Host Files' group on the left hand side consisting of:
    - Button called 'Change Directory'.
    - Multi-select widget that shall display on startup the files in the current working folder of the host system.
- The 'Remote Files' group on the left hand side consisting of:
    - Button called 'Update'.
    - Multi-select widget that shall be empty on startup.
- In between the 'Host Files' and 'Remote Files' groupss shall be the following buttons:
    - Connect
    - Copy to Remote
    - Copy to Host
    - Refresh
    - Terminal

### Menu Items

#### Load
The File>Load menu item shall prompt the user via a file select dialog box, defaulting to the file type 'json' for a configuration file to load from. The internal program structures and variables for serial configuration settings and general configuration settings shall be updated with those in the configuration file. Any settings not recognised in the settings file shall be ignored.

#### Save
The File>Save menu item shall prompt the user via a file select dialog box, defaulting to the file type 'json' for a configuration file to save to. The internal program structures and variables for serial configuration settings and general configuration settings shall be saved to the configuration file in JSON format.

#### Exit
The File>Exit menu item shall:
- Close any open com ports.
- Close all open dialogs and windows.

#### Serial
When the 'Config>Serial' menu option is chosen, the Serial Configuration Dialog shall be presented to enable the user to modify the serial settings.

#### Serial
When the 'Config>General' menu option is chosen, the General Configuration Dialog shall be presented to enable the user to modify the general settings.

### Status Bar
The status bar shall be a single line text label with a maximum of 127 characters.

### Buttons
#### Change Directory
This shall be enabled at startup and shall prompt the user via a folder select dialog box for the folder to load into the 'Host Files' multi-select widget.

#### Update
This shall be enabled at startup and shall interrogate the remote host for the list of files in the current working drive of the remote computer to load into the 'Remote Files' multi-select widget following the process listed in the 'Populating remote file list' requirement

#### Connect
This shall be enabled at startup and the function that handles the button click shall implement the functionality specified by 'Connecting to the remote system".

#### Disconnect
This shall be enabled at startup and the function that handles the button click shall implement the functionality specified by 'Disconnecting from the remote system".

#### Copy to Remote
This shall be enabled at startup and the function that handles the button click shall an empty stub.

#### Copy to Host
This shall be enabled at startup and the function that handles the button click shall an empty stub.

#### Refresh
This shall be enabled at startup and the function that handles the button click shall implement the functionality specified by 'Populating remote file list'.

### Host Files
This shall be populated with the file contents of the current working directory on the host.

### Remote Files
This shall be unpopulated at start up.

### Dialogs

#### Serial Configuration Dialog
The Serial Configuration Dialog is a modal dialog called 'Serial Config' that enables the user to modify the following items:
- Port Settings: This shall be a group of the following items consisting of 2 columns with setting name left justified in the first column and the setting field right justified in the second column
    - Terminal Port: This shal be a a drop down list.
        - Enumerate through the installed serial ports on the host and populate the list with the serial ports found.
    - Transfer Port: This shal be a a drop down list.
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
        - NONE
        - ODD
        - EVEN
        - MARK
        - SPACE
    - Stop Bits: This shall be a drop down list of the following stop bits. The default shall be 1.
        - 1
        - 2
    - Flow Control: This shall be a drop down list of the following flow control options. The default shall be NONE.
        - NONE
        - XON/XOFF
        - RTS/CTS
        - DSR/DTR

- Transmit Delay: This shall be a group of the following items consisting of 2 columns with setting name left justified in the first column and the setting field right justified in the second column
    - msec/char: This shall be a text field that defaults to 0. It shall be limited to numbers between the values of 0 and 255.
    - msec/line: This shall be a text field that defaults to 0. It shall be limited to numbers between the values of 0 and 255.

#### General Configuration Dialog
The General Configuration Dialog is a modal dialog called 'General Config' that shall enable the user to modify the following items:
- Terminal Commands: This shall be a group of the following items consisting of 2 columns with setting name left justified in the first column and the setting field right justified in the second column
    - List Files: This shall be a text field limited to 79 characters. The default shall be 'DIR'
    - Change Disk: This shall be a text field limited to 79 characters. The default shall be an empty field.

- Xmodem Commands: This shall be a group of the following items consisting of 2 columns with setting name left justified in the first column and the setting field right justified in the second column
    - Receive from Remote: This shall be a text field limited to 79 characters. The default shall be 'PCPUT $1'
    - Send to Remote: This shall be a text field limited to 79 characters. The default shall be 'PCGET $1'

- End of Line: This shall be a group of the following radio buttons where only one of the buttons can be selected at any point in time
    - Carriage Return (CR): This shall be the default radio button.
    - Line Feed (LF): This shall be a radio button.
    - Carriage Return/Line Feed (CR/LF): This shall be a radio button.

#### Terminal Window
The terminal window is a non-modal window called 'Terminal' that shall be used to send and receive data from the remote system. The window consists of the following items:
- Large multi-line text area called 'Receive' for displaying incoming data from the remote system and has the following characteristics:
    - Auto scrolls the incoming text.
    - Read only.
- The following items are positioned below the receive text area:
    - Button called 'Clear' that is left aligned to the terminal window that clears the contents of the receive text are when pressed.
    - Check box to enable/disable the 'Local Echo' that is centered to the terminal window and is disabled by default. 
    - Check box to enable/disable the 'Autoscroll' that is right aligned to the terminal window and is enabled by default.
- Below the clear button and the autoscroll checkbox is a group called 'Transmit' that contains the following items:
    - Single line text field aligned to the left.
    - 'Send' button aligned to the right in the same row as the text area.

## Functional
### Connecting to the remote system
When the 'Connect' button is pressed, the following actions shall occur:
- Open the 'Terminal Port' serial port if not already open.
    - If the serial port cannot be opened, display an error dialog "Terminal port is unable to be opened" and cancel the current workflow.
- Display in the status bar 'Terminal port open'
- Open the 'Terminal Window' if not already open.
- Display received data from the remote 'Terminal Port' in the receive text area of the 'Terminal' window.

### Disconnecting from the remote system
When the 'Disconnect' button is pressed, the following actions shall occur:
- If the 'Terminal Port' is currently open, attempt to close the serial port.
    - If the serial port cannot be closed, display an error dialog "Terminal port is unable to be closed" and cancel the current workflow.
- Display in the status bar 'Terminal port closed'

### Populating remote file list
If the terminal port is not open, the status bar text shall be updated to 'Terminal port not open - cannot read file list' and the remote file list shall be cleared.
If the terminal port is open, the remote file list shall be populated with the files on the remote host.
- The system shall update the status bar with the text 'Remote file list updated'

### File Transfers
File transfers can only occur if both the terminal status flag and the transport status flag are set to connected.
The file transfers shall be in both directions, i.e., host to remote and remote to host.
The file transfer protocol shall be X-Modem.
The serial port to be used for transfers shall be the 'Transfer Port'.

