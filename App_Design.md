# Software Architecture
## Project Structure
There shall be a 'src' folder as the root of all source files at the project root.
The shall be a 'main.py' source file in the 'src' folder.
All GUI related source files shall be in a 'gui' folder within the 'src' folder.
All serial and terminal related source files shall be in a 'terminal' folder within the 'src' folder.
All other source files shall be in a 'utils' folder within the 'src' folder.
There shall be a 'resources' folder at the project root. This is for icons, images and other none Python files.

## Class Files
Each class shall have it's own source file.
The name of the source file shall be the same name as the class.

## Code Quality
All Python source files shall adhere to the PEP8 standard.

# Software Design
## Program state
The following program states shall be maintained:
- Terminal status flag. Default at startup is not set. This flag is used to determine if the 'Terminal Port' is open and available for communication.
- Transport status flag. Default at startup is not set. This flag is used to determine if the 'Transport Port' is open and available for communication.

## Functional
### Connecting to the remote system
When the 'Connect' button is pressed, the following actions shall occur:
- If the serial port is successfully opened, set the terminal status flag to true.
- If the serial port cannot be opened, set the terminal status flag to false.
- If the 'Transport Port' is the same as the 'Terminal Port', set the global transport status flag to connected.
- If the 'Transport Port' is different from the 'Terminal Port' and the 'Transport Port' is not currently open, attempt to open the 'Transport Port' serial port.
    - If the serial port cannot be opened, display an error dialog "Transport port is unable to be opened".
    - If the serial port can be opened, set the transport status flag to connected.

### Disconnecting from the remote system
When the 'Disconnect' button is pressed, the following actions shall occur:
- Set the global terminal status flag to false.
    - If the 'Transport Port' is the same as the 'Terminal Port', set the transport status flag to false.
    - If the 'Transport Port' is different from the 'Terminal Port' and the 'Transport Port' is currently open, attempt to close the 'Transport Port' serial port.
        - If the serial port cannot be closed, display an error dialog "Transport port is unable to be closed".
        - If the serial port can be closed, set the transport status flag to false.

### Populating remote file list
Check the terminal status flag and if true, perform the following actions:
- Send the 'List Files' command and 'End of Line' character(s) to the terminal port and the receive text area.
- Wait for at least one second, wait again for the receive buffer to timeout then take the received text and process it into a dictionary using the algorithm for extracting remote file names in the standard CP/M 4 column format.
- Populate the remote file list with the entries in the dictionary.

### File Transfers
File transfers can only occur if both the terminal status flag and the transport status flag are set to connected.
The file transfers shall be in both directions, i.e., host to remote and remote to host.
The file transfer protocol shall be X-Modem.
The serial port to be used for transfers shall be the 'Transfer Port'.

### Receiving data from the terminal port
- Received data is to be stored in a received data buffer until explicitly cleared.
- All received data from the remote 'Terminal Port' is to be displayed in the receive text area of the 'Terminal' window.

### Sending data to the terminal port
- Transmit data is to be stored in a transmit data buffer until explicitly cleared.
- If the 'Local Echo' checkbox in the terminal window is enabled, transmit data shall be copied to the receive text area of the 'Terminal' window.
- The transmitted data shall have appended the 'End of Line' character(s) specified in the general configuration.

### Algorithm for extracting remote file names in the standard CP/M 4 column format
#### Ignore non-file lines
The system shall ignore all lines that:
- Are empty or contain only whitespace.
- Begin with C> (shell prompts) where the C can be any drive letter.
- Contain the substring "NO FILE".
#### Identify file listing lines
The system shall identify and process only lines that:
- Start with the literal prefix C: (where C can be any drive letter) followed by a colon.
- Contain at least one occurrence of the separator sequence : (space-colon-space).
#### Strip drive identifier
For each identified file listing line, the system shall remove the leading C: prefix and process only the remainder of the line.
#### Split file entries
The system shall split each processed line into individual file entries using the delimiter : (space-colon-space), producing a list of filename-extension pairs.
#### Normalise whitespace
For each file entry, the system shall normalize internal whitespace by:
- Replacing any sequence of one or more consecutive spaces with a single space.
- Trimming leading and trailing whitespace.
#### Parse filename and extension
For each normalized file entry, the system shall:
- Split the string into tokens by whitespace.
- Treat the last token as the file extension (e.g., COM, TXT, OVR, XCL).
- Treat all preceding tokens (if any) as the filename base, concatenated without spaces.
    Example: "TE       COM" → ["TE", "COM"] → "TE.COM"
    Example: "WSCHANGE OVR" → ["WSCHANGE", "OVR"] → "WSCHANGE.OVR"
#### Construct full filename
The system shall construct a canonical filename string in the format:
    <filename_base>.<extension>
where:
    <filename_base> is the concatenation of all tokens except the last.
    <extension> is the final token.
#### Store filenames in dictionary
The system shall store each constructed filename as a key in a dictionary, with the value set to True. Duplicate filenames (if any) shall be overwritten (i.e., no duplicate keys allowed).
#### Output format
The system shall return a Python dict where:
- All keys are strings of the form "NAME.EXT".
- All values are the boolean literal True.
- The dictionary contains only valid filenames extracted from input lines.
#### Case sensitivity
The system shall preserve the exact case of filename and extension characters as provided in the input (e.g., "WSCHANGE.OVR" not converted to lowercase).
#### Handle edge cases gracefully
The system shall:
- Skip malformed entries with fewer than two tokens.
- Not raise exceptions for invalid or unexpected input.
- Return an empty dictionary if no valid file entries are found.
#### Input robustness
The system shall tolerate irregular spacing, extra colons within filenames (e.g., A:B.COM — though rare in CP/M), and mixed line endings (\n, \r\n).
#### Constraints
The method assumes input conforms to standard CP/M 2.2 DIR output format (8.3 filenames, space-padded).
Does not support long filenames or non-ASCII characters.
Does not parse file sizes, dates, or attributes — only names and extensions.
