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

## Security and Responsible Use

Please review:

- [SECURITY.md](SECURITY.md)
- [ETHICS.md](ETHICS.md)

If you believe you found a vulnerability, do not open a public issue with
exploit details.
