# QA scenario and state exploration

## Purpose

Expose failures hidden by happy-path examples.

## Scenario dimensions

- initial state, action, intermediate state, final state;
- first use, repeat use, retry, cancellation, interruption, and timeout;
- create/read/update/delete and empty/one/many;
- authenticated roles, tenant and ownership boundaries;
- offline, slow, partial, duplicated, reordered, or failed dependencies;
- concurrent operations and idempotency;
- migration, rollback, recovery, and restart;
- locale, time zone, clock boundary, and supported device/environment.

## Decision checks

1. Draw a state model when validity depends on history.
2. Test forbidden transitions as well as allowed transitions.
3. For persistence, verify atomicity, isolation expectations, retry behavior,
   uniqueness, and partial failure.
4. For asynchronous work, identify eventual consistency window and duplicate
   delivery behavior.
5. Use exploratory charters with mission, focus, data, timebox, and captured
   observations; “click around” is not a charter.

## Verification

Every scenario states initial conditions, action, oracle, evidence, and cleanup.
Keep environment-specific claims behind current evidence.
