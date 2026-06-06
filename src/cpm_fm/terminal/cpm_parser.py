class CPMParser:
    """
    Implements the algorithm for extracting remote file names from the
    standard CP/M 2.2 4-column DIR output format (SRS docs/cpm_fm_requirements.md,
    DR-001 through DR-032).
    """

    @staticmethod
    def parse_dir_output(text: str) -> dict[str, bool]:
        """
        Parses the raw text output of a CP/M DIR command and returns a
        dictionary where keys are filenames in 'NAME.EXT' format.
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

            # 2. Identify file listing lines
            # Must start with drive identifier (e.g., 'C:') and contain ' : '
            if not (len(line) > 1 and line[0].isalpha() and line[1] == ":"):
                continue

            if " : " not in line:
                continue

            # 3. Strip drive identifier (e.g., remove 'C:')
            content = line[2:].strip()

            # 4. Split file entries using the delimiter ' : '
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
