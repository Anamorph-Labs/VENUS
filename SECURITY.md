# Security

Please report a security problem privately, never in a public issue: use the
**Report a vulnerability** button under this repository's Security tab. Anamorph
Labs answers within a few days and credits you when it is fixed, if you wish.

How Venus stays safe by design:
- Everything runs on the user's own computer; nothing is uploaded.
- Community add-ons are data files, never code; every value is checked before use.
- No contribution is added to the main code directly. Proposals wait in a holding
  area, are scanned automatically (tests, a test render, CodeQL, Bandit, Semgrep,
  Gitleaks, pip-audit, a licence check) and are built into Venus by Anamorph Labs.
- Checks on proposals run with read-only access and no secrets.
