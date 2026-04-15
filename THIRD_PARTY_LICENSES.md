# Third-party licenses

PAM is distributed under the MIT license (see `LICENSE`). It uses the following
open-source dependencies. All are redistributable under MIT.

| Package | License |
|---------|---------|
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| httpx | BSD-3-Clause |
| aiosqlite | MIT |
| aiosmtplib | MIT |
| pydantic-settings | MIT |
| tzlocal | MIT |
| cryptography | Apache-2.0 / BSD |
| google-api-python-client | Apache-2.0 |
| google-auth-httplib2 | Apache-2.0 |
| google-auth-oauthlib | Apache-2.0 |
| whisper.cpp (external binary) | MIT |
| ffmpeg (external binary) | LGPL / GPL (see ffmpeg.org) |
| Claude Code CLI (external binary) | Proprietary (Anthropic) |

To regenerate this file with exact versions:

```bash
pip install pip-licenses
pip-licenses --format=markdown --with-urls > THIRD_PARTY_LICENSES.md
```

**A note on ffmpeg**: PAM invokes the `ffmpeg` binary that must be installed on the host. It is not distributed with PAM. Users are responsible for sourcing a build that matches their license needs (LGPL vs GPL).

**A note on Claude Code CLI**: PAM invokes the `claude` binary via subprocess. It is not distributed with PAM. Users need an active Claude subscription.
