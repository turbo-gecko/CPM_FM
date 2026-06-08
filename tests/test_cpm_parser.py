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


def test_parse_dir_output_includes_extensionless_files():
    # Bug 3: a file with no extension (e.g. LICENCE) is shown by CP/M DIR with a
    # blank, space-padded extension field, so after whitespace normalisation the
    # entry is a single token. It must still be listed (DR-013/DR-021/DR-023).
    mock_output = "C: LICENCE      : PIP      COM\n"
    assert CPMParser.parse_dir_output(mock_output) == {
        "LICENCE": True,
        "PIP.COM": True,
    }


def test_parse_dir_output_single_file_has_no_separator():
    # Regression (DR-005): a directory with a single file produces a line with
    # no " : " separator (that delimiter only appears between multiple entries).
    # Such a line must still be parsed, otherwise the lone file is dropped.
    mock_output = "A: MYFILE   TXT\nA>\n"
    assert CPMParser.parse_dir_output(mock_output) == {"MYFILE.TXT": True}


def test_parse_dir_output_single_extensionless_file():
    # The single-file path must also handle an extensionless name (DR-013/DR-023).
    assert CPMParser.parse_dir_output("A: LICENCE\n") == {"LICENCE": True}


def test_has_drive_prompt_detects_prompt():
    # FR-102/DR-033: after "B:" the terminal answers with a "B>" prompt.
    assert CPMParser.has_drive_prompt("B>", "B") is True


def test_has_drive_prompt_detects_prompt_embedded_in_output():
    # The prompt may be preceded by the echoed command and other output.
    text = "B:\nB: SOMEFILE COM\nB>\n"
    assert CPMParser.has_drive_prompt(text, "B") is True


def test_has_drive_prompt_is_case_insensitive():
    assert CPMParser.has_drive_prompt("a>", "A") is True
    assert CPMParser.has_drive_prompt("A>", "a") is True


def test_has_drive_prompt_ignores_blank_lines():
    # FR-101: blank lines returned by the terminal must be ignored, and a
    # response without the prompt must report absent.
    assert CPMParser.has_drive_prompt("\n   \n\n", "B") is False
    assert CPMParser.has_drive_prompt("\n\nNot ready\n\n", "B") is False


def test_has_drive_prompt_rejects_different_drive():
    # A prompt for a different drive does not satisfy the requested drive.
    assert CPMParser.has_drive_prompt("A>", "B") is False
