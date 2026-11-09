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
Gitar auto-applied event-first persistence with compensating cleanup. The API PR
merged after checks passed.

The [UI PR #2](https://github.com/srbhklkrn/cloudnative-hackathon/pull/2) received
two real polling-race findings. Gitar's commits `0944028` and `3330e14` queue and
await a fresh post-mutation snapshot. A browser regression deliberately holds an
in-flight poll while saving a session. Gitar also fixed small-screen text sizing in
`204e00e`; the final CSS preserves readable card labels on mobile.

The first UI CI run genuinely failed in `npm ci`. Gitar investigated the failure
and initially attributed it to npm tooling without proving the root cause. Inspection
showed the local lockfile contained private registry URLs. Regenerating against the
public npm registry fixed the builds (`f72cbbf`). Do not present Gitar's initial
hypothesis as the verified diagnosis. Subsequent CI passed backend, frontend and
Chromium jobs, including [run 42688406180](https://github.com/srbhklkrn/cloudnative-hackathon/actions/runs/42688406180).

The [observability PR #3](https://github.com/srbhklkrn/cloudnative-hackathon/pull/3)
received three additional findings: incomplete event rollback, an ignored explicit
MCP endpoint, and missing coverage for item-level Bulk API conflicts. Gitar fixed
them in `6386b05`/`93f70a6` and `fb1f816`. Local tests also cover non-conflict item
errors without masking the original failure.

Project review context lives in `.gitar/review/detour.md`; the explicit check rule
is `.gitar/rules/scheduling-contract.md`. A review that says "No rules evaluated"
does not establish that the check rule ran; rule execution is tracked separately.

## Dash0: verified ingestion and a real Agent0 investigation

The initial ingestion token could not query MCP (403). After the participant enabled
query permissions, the official MCP Python client successfully read dataset
`default`, service `detour-api`, traces, logs and metrics. The service catalog
initially reported 136 requests and zero HTTP errors. These were local integration
requests against real Elasticsearch, not traffic from a deployed version.

Agent0 investigation `897ec8fd-1de8-4755-bc81-381a0666b691` inspected genuine
telemetry. Its finding: two sequential writes using `refresh=wait_for` dominated
organizer latency. Reading Elasticsearch settings confirmed a **5s default refresh
interval**. Agent0 correctly distinguished that wait from an unproven inference
bottleneck, and identified duplicate HTTP instrumentation.

| Observed request | Total trace | Event write | Session write |
| --- | ---: | ---: | ---: |
| Before | 8.567s | 3.755s | 4.771s |
| After | 4.865s | 0.183s | 4.640s |

[Before trace](https://app.dash0.com/goto/traces/explorer?org=04f0aadf-6701-43ec-92a9-61f3ef36109d&dataset=default&from=2026-11-09T19%3A30%3A00.000Z&to=2026-11-09T19%3A45%3A00.000Z&trace_id=97e878c747b32d71becac65f38ff1d9e)
and [after trace](https://app.dash0.com/goto/traces/explorer?org=04f0aadf-6701-43ec-92a9-61f3ef36109d&dataset=default&from=2026-11-09T19%3A55%3A00.000Z&to=2026-11-09T20%3A10%3A00.000Z&trace_id=a6bdeb97739b885ba8959a5f3b582778).
These are individual observations, not a controlled performance benchmark.

Actions taken: retain one session refresh barrier so search sees the change before
success; stop waiting for agenda refresh because agendas use real-time GET; allow
event history to become searchable on its next refresh; use Bulk partial updates to
reuse unchanged semantic embeddings per [Elastic's documentation](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/semantic-text-ingestions);
disable FastAPI's overlapping native telemetry. The after trace has one Detour HTTP
root, one event-write span and one session-write span.

Agent0's dashboard task (`81f775aa-a8d9-458b-a487-3a960e8e4986`) returned a validated
Perses definition but could not create dashboards in that context. The definition
was adapted to Detour's custom request/error metrics and created using the official
REST API. Both API GET and MCP `listDashboards` confirmed it exists with 12 panels.

- Name: `detour-disruption-recovery`
- API origin: `api-8bcc23c9-5fac-4b46-8ff7-abbea0a0b045`
- MCP dashboard ID: `7f8f4e66-28f2-4a83-934f-8a63e12b3d31`
- [Dashboard list](https://app.dash0.com/dashboards?org=04f0aadf-6701-43ec-92a9-61f3ef36109d)
- Source: `observability/dash0-dashboard.json`

PromQL read-back of `detour.request.duration` returned live service data (0.2583
requests/s at 19:59:25 UTC). MCP log reads returned `API request completed` entries.
Datastore failure panels count failed API requests, excluding expected not-found
lookups. Native framework metrics from earlier local runs remain in historical data;
the checked-in dashboard uses the custom metrics.

## Validation and presentation

31 backend tests pass locally. All four Chromium tests pass against real Elasticsearch:
the attendee/organizer recovery flow, mobile/keyboard/time-zone behavior, deliberate
polling overlap, and automated WCAG AA checks for both views. The same browser tests
run in CI using explicitly labeled memory mode. The real Elasticsearch check is
separate and uses protected local credentials.

`docs/screenshots/` contains actual local-browser screenshots. `docs/architecture.html`
is a validated, standalone interactive diagram; its pinned source revision and
validation receipt are checked in. These are implementation evidence, not screenshots
of a public rollout.

## Deployment status

All three feature PRs are merged. The final source merge is `2b30eaa`.
[Build 42689393250](https://github.com/srbhklkrn/cloudnative-hackathon/actions/runs/42689393250)
succeeded and bot commit `2191e07` updated Kustomize to
`ghcr.io/srbhklkrn/cloudnative-hackathon:2b30eaa`. An anonymous registry request
for that exact tag returned 200 with manifest digest
`sha256:56a1583190bafe8b9ac2e3f1249d6332ad9ff309e581f42aef58831b86c2d632`.
The final local Docker image passed all four Chromium tests against real Elasticsearch.

Radar accepted a server-side dry run of `argocd/application.yaml`; no Application
was created. Its hosted AI investigation
[chat_I6wiDXKDB6aOqmg7](https://app.radarhq.io/c/7rQNMDbB570/investigations/chat_I6wiDXKDB6aOqmg7?org=org_NCJbssDGEBsU)
finished with a healthy verdict on the **original starter**: 2/2 ready, no restarts
or live issues, and a medium token-automount posture finding. Direct resource and
Checks reads independently confirmed the starter image and the same three medium
findings listed above. This establishes a baseline, not Detour rollout success.

Timeline `get_changes` returned no observed Deployment changes in the requested
two-hour window and explicitly limited coverage to observations after 18:54:26 UTC.
That limited history does not prove no earlier changes occurred.

Public rollout is pending the participant's `detour-credentials` Secret in
`team-bumblebee` (or a team-scoped kubeconfig to import it through a secure terminal).
Radar still shows the original 2/2 Node starter replicas. No Detour deployment,
post-rollout Checks, Timeline, or deployed-Detour AI investigation is claimed yet.
