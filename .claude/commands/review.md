---
description: Review current changes with reviewer (and security-auditor if sensitive)
---
Run the `reviewer` agent on the current diff. If the diff touches auth, permissions, uploads, playback or nginx, also run
`security-auditor`. Summarize findings, fix BLOCKERs, list the rest.
