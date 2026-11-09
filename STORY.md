# Detour integration evidence

## Before

2026-11-09, approximately 12:40 PM Mountain Time. Radar MCP confirmed the
`bumblebee` cluster, namespace `team-bumblebee`, with the original starter
Deployment `app` (2/2 replicas ready). No Argo CD Application `app` existed yet.

[Namespace Checks](https://app.radarhq.io/checks?scope=7rQNMDbB570&namespace=team-bumblebee)

Radar reported 0 high and 3 medium findings on `Deployment/team-bumblebee/app`:

- `automountServiceAccountToken`: service account token automatically mounted.
- `missingPDB`: two replicas without a PodDisruptionBudget.
- `missingTopologySpread`: two replicas without topology spread constraints.

Detour disables token automounting and uses one replica to serialize synthetic demo
mutations. This is a deliberate hackathon availability tradeoff, not a claim of high
availability. Cross-process session and agenda updates also use optimistic concurrency.

## Elasticsearch: verified locally against the real project

- Elasticsearch reported version 9.7.0; `.jina-embeddings-v5-text-small` is available.
- All 30 explicitly fictional sessions indexed using a `semantic_text` mapping.
- Query `sniffing interpod conversations`: keyword search returned no hits;
  semantic search returned Seeing Traffic Without Sidecars, Packets, Policies and
  Pod Identity, Tracing the Invisible, Inside Cilium's Datapath, and Following a
  Packet Across the Cluster in its top five.
- A saved agenda was read using a separate Elasticsearch client, establishing persistence.
- Reproduce with `scripts/verify_elastic.py`; no credentials appear in its output.

## Gitar: real review findings

[API PR #1](https://github.com/srbhklkrn/cloudnative-hackathon/pull/1)
received a Gitar review identifying HTTPS proxy-origin handling, initialization
recovery and concurrent organizer updates. Commit `391d557` fixes these and adds
regressions, taking the backend suite from 20 to 23 passing tests.
Auto-apply was requested through Gitar's PR interface. Final review and CI status
must be checked before merge; a passing Gitar check alone does not mean no findings.

## Remaining evidence

Public rollout, Dash0 ingestion/query verification, dashboards and hosted AI
investigations will be recorded here only after successful execution.
