# Playback observability

## Purpose

Make Mux playback health diagnosable while keeping provider delivery signals,
application failures, viewer identity, and product outcomes correctly scoped.

## Use when

Use for Mux Data metadata, startup delay, playback failure, rebuffering,
Playback Success, viewer incident diagnosis, or player error telemetry.

## Inputs

- Mux environment and the player integration path.
- Stable video, viewer, session, page, and experiment identifiers that are
  permitted for analytics.
- Product playback journey and failure categories.
- Current Mux Data events, dashboards, alerting, logs, and business metrics.
- Privacy, retention, and redaction requirements.

## Decision checks

1. Attach stable video and viewer metadata at the player boundary. Use
   pseudonymous identifiers where appropriate and never send tokens, secrets,
   stream keys, or unnecessary personal data.
2. Measure playback startup, fatal failure, rebuffering, completion, and
   Playback Success at consistent scopes and denominators.
3. Separate provider delivery health from application authorization, token
   issuance, network, browser, UI, and business-conversion failures.
4. Preserve a correlation path across application request, token issuance,
   player session, Mux Data, and webhook state without making a secret the
   correlation identifier.
5. Define diagnostic evidence and alert thresholds from product impact and
   baseline behavior. A single aggregate average can hide affected devices,
   regions, content, or release cohorts.
6. Treat missing telemetry as a failure mode. Confirm initialization timing,
   metadata changes, media changes, consent behavior, and teardown.
7. Pair provider metrics with rendered and application evidence before
   attributing a viewer failure to Mux or declaring the issue resolved.

## Required evidence

- A metadata dictionary with owner, sensitivity, cardinality, and retention.
- Successful and failing playback sessions visible in the intended Mux
  environment without secret values.
- Segmented startup, failure, rebuffering, and success evidence for relevant
  devices, regions, content, and release versions.
- Correlated application logs for authorization, token, network, player, and
  webhook failures.

## Reject or stop when

- Telemetry includes playback tokens, signing material, stream keys, webhook
  secrets, or unnecessary personal data.
- Viewer and video identifiers change unpredictably across the same diagnostic
  journey.
- Provider playback metrics are presented as product conversion proof.
- A dashboard or alert lacks a defined population, denominator, or action.
- The integration claims success without observing a real playback session.

## Verification

Run successful, authorization-denied, expired-token, offline, rebuffering, and
fatal-player scenarios. Confirm expected Mux Data and application events,
metadata, redaction, correlation, teardown, and cohort segmentation. Verify
that business metrics remain separately named and interpreted.

## Counterexamples

- Marketing video conversion analysis belongs to marketing measurement.
- General log architecture and SRE alert policy are broader than this Pack.
- Generic performance and failure-injection strategy belongs to
  `software-qa`.
