# Contributing

Thanks for helping improve Trackher.

## Principles

- Keep changes focused and reviewable.
- Prefer evidence-based detections over heuristic guesses.
- Do not add checks that can trigger password resets, OTP messages, sign-in
  notifications, or account creation flows.
- Treat cleanup and deletion code as safety-critical.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Before Opening a Pull Request

Run the full verification suite:

```bash
python -m pip check
python -m compileall -q footprint osint utils gui.py main.py setup_context_menu.py
python -m unittest discover -s tests -v
```

## Code Guidelines

- Add tests with every behavioral change.
- For OSINT features, only report a positive match when there is clear,
  service-specific evidence.
- For cleanup features, keep protections for critical paths, user roots, and
  exclusions intact.
- Avoid broad changes that mix product work, refactors, and documentation in a
  single pull request.

## Reporting New Checks

If you add or modify a service check:

- document the source of truth used for verification
- prove that the check is side-effect-free
- include tests that cover false positives and blocked or unknown states
- if you add remediation links, keep them official, user-facing, and limited to `http` / `https` URLs only

## Updating Catalogs

Trackher keeps its platform catalogs in JSON:

- username platforms: `osint/platforms.json`
- email platforms and breach providers: `osint/email_platforms.json`

When updating a platform entry, keep the current runtime shape in mind:

- username entries use `url_pattern`, `error_type`, `reliability`, and the
  detector-specific metadata fields already used by the runtime
- email entries use `section`, `category`, `check`, `probe_url` or
  `profile_url_template`, and the metadata fields already consumed by the
  detector runtime
- `verified` means the result is backed by clear, side-effect-free evidence
- `unreliable` / `heuristic` means the detector is still passive but weaker
- `manual` means no safe automatic check is available

If you change catalog logic, add tests that cover:

- `FOUND`, `NOT_FOUND`, `POSSIBLE`, `UNKNOWN`, `MANUAL`, and error handling
- reliability normalization, especially that heuristic results never become
  verified `FOUND`
- remediation metadata serialization when official links are added
- reporting output if the change affects CLI, GUI, HTML, or JSON exports

## Adding a New Username Platform

Username platform definitions live in `osint/platforms.json`.

1. Add a new JSON entry with at least these fields:
   `name`, `url_pattern`, `error_type`, `reliability`, and either
   `expected_status` or `error_msg`.
2. Use `{username}` as the placeholder inside `url_pattern`.
   If the probe endpoint differs from the profile page, also add
   `probe_url_pattern`.
3. Set `reliability` to `verified` only when the platform has a clear,
   service-specific proof such as an exact JSON field or a stable status-code
   contract. Use `unreliable` for heuristic HTML/message checks.
4. If the platform needs structured parsing, include the matching metadata such
   as `check`, `json_path`, `json_list_path`, `profile_id_path`, `accept`, or
   `profile_url_pattern`.
5. Run the username verification suite before opening the pull request:

```bash
python -m unittest tests.test_platform_catalog tests.test_username_checker -v
```

6. If your change affects email catalogs, reporting, or catalog loading, also run:

```bash
python -m unittest tests.test_email_checker tests.test_platform_catalog tests.test_health -v
```

7. If your change touches runtime modules or catalog loading, also run:

```bash
python -m compileall -q osint utils tests
```

## Security and Responsible Use

Please review:

- [SECURITY.md](SECURITY.md)
- [ETHICS.md](ETHICS.md)

If you believe you found a vulnerability, do not open a public issue with
exploit details.
