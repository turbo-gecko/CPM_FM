# Security Policy

Thank you for helping keep **CP/M File Manager (`cpm-fm`)** and its users safe.

## Supported versions

Security fixes are applied to the latest release on the `main` branch. We
recommend always running the most recent version.

| Version         | Supported          |
| --------------- | ------------------ |
| Latest release (`main`) | :white_check_mark: |
| `2.36.x`        | :white_check_mark: |
| Older `2.x`     | :x: (upgrade recommended) |
| `1.x` and earlier | :x:              |

The current version is recorded in [`src/version.txt`](../src/version.txt) and
shown in **Help → About**.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report privately using GitHub's confidential vulnerability reporting:

1. Go to the repository's **Security** tab →
   [**Report a vulnerability**](https://github.com/turbo-gecko/CPM_FM/security/advisories/new).
2. Fill in the advisory form with as much detail as you can.

This routes your report privately to the maintainers.

Please include, where possible:

- The `cpm-fm` version and your operating system.
- A description of the vulnerability and its potential impact.
- Steps to reproduce, a proof of concept, or affected source
  file(s)/function(s).
- Any relevant configuration (for example, serial setup or a disk-image
  scenario).

## What to expect

- **Acknowledgement:** we aim to acknowledge your report within **7 days**.
- **Assessment:** we will investigate, confirm the issue, and keep you updated
  on progress.
- **Fix & disclosure:** once a fix is ready we will release it and, with your
  agreement, publish a security advisory. We are happy to credit you for the
  discovery unless you prefer to remain anonymous.
- Please give us a reasonable opportunity to release a fix before any public
  disclosure (coordinated disclosure).

## Scope

`cpm-fm` is a desktop application that communicates over a **local serial link**
with legacy CP/M hardware; it is not a networked service. Relevant security
considerations include, for example:

- Handling of untrusted files, filenames, and `DIR`/terminal output received
  from a remote CP/M system.
- Parsing of CP/M disk images.
- Local handling of configuration and history files.

Reports about third-party dependencies (PySide6, pyserial, qt-material,
markdown, pyte) are welcome; where the issue is in the upstream project, please
also report it upstream.

Thank you for reporting responsibly.
