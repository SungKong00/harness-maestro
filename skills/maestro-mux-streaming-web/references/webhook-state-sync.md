# Webhook state sync

## Purpose

Authenticate Mux webhook deliveries and turn duplicate, retried, delayed, or
reordered events into idempotent, observable application state transitions.

## Use when

Use for a Mux webhook endpoint, asset or live-state synchronization, replaying
failed deliveries, changing endpoint environments, or diagnosing state drift.

## Inputs

- Endpoint signing secret and its owning Mux environment.
- Framework access to the unmodified raw request body and signature header.
- Relevant event types, event identity, provider timestamps, and resource IDs.
- Durable event ledger or idempotency mechanism.
- State-transition rules, retry strategy, reconciliation mechanism, and
  observability fields.

## Decision checks

1. Capture the raw request bytes before JSON middleware changes them.
2. Verify `mux-signature` with the endpoint signing secret and timestamp
   tolerance before parsing or mutating application state. Prefer an official
   SDK verifier when supported.
3. Bind endpoint configuration and secrets to the correct Mux environment.
   Local forwarding is development tooling, not a production delivery
   guarantee.
4. Persist event identity or an equivalent idempotency record in the same
   durable boundary as the state transition.
5. Make repeated processing safe. Return a successful acknowledgement for an
   already-committed valid event instead of applying the transition twice.
6. Do not assume delivery order. Validate transitions using resource identity,
   current state, and provider time; reconcile ambiguous gaps.
7. Return non-2xx only when retry is useful. Mux retries failed deliveries with
   increasing delay, so permanent failures need quarantine and operator
   evidence rather than an infinite local loop.
8. Keep the response path bounded. Move slow follow-up work to a durable queue
   after authenticating and recording the event.

## Required evidence

- Valid and invalid signature tests using exact raw bytes.
- Environment-bound secret configuration without revealing the secret.
- Duplicate, reordered, delayed, malformed, unknown-event, transient-failure,
  and permanent-failure execution evidence.
- A durable event and state record that supports replay and reconciliation.
- Logs or metrics for accepted, duplicate, rejected, retried, quarantined, and
  reconciled events.

## Reject or stop when

- The framework cannot expose the raw body used for signature verification.
- Endpoint signing secret and Mux environment ownership are ambiguous.
- State is mutated before authenticity is established.
- The consumer assumes exactly-once or ordered delivery.
- A non-2xx retry path can repeatedly perform a non-idempotent side effect.

## Verification

Execute signature vectors against unchanged and modified bodies, then replay
the same valid event concurrently and sequentially. Send allowed events out of
order, inject a transient failure, and reconcile a deliberately missed event.
Confirm bounded acknowledgements and secret-free diagnostics.

## Counterexamples

- Client-side player events are not a substitute for authenticated Mux
  webhooks.
- A generic webhook library without Mux signature and delivery semantics is
  insufficient evidence.
- Broad integration test planning belongs to `software-qa`.
