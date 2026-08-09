# QA quality handoffs

## Purpose

Make design, implementation, QA, and verification boundaries explicit.

## Before implementation

- resolve untestable acceptance language;
- identify high-risk state, data, permission, and dependency behavior;
- agree on observability and required fixtures;
- assign quality owners without making QA the sole owner of quality.

## During implementation

- record changed assumptions and newly discovered risk;
- keep testability hooks narrow and production-safe;
- distinguish a test plan from executed evidence;
- escalate a design defect instead of encoding it as the expected test result.

## Before release

- provide exact build/revision and environment;
- map risk to executed evidence;
- list failures, quarantined tests, waivers, and untested boundaries;
- separate fix verification from regression;
- hand the evidence to an independent Verifier.

## Reject

A “QA passed” message without build, command, result, environment, and gaps is
not a handoff. Verbal acceptance does not erase a known risk or waiver.
