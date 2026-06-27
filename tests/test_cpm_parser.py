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
    """Verifies: DR-013, DR-021, DR-023."""
    # Bug 3: a file with no extension (e.g. LICENCE) is shown by CP/M DIR with a
    # blank, space-padded extension field, so after whitespace normalisation the
    # entry is a single token. It must still be listed (DR-013/DR-021/DR-023).
    mock_output = "C: LICENCE      : PIP      COM\n"
    assert CPMParser.parse_dir_output(mock_output) == {
        "LICENCE": True,
        "PIP.COM": True,
    }


def test_parse_dir_output_single_file_has_no_separator():
    """Verifies: DR-005."""
    # Regression (DR-005): a directory with a single file produces a line with
    # no " : " separator (that delimiter only appears between multiple entries).
    # Such a line must still be parsed, otherwise the lone file is dropped.
    mock_output = "A: MYFILE   TXT\nA>\n"
    assert CPMParser.parse_dir_output(mock_output) == {"MYFILE.TXT": True}


def test_parse_dir_output_single_extensionless_file():
    """Verifies: DR-013, DR-023."""
    # The single-file path must also handle an extensionless name (DR-013/DR-023).
    assert CPMParser.parse_dir_output("A: LICENCE\n") == {"LICENCE": True}


def test_parse_dir_output_vertical_bar_format():
    """Verifies: DR-006, DR-015."""
    # DR-006/DR-015: ZCPR/ZSDOS-style DIR uses '|' as a leading line marker and
    # entry separator (no drive prefix), with a literal dot before the extension.
    mock_output = """
    C>DIR

      |  ASM     .COM  |  CLRDIR  .COM  |  COMPARE .COM  |  COPY    .CFG
      |  FILEATTR.COM  |  CPM     .SYS  |  ZSYS    .SYS
    """
    assert CPMParser.parse_dir_output(mock_output) == {
        "ASM.COM": True,
        "CLRDIR.COM": True,
        "COMPARE.COM": True,
        "COPY.CFG": True,
        "FILEATTR.COM": True,
        "CPM.SYS": True,
        "ZSYS.SYS": True,
    }


def test_parse_dir_output_vertical_bar_extensionless():
    """Verifies: DR-015, DR-014."""
    # DR-015: an empty extension field leaves a trailing dot, which is stripped
    # so the name matches the extensionless convention (DR-014).
    assert CPMParser.parse_dir_output("|  LICENCE  .    |  PIP     .COM\n") == {
        "LICENCE": True,
        "PIP.COM": True,
    }


def test_has_drive_prompt_detects_prompt():
    """Verifies: FR-102, DR-033."""
    # FR-102/DR-033: after "B:" the terminal answers with a "B>" prompt.
    assert CPMParser.has_drive_prompt("B>", "B") is True


def test_has_drive_prompt_detects_prompt_embedded_in_output():
    # The prompt may be preceded by the echoed command and other output.
    text = "B:\nB: SOMEFILE COM\nB>\n"
    assert CPMParser.has_drive_prompt(text, "B") is True


def test_has_drive_prompt_matches_lowercase_response():
    """Verifies: DR-033."""
    # DR-033: a lowercase prompt from the terminal satisfies an upper-case drive.
    assert CPMParser.has_drive_prompt("a>", "A") is True


def test_has_drive_prompt_matches_lowercase_request():
    """Verifies: DR-033."""
    # DR-033: a lowercase requested drive letter is matched case-insensitively.
    assert CPMParser.has_drive_prompt("A>", "a") is True


def test_has_drive_prompt_ignores_blank_lines():
    """Verifies: FR-101."""
    # FR-101: blank lines returned by the terminal must be ignored, and a
    # response without the prompt must report absent.
    assert CPMParser.has_drive_prompt("\n   \n\n", "B") is False
    assert CPMParser.has_drive_prompt("\n\nNot ready\n\n", "B") is False


def test_has_drive_prompt_rejects_different_drive():
    # A prompt for a different drive does not satisfy the requested drive.
    assert CPMParser.has_drive_prompt("A>", "B") is False


def test_has_drive_prompt_accepts_zcpr_user_area():
    """Verifies: DR-033."""
    # DR-033: ZCPR-family CCPs embed the user area in the prompt, so the drive
    # letter may be preceded and/or followed by digits (e.g. "A0>", "4A>").
    assert CPMParser.has_drive_prompt("A0>", "A") is True
    assert CPMParser.has_drive_prompt("4A>", "A") is True
    assert CPMParser.has_drive_prompt("B12>", "B") is True
    assert CPMParser.has_drive_prompt("4a>", "A") is True  # case-insensitive


