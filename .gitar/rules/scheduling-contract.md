---
title: "Preserve Detour scheduling and API contracts"
description: "Check scheduling, accessibility and frontend contracts when application behavior changes"
type: check
when: "A pull request modifies backend Python, frontend TypeScript, or application deployment configuration"
actions: "Verify relevant edge-case coverage and API callers; report concrete mismatches in the PR verification results"
---

Follow `.gitar/review/detour.md`. For behavior changes, trace affected frontend callers
and tests. Check timezone-aware UTC storage, interval and transfer-time conflicts,
canceled/full exclusion, unverified accessibility metadata, replacement revalidation,
and deterministic ranking. For deployment changes, verify HTTPS origin/cookie behavior,
port 8080, Service app:80, Secret references and probes remain coherent.

Check that test evidence actually exists; do not invent results or manufacture failures.
Public build lockfiles must resolve through public registries without credentials.
Synthetic reset is explicitly required and affects only fixed detour-demo-* indices.
Do not contact people or external messaging services as part of this rule.
