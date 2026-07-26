# QA test design

## Purpose

Derive a small set of high-information tests from behavior and risk.

## Decision checks

1. Partition valid and invalid input classes; select representative values.
2. Test on, immediately below, and immediately above meaningful boundaries.
3. For interacting rules, use a decision table or pairwise method before
   enumerating combinations.
4. Choose the cheapest level that proves the claim:
   pure logic at unit level, service contracts at integration level, critical
   user journey at system level.
5. Include negative paths and failure injection where recovery matters.
6. Verify observable outcome and durable side effects, not implementation steps.
7. Control time, randomness, identity, locale, network, and data when they
   affect determinism.
8. Keep one reason per test; remove duplicate cases that prove no new condition.

## Stop conditions

Do not mock away the boundary being tested. Do not add end-to-end coverage for
logic already proven cheaply unless the integration itself is the risk. Flaky
tests are defects in evidence and need a reproducible owner.
