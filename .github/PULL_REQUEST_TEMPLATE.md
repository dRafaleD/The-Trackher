## Summary

- What does this change do?

## Verification

- [ ] `python -m pip check`
- [ ] `python -m compileall -q footprint osint utils gui.py main.py setup_context_menu.py`
- [ ] `python -m unittest discover -s tests -v`

## Safety Review

- [ ] No new side-effectful OSINT behavior was introduced
- [ ] Critical-path and exclusion protections remain intact
- [ ] Documentation was updated if behavior changed

## Notes

- Anything reviewers should pay special attention to?
