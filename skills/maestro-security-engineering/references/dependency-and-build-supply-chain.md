# Dependency And Build Supply Chain

## Purpose

Choose supplier, dependency, integrity, isolated-build, provenance, vulnerability-response, and rollback requirements proportionate to risk.

## Use when

- software supply chain
- dependency security
- build provenance
- supplier due diligence
- 소프트웨어 공급망
- 의존성 보안
- 빌드 출처
- 공급자 실사

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Dependency inventory, lock or resolution evidence, build inputs, and provenance
- Current supplier, package registry, vulnerability, and build-system documentation

## Decision checks

- Inventory direct, transitive, build, runtime, and delivered dependencies with owners and update paths.
- Define supplier and component acceptance criteria from impact, support, provenance, and vulnerability response.
- Verify package and source integrity; isolate and harden builds proportionate to the threat model.
- Choose a provenance assurance level explicitly and keep emergency update and rollback paths.

## Required evidence

- Dependency inventory, lock or resolution evidence, build inputs, and provenance
- Current supplier, package registry, vulnerability, and build-system documentation

## Reject or stop when

- An artifact is accepted when its source or integrity cannot be established and no owner accepts the risk.
- A vulnerable dependency has no update, containment, exception, or rollback owner.

## Verification

- Rebuild from declared inputs and verify provenance and artifact identity where supported.
- Exercise dependency update, compromise containment, and rollback on representative components.

## Counterexamples

- Do not claim provenance proves absence of vulnerabilities.
- Do not require the same assurance level for an internal prototype and a critical release.
