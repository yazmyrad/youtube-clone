---
description: Implement one feature end to end in small steps
---
Implement: $ARGUMENTS

1. Read docs/architecture.md and relevant code. State a short plan (steps = commits). Wait for my OK if the plan touches schema.
2. For each step: migration (if needed) -> service -> router -> test -> run ruff+pytest -> commit.
3. At the end run the `reviewer` agent on the diff and fix BLOCKERs.
