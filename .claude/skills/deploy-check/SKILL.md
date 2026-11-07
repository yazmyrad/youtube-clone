---
name: deploy-check
description: Verify one-command deploy on a clean Ubuntu VM and the main user scenario. Use before submission.
---
1. On a fresh Ubuntu VM: git clone, run ./install.sh only. No manual steps.
2. Check: containers healthy, migrations applied, MinIO bucket created, seed data loaded.
3. Run scenario: register -> upload -> wait for processing -> watch (HLS plays) -> like -> comment. Also private video denied to a stranger.
4. Fix install.sh/README for anything that needed manual intervention.
