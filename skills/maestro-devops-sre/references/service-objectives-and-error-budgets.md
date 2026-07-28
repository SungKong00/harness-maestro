# Service Objectives And Error Budgets

## Purpose

Define user-centered service indicators, objectives, windows, measurement limits, and error-budget actions.

## Use when

- service level objective
- slo
- error budget
- sli slo
- reliability target
- 서비스 수준 목표
- 에러 버짓
- 신뢰성 목표

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Production or representative event population and measurement method
- Product and operations owner decision on reliability and delivery trade-offs

## Decision checks

- Define the service, user journey, good event, valid population, and measurement window.
- Choose an SLI that reflects user-visible behavior and expose sampling or aggregation bias.
- Set an SLO from product and operational risk rather than copying a universal number.
- Define error-budget consumption, alerting, exception, and change-control actions with owners.

## Required evidence

- Production or representative event population and measurement method
- Product and operations owner decision on reliability and delivery trade-offs

## Reject or stop when

- The SLI measures only infrastructure health while the user-visible service can fail.
- An SLO number has no population, window, owner, or action policy.

## Verification

- Recompute the SLI from raw or independently aggregated evidence.
- Test that budget policy names a decision and owner rather than only a dashboard.

## Counterexamples

- Do not copy a 99.9 percent target without product impact and cost evidence.
- Do not call every internal component metric an SLI.
