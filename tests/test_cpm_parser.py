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


def test_parse_dir_output_vertical_bar_format():
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
    # DR-015: an empty extension field leaves a trailing dot, which is stripped
    # so the name matches the extensionless convention (DR-014).
    assert CPMParser.parse_dir_output("|  LICENCE  .    |  PIP     .COM\n") == {
        "LICENCE": True,
        "PIP.COM": True,
    }


def test_has_drive_prompt_detects_prompt():
    # FR-102/DR-033: after "B:" the terminal answers with a "B>" prompt.
    assert CPMParser.has_drive_prompt("B>", "B") is True


def test_has_drive_prompt_detects_prompt_embedded_in_output():
    # The prompt may be preceded by the echoed command and other output.
    text = "B:\nB: SOMEFILE COM\nB>\n"
    assert CPMParser.has_drive_prompt(text, "B") is True


def test_has_drive_prompt_matches_lowercase_response():
    # DR-033: a lowercase prompt from the terminal satisfies an upper-case drive.
    assert CPMParser.has_drive_prompt("a>", "A") is True


def test_has_drive_prompt_matches_lowercase_request():
    # DR-033: a lowercase requested drive letter is matched case-insensitively.
    assert CPMParser.has_drive_prompt("A>", "a") is True


def test_has_drive_prompt_ignores_blank_lines():
    # FR-101: blank lines returned by the terminal must be ignored, and a
    # response without the prompt must report absent.
    assert CPMParser.has_drive_prompt("\n   \n\n", "B") is False
    assert CPMParser.has_drive_prompt("\n\nNot ready\n\n", "B") is False


def test_has_drive_prompt_rejects_different_drive():
    # A prompt for a different drive does not satisfy the requested drive.
    assert CPMParser.has_drive_prompt("A>", "B") is False


# --------------------------------------------------------------------------- #
# parse_dir_output boundary / edge cases (DR-001-DR-032).
# --------------------------------------------------------------------------- #


def test_parse_dir_output_joins_multi_token_base():
    # DR-011: the base is every token except the last (the extension) joined
    # without spaces; pins the documented join so it cannot regress to tokens[0].
    assert CPMParser.parse_dir_output("A: FOO BAR TXT") == {"FOOBAR.TXT": True}


def test_parse_dir_output_accepts_lowercase_drive_letter():
    # DR-004: the drive identifier is matched case-insensitively (line[0].isalpha).
    assert CPMParser.parse_dir_output("c: GAME COM") == {"GAME.COM": True}


def test_parse_dir_output_skips_empty_entry_between_delimiters():
    # DR-011: an empty entry produced by adjacent ' : ' delimiters is skipped,
    # leaving the surrounding real files intact.
    assert CPMParser.parse_dir_output("A: FOO     TXT :  : BAR     COM") == {
        "FOO.TXT": True,
        "BAR.COM": True,
    }


def test_parse_dir_output_bar_format_skips_dot_only_entry():
    # DR-015: a bar entry that is only a dot (empty name and extension) is
    # discarded rather than yielding an empty filename.
    assert CPMParser.parse_dir_output("|  .    |  PIP     .COM") == {"PIP.COM": True}


def test_parse_dir_output_deduplicates_repeated_names():
    # DR-011: a name appearing twice collapses to a single entry.
    assert CPMParser.parse_dir_output("C: FOO      TXT : FOO      TXT") == {"FOO.TXT": True}


def test_parse_dir_output_handles_crlf_line_endings():
    # DR-001: real serial output is CRLF-terminated; splitlines must handle it.
    assert CPMParser.parse_dir_output("C: FOO      TXT\r\nC>\r\n") == {"FOO.TXT": True}


def test_parse_dir_output_empty_input_yields_no_files():
    # DR-001: empty / whitespace-only input yields an empty mapping, never raises.
    assert CPMParser.parse_dir_output("") == {}
    assert CPMParser.parse_dir_output("   \n\t\n") == {}
