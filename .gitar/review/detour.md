# Detour review rules

This public application uses synthetic conference data only. Never expose credentials,
request bodies, attendee tokens or search text in logs, traces, CI or frontend bundles.

- Store timezone-aware UTC timestamps; display with an explicit IANA time zone.
- Sessions overlap when start < other.end AND end > other.start. Adjacent sessions
  also need the documented synthetic building-transfer time.
- Canceled/full sessions and unverified accessibility metadata cannot satisfy requirements.
- Revalidate every saved session and accepted replacement against current state.
- Break ranking ties by start time and stable session ID. Preserve API contracts.
- Elasticsearch is the persistent store; memory mode is explicit development/testing only.
- Protect agenda writes with optimistic concurrency; never silently overwrite conflicts.
- Reset may touch only Detour's synthetic demo indices, never other project data.
- Require scheduling edge-case and API tests; use accessible labels, semantic controls,
  keyboard navigation and visible focus in the frontend.
- Review and verify auto-applied changes before merging. Do not manufacture CI failures.
