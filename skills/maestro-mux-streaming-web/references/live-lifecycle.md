# Live lifecycle

## Purpose

Translate Mux Live state and recording events into explicit, recoverable
application state without leaking ingest credentials or inferring authority
from local player behavior.

## Use when

Use for a Mux Live viewer page, pre-live waiting room, reconnecting broadcast,
ended-state handling, live recording catalog, or live-to-VOD continuity.

## Inputs

- Mux environment, live stream ID, playback ID, and playback policy.
- Relevant Mux live and asset webhook event types.
- Product meanings for scheduled, waiting, live, reconnecting, ended,
  cancelled, and replay available.
- Reconnect grace period, recording configuration, and replay publication
  policy.
- Existing durable stream and asset records.

## Decision checks

1. Keep stream keys and ingest credentials in protected broadcaster or server
   boundaries. Never deliver them to a viewer page.
2. Define one application state model that distinguishes Mux provider state
   from scheduled product state and local player state.
3. Map connected, recording, active, disconnected, idle, and relevant asset
   events to allowed transitions. Record event identity and provider time.
4. Use an explicit reconnect grace period. A short disconnect need not mean a
   permanently ended product event, but the browser cannot decide authority
   alone.
5. Preserve the one-live-stream-to-many-recording-assets relationship. Track
   active and completed assets by identity; do not overwrite prior recordings
   with the latest asset.
6. Define how missed, delayed, or reordered events are reconciled against
   provider state.
7. Keep viewer fallback deterministic: waiting, live, temporarily reconnecting,
   ended without replay, replay processing, replay ready, and unavailable.
8. Separate ingest health, playback health, and application scheduling
   failures in telemetry and user messaging.

## Required evidence

- A state-transition table with authoritative inputs and forbidden
  transitions.
- Captured or fixture Mux live and asset event payloads with secrets removed.
- Durable records showing live stream and recording asset relationships.
- Executed waiting, active, disconnect/reconnect, idle, recording-processing,
  replay-ready, duplicate-event, and missed-event reconciliation paths.

## Reject or stop when

- Viewer state is derived only from browser player callbacks or polling.
- Stream keys appear in client configuration, logs, fixtures, or screenshots.
- The product's meaning of ended versus reconnecting is undefined.
- Recording logic assumes exactly one asset per live stream.
- Event ordering is treated as guaranteed.

## Verification

Replay a bounded event sequence through the state reducer and persistent
consumer. Verify allowed transitions, duplicates, reordered events, reconnect
grace behavior, ended-state semantics, and multiple recording assets. Compare
durable state with the Mux environment after intentionally omitting one event.

## Counterexamples

- Building an encoder or RTMP broadcaster is outside this web playback Pack.
- General event-page layout and waiting-room visual design belong to
  `product-design`.
- Generic state-machine test design belongs to `software-qa`.
