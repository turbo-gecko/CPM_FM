import re

# A CP/M / ZCPR drive prompt at the start of a (stripped) line: an optional
# user-area number (ZCPR-style), the drive letter, an optional user-area number,
# then '>' (e.g. "A>", "A0>", "4A>"). Path-style prompts containing ':'
# (e.g. "A0:BASE>") are intentionally not matched (DR-033).
_DRIVE_PROMPT_RE = re.compile(r"^\d*([A-Za-z])\d*>")


# CP/M 2.2 file names are upper-case 8.3 names drawn from a restricted
# character set. These characters are reserved by CP/M as command-line / FCB
# delimiters and wildcards and may not appear in a file name (FR-148, DR-046).
# A space is also disallowed. Lower-case letters are *not* listed here: the CP/M
# CCP folds command-line arguments to upper case, so a lower-case host name is
# accepted by the remote unchanged and is treated as conforming.
CPM_INVALID_CHARS = frozenset(" <>.,;:=?*[]|/\\")


class CPMParser:
    """
    Implements the algorithm for extracting remote file names from the
    standard CP/M 2.2 4-column DIR output format (SRS docs/cpm_fm_requirements.md,
    DR-001 through DR-032).

    Satisfies: DR-001-DR-032.
    """

    @staticmethod
    def is_valid_8_3(name: str) -> bool:
        """Return True if ``name`` conforms to the CP/M 2.2 8.3 naming convention.

        A conforming name has a base of 1–8 characters and an optional extension
        of up to 3 characters, separated by a single dot, with every character
        drawn from the permitted set (no spaces or reserved characters, see
        ``CPM_INVALID_CHARS``). A name with no dot is valid when its base is
        1–8 characters; a trailing dot (an empty extension, e.g. ``FOO.``) is
        rejected because CP/M cannot represent it distinctly. Case is not
        checked — the CP/M CCP folds command-line arguments to upper case, so a
        lower-case host name uploads unchanged.

        Satisfies: FR-148, DR-046.
        """
        if not name or name.count(".") > 1:
            return False
        base, dot, ext = name.partition(".")
        if not (1 <= len(base) <= 8) or len(ext) > 3:
            return False
        # A dot with no extension ("FOO.") cannot be stored by CP/M.
        if dot and not ext:
            return False
        return all(ch not in CPM_INVALID_CHARS and 0x20 < ord(ch) < 0x7F for ch in base + ext)

    @staticmethod
    def suggest_8_3(name: str) -> str:
        """Derive a CP/M 8.3-conforming suggestion from ``name``.

        Used to pre-fill the rename field when an upload's name is rejected
        (FR-149): the base and extension are split on the final dot, stripped of
        reserved/invalid characters, upper-cased, and truncated to 8 and 3
        characters respectively. An empty base falls back to ``FILE`` so the
        suggestion is always itself valid (:meth:`is_valid_8_3`).

        Satisfies: FR-149.
        """
        base, dot, ext = name.rpartition(".")
        if not dot:  # no extension separator -> the whole name is the base
            base, ext = name, ""

        def clean(part: str, limit: int) -> str:
            kept = [
                ch for ch in part.upper() if ch not in CPM_INVALID_CHARS and 0x20 < ord(ch) < 0x7F
            ]
            return "".join(kept)[:limit]

        clean_base = clean(base, 8) or "FILE"
        clean_ext = clean(ext, 3)
        return f"{clean_base}.{clean_ext}" if clean_ext else clean_base

    @staticmethod
    def parse_dir_output(text: str) -> dict[str, bool]:
        """
        Parses the raw text output of a CP/M DIR command and returns a
        dictionary where keys are filenames in 'NAME.EXT' format.

        Satisfies: FR-077, DR-001-DR-006, DR-010-DR-015, DR-020-DR-026.
        """
        filenames = {}
        lines = text.splitlines()

        for line in lines:
            # 1. Ignore non-file lines
            line = line.strip()
            if not line:
                continue

            # Ignore lines starting with drive prompts (e.g., C>)
            if len(line) > 1 and line[0].isalpha() and line[1] == ">":
                continue

            # Ignore lines containing "NO FILE"
            if "NO FILE" in line.upper():
                continue

            # 2a. Vertical-bar format (DR-006): CP/M variants such as ZCPR/ZSDOS
            # emit listing lines that begin with '|', use '|' as the entry
            # delimiter, and have no drive prefix. The dot before the extension
            # is already present in the output (e.g. "ASM     .COM"), so each
            # entry only needs its internal whitespace removed (DR-015).
            if line.startswith("|"):
                for entry in line.split("|"):
                    # Remove all internal whitespace; the base is space-padded.
                    full_filename = "".join(entry.split())
                    if not full_filename:
                        continue
                    # An empty extension field leaves a trailing dot; drop it so
                    # the result matches the extensionless convention (DR-015).
                    full_filename = full_filename.rstrip(".")
                    if not full_filename:
                        continue
                    filenames[full_filename] = True
                continue

            # 2b. Identify file listing lines
            # Must start with a drive identifier (e.g., 'C:'). The ' : ' sequence
            # is only the delimiter *between* multiple entries on a line, so a
            # directory containing a single file has no ' : ' — such lines must
            # still be processed (DR-004/DR-005, DR-011).
            if not (len(line) > 1 and line[0].isalpha() and line[1] == ":"):
                continue

            # 3. Strip drive identifier (e.g., remove 'C:')
            content = line[2:].strip()

            # 4. Split file entries using the delimiter ' : ' (a single-file line
            # has no delimiter and yields one entry).
            entries = content.split(" : ")

            for entry in entries:
                # 5. Normalise whitespace
                # Replace multiple spaces with single space and trim
                normalized = " ".join(entry.split()).strip()
                if not normalized:
                    continue

                # 6 & 7. Parse filename and extension
                # Split by whitespace; last token is extension, others are base
                tokens = normalized.split()
                if not tokens:
                    # Skip empty entries
                    continue

                if len(tokens) == 1:
                    # A file with no extension (e.g. LICENCE): CP/M pads the
                    # extension field with spaces, leaving a single token after
                    # whitespace normalisation. List it as-is, with no trailing
                    # dot, so the name matches the host file (DR-013/DR-023).
                    full_filename = tokens[0]
                else:
                    extension = tokens[-1]
                    # Concatenate all preceding tokens without spaces for the base
                    filename_base = "".join(tokens[:-1])

                    # 8. Construct full filename
                    full_filename = f"{filename_base}.{extension}"

                # 9. Store in dictionary (duplicates are overwritten)
                filenames[full_filename] = True

        return filenames

    @staticmethod
    def has_drive_prompt(text: str, drive: str) -> bool:
        """Return True if a CP/M drive prompt for ``drive`` (e.g. ``A>``)
        appears on any non-blank line of ``text`` (DR-033).

        After a drive-change command (``<letter>:``) CP/M responds with a new
        drive prompt — the drive letter followed by ``>``. ZCPR-family CCPs
        embed the user-area number in the prompt, so the letter may be preceded
        and/or followed by decimal digits (e.g. ``A0>``, ``4A>``); all such
        forms are accepted. Blank lines are ignored and matching is
        case-insensitive. Path-style prompts containing ``:`` are not matched.

        Satisfies: DR-033, FR-101, FR-102.
        """
        target = drive.upper()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = _DRIVE_PROMPT_RE.match(line)
            if match and match.group(1).upper() == target:
                return True
        return False

    @staticmethod
    def drive_prompt_letter(text: str) -> str | None:
        """Return the drive letter of the first CP/M drive prompt in ``text``.

        Applies the same matching rule as :meth:`has_drive_prompt` (DR-033) but
        without a target drive letter: it scans the non-blank lines in order and
        returns the upper-cased drive letter (``A``-``P``) of the first drive
        prompt found, or ``None`` when none is present. Used by the post-connect
        probe (FR-041/FR-042) to discover which drive the remote is on without
        knowing it in advance.

        Satisfies: DR-033a, FR-041, FR-042.
        """
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = _DRIVE_PROMPT_RE.match(line)
            if match:
                letter = match.group(1).upper()
                if "A" <= letter <= "P":
                    return letter
        return None
