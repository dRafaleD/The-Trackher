# Trackher

Trackher is an open-source Python application for reviewing parts of your own
digital footprint and cleaning selected local traces on your own devices.
It ships with both a GUI and a CLI, and it is designed around cautious,
evidence-based checks instead of aggressive or side-effectful probing.

> Trackher should only be used on accounts, email addresses, usernames, and
> devices that belong to you, or for which you have explicit permission. See
> [ETHICS.md](ETHICS.md) for the usage policy.

## Why Trackher

- Evidence-based email and username OSINT
- Local cleanup tools for shell history, browser traces, and system caches
- Best-effort secure deletion for files and directories
- HTML and JSON reporting
- Dry-run support before any destructive action
- Windows, macOS, and Linux support
- Scheduled cleanup support for Windows Task Scheduler, macOS `launchd`, and Linux `cron`

## Safety Model

Trackher is intentionally conservative.

- Risky account checks that may trigger password resets, OTP messages, sign-in
  notices, or other side effects are skipped.
- Destructive actions require either `--dry-run`, interactive confirmation, or
  an explicit `--yes` flag.
- Critical system paths, user root paths, and protected exclusions are blocked
  from bulk deletion.
- HTML reports escape dynamic values and reject unsafe links.

## Features

### OSINT

- Username scan across 197 platforms
- Email catalog with 110 services
- Up to 2 side-effect-free automatic email checks (`Gravatar` avatar existence
  via its documented `d=404` behavior, and `Have I Been Pwned` breach lookup
  via the official API v3 when `HIBP_API_KEY` is set)
- Search engine dork generation for manual investigation
- Optional Have I Been Pwned API v3 support through `HIBP_API_KEY`

### Cleanup

- Shell and terminal history cleanup
- Browser cache and selected browser trace cleanup
- Cross-platform system temp and cache cleanup
- Exclusion list support through JSON config

### Secure Deletion

- Best-effort overwrite and delete for files
- Recursive directory shredding
- Symlink and critical-path protections

## Requirements

- Python 3.10 or newer
- Internet connection for OSINT features
- Tk support for the GUI

If Tk is missing on Debian or Ubuntu:

```bash
sudo apt install python3-tk
```

## Dependencies

Main runtime dependencies: `rich`, `httpx`, `customtkinter`, `Pillow`

## Installation

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Running `python main.py` with no arguments launches the GUI if GUI
dependencies are available. Passing arguments runs the CLI mode.

## Quick Start

### Email and username checks

```bash
python main.py --email user@example.com
```

```text
[INFO] Scanning: user@example.com
[+] Found on 1/110 services: Gravatar
[?] 1 result could not be verified: Have I Been Pwned
```

```bash
python main.py --username example_user
```

```text
[INFO] Scanning: example_user
[+] Found on 3/197 platforms: Reddit, GitLab, Medium
[?] 4 platform checks could not be verified
```

```bash
python main.py --email user@example.com --search-dork
```

```text
[INFO] Generated search links for: user@example.com
[+] Google, Bing, DuckDuckGo, and Yandex dorks ready
```

### Cleanup preview and execution

```bash
python main.py --clean-all --dry-run
python main.py --clean-all --yes
python main.py --clean-browser --clean-system --dry-run
```

### Exclusions

```bash
python main.py --clean-all --dry-run --exclude exclusions.example.json
```

### Secure deletion

```bash
python main.py --shred /path/to/file --dry-run
python main.py --shred /path/to/file --yes
```

### Scheduled cleanup

```bash
python main.py --schedule weekly --dry-run
python main.py --schedule weekly --yes
```

## Reports

Trackher can generate reports in HTML or JSON:

```bash
python main.py --email user@example.com --report html
python main.py --username example_user --report json
```

Generated report filenames follow this pattern:

- `footprint_report_html.html`
- `footprint_report_json.json`

These files are already ignored by `.gitignore`.

## HIBP API Support

Have I Been Pwned requests use the official API v3 and require an API key.

### PowerShell

```powershell
$env:HIBP_API_KEY="your-api-key"
```

### Bash

```bash
export HIBP_API_KEY="your-api-key"
```

If `HIBP_API_KEY` is not set, Trackher will not send the HIBP request.
Do not commit API keys, screenshots containing keys, or generated reports with
sensitive data.

Reported vulnerabilities are handled through the disclosure process described in
[SECURITY.md](SECURITY.md).

## Platform Support

| Feature | Windows | macOS | Linux |
|---|:---:|:---:|:---:|
| GUI | Yes | Yes | Yes |
| CLI | Yes | Yes | Yes |
| OSINT | Yes | Yes | Yes |
| Cleanup | Yes | Yes | Yes |
| Scheduling | Yes | Yes | Yes |
| Context menu helper | Yes | No | Limited |

## Testing

```bash
python -m pip check
python -m compileall -q footprint osint utils gui.py main.py setup_context_menu.py
python -m unittest discover -s tests -v
```

The project includes automated tests for:

- Cross-platform cleanup path selection
- Safe deletion and exclusion handling
- HTML report escaping
- Non-interactive destructive action protection
- Username and email detection rules
- GUI queue and terminal memory behavior

## Repository Guide

- [CONTRIBUTING.md](CONTRIBUTING.md): contribution workflow
- [SECURITY.md](SECURITY.md): security disclosure policy
- [ETHICS.md](ETHICS.md): acceptable use policy
- [CHANGELOG.md](CHANGELOG.md): release history
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md): community expectations

## Limitations

- Secure deletion is best-effort and cannot guarantee physical overwrite on SSD,
  copy-on-write, journaled, compressed, or network-backed file systems.
- OSINT results can change as services update their behavior, anti-bot rules,
  or public endpoints.
- A positive result should not be treated as sole proof of identity or account ownership.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
