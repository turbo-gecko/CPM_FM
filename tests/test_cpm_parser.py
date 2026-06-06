from cpm_fm.terminal.cpm_parser import CPMParser


def test_parse_dir_output_extracts_filenames():
    # Standard CP/M 2.2 4-column DIR output (see docs/App_Design.md): each file line
    # starts with a drive identifier (e.g. "C:") and separates entries with " : ".
    mock_output = """
    C: TE       COM : WSCHANGE OVR : MYFILE   TXT
    C: MOREFILES TXT : OTHER    BIN
    C>
    A: NO FILE FOUND
    """

    assert CPMParser.parse_dir_output(mock_output) == {
        "TE.COM": True,
        "WSCHANGE.OVR": True,
        "MYFILE.TXT": True,
        "MOREFILES.TXT": True,
        "OTHER.BIN": True,
    }


def test_parse_dir_output_ignores_prompts_and_empty():
    # Drive prompts ("C>"), "NO FILE" responses, and blank lines yield no entries.
    assert CPMParser.parse_dir_output("\nC>\nA: NO FILE FOUND\n\n") == {}
