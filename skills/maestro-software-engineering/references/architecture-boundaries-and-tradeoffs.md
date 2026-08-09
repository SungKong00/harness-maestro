# Architecture Boundaries And Tradeoffs

## Purpose

Choose responsibility, state, and dependency boundaries from explicit quality trade-offs and reversible seams.

## Use when

- architecture boundary
- module boundary
- dependency direction
- architecture tradeoff
- 아키텍처 경계
- 모듈 경계
- 의존성 방향
- 아키텍처 트레이드오프

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Repository dependency and call-site evidence for the affected surface
- Named quality attributes, constraints, owners, and current state boundaries
- At least one rejected alternative with the evidence that changed the choice

## Decision checks

- Name the entity, stakeholders, lifecycle, and decision scope before drawing a boundary.
- Map responsibilities, state owners, public interfaces, and dependency direction on both sides.
- Evaluate alternatives against named quality attributes instead of declaring a pattern universally best.
- Expose cycles, shared mutable state, temporal coupling, and cross-team ownership.
- Prefer the smallest reversible seam that supports an explicit migration and rollback path.

## Required evidence

- Repository dependency and call-site evidence for the affected surface
- Named quality attributes, constraints, owners, and current state boundaries
- At least one rejected alternative with the evidence that changed the choice

## Reject or stop when

- The proposed boundary is justified only by layer names or fashionable patterns.
- State or interface ownership is unknown.
- A cross-team or public commitment has no owner or compatibility decision.

## Verification

- Trace representative calls and state mutations across the proposed boundary.
- Check that the chosen seam can be introduced and reversed without an all-at-once rewrite.

## Counterexamples

- Do not split a cohesive local helper into a service merely to add a boundary.
- Do not preserve a dependency cycle behind a new interface and call it decoupled.
