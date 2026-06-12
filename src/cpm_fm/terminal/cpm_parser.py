class CPMParser:
    """
    Implements the algorithm for extracting remote file names from the
    standard CP/M 2.2 4-column DIR output format (SRS docs/cpm_fm_requirements.md,
    DR-001 through DR-032).

    Satisfies: DR-001-DR-032.
    """

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
        drive prompt — the drive letter followed by ``>``. Blank lines returned
        by the terminal are ignored. Matching is case-insensitive.

        Satisfies: DR-033, FR-101, FR-102.
        """
        target = f"{drive.upper()}>"
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith(target):
                return True
        return False