def test_has_drive_prompt_zcpr_matches_requested_drive_only():
    """Verifies: DR-033."""
    # DR-033: the embedded digits are the user area, not the drive — a ZCPR
    # prompt for drive A must not satisfy a request for drive B.
    assert CPMParser.has_drive_prompt("4A>", "B") is False


def test_has_drive_prompt_ignores_path_style_prompt():
    """Verifies: DR-033."""
    # DR-033: path-style prompts containing ':' (e.g. "A0:BASE>") are out of scope.
    assert CPMParser.has_drive_prompt("A0:BASE>", "A") is False


def test_drive_prompt_letter_extracts_plain_prompt():
    """Verifies: DR-033a, FR-042."""
    # DR-033a/FR-042: the probe discovers the remote's drive from the prompt.
    assert CPMParser.drive_prompt_letter("A>") == "A"


def test_drive_prompt_letter_extracts_zcpr_prompt():
    """Verifies: DR-033a."""
    # DR-033a: ZCPR user-area digits are stripped, leaving the drive letter.
    assert CPMParser.drive_prompt_letter("B0>") == "B"
    assert CPMParser.drive_prompt_letter("4C>") == "C"


def test_drive_prompt_letter_upper_cases_result():
    """Verifies: DR-033a."""
    # DR-033a: the returned letter is upper-cased regardless of prompt case.
    assert CPMParser.drive_prompt_letter("d>") == "D"


def test_drive_prompt_letter_returns_first_prompt():
    """Verifies: DR-033a."""
    # DR-033a: the FIRST drive prompt on a non-blank line wins.
    assert CPMParser.drive_prompt_letter("\n\nB:\nB: FOO BAR\nB>\nA>\n") == "B"


def test_drive_prompt_letter_none_when_absent():
    """Verifies: DR-033a, FR-043."""
    # DR-033a/FR-043: no prompt -> None (which triggers the probe retry/failure).
    assert CPMParser.drive_prompt_letter("\n  \nNot ready\n") is None
    assert CPMParser.drive_prompt_letter("A0:BASE>") is None


# --------------------------------------------------------------------------- #
# parse_dir_output boundary / edge cases (DR-001-DR-032).
# --------------------------------------------------------------------------- #


def test_parse_dir_output_joins_multi_token_base():
    """Verifies: DR-011."""
    # DR-011: the base is every token except the last (the extension) joined
    # without spaces; pins the documented join so it cannot regress to tokens[0].
    assert CPMParser.parse_dir_output("A: FOO BAR TXT") == {"FOOBAR.TXT": True}


def test_parse_dir_output_accepts_lowercase_drive_letter():
    """Verifies: DR-004."""
    # DR-004: the drive identifier is matched case-insensitively (line[0].isalpha).
    assert CPMParser.parse_dir_output("c: GAME COM") == {"GAME.COM": True}


def test_parse_dir_output_skips_empty_entry_between_delimiters():
    """Verifies: DR-011."""
    # DR-011: an empty entry produced by adjacent ' : ' delimiters is skipped,
    # leaving the surrounding real files intact.
    assert CPMParser.parse_dir_output("A: FOO     TXT :  : BAR     COM") == {
        "FOO.TXT": True,
        "BAR.COM": True,
    }


def test_parse_dir_output_bar_format_skips_dot_only_entry():
    """Verifies: DR-015."""
    # DR-015: a bar entry that is only a dot (empty name and extension) is
    # discarded rather than yielding an empty filename.
    assert CPMParser.parse_dir_output("|  .    |  PIP     .COM") == {"PIP.COM": True}


def test_parse_dir_output_deduplicates_repeated_names():
    """Verifies: DR-011."""
    # DR-011: a name appearing twice collapses to a single entry.
    assert CPMParser.parse_dir_output("C: FOO      TXT : FOO      TXT") == {"FOO.TXT": True}


def test_parse_dir_output_handles_crlf_line_endings():
    """Verifies: DR-001."""
    # DR-001: real serial output is CRLF-terminated; splitlines must handle it.
    assert CPMParser.parse_dir_output("C: FOO      TXT\r\nC>\r\n") == {"FOO.TXT": True}


def test_parse_dir_output_empty_input_yields_no_files():
    """Verifies: DR-001."""
    # DR-001: empty / whitespace-only input yields an empty mapping, never raises.
    assert CPMParser.parse_dir_output("") == {}
    assert CPMParser.parse_dir_output("   \n\t\n") == {}
