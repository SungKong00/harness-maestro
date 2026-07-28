# Authorization And Tenant Isolation

## Purpose

Define subject-resource-action policy, ownership, tenant context, enforcement points, isolation, and privileged overrides.

## Use when

- authorization design
- tenant isolation
- resource ownership
- access control
- 인가 설계
- 테넌트 격리
- 리소스 소유권
- 접근 제어

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Complete entry-point and data-path inventory
- Policy examples covering ownership, cross-tenant denial, and privileged override

## Decision checks

- Express policy as subject, tenant, resource, action, context, and ownership rather than UI roles alone.
- Derive trusted tenant context from authenticated server-side state and enforce it on every storage, cache, queue, and object path.
- Choose isolation strength from impact and operational constraints; record shared-resource leakage paths.
- Define privileged, support, break-glass, invitation, transfer, suspension, and deletion behavior.

## Required evidence

- Complete entry-point and data-path inventory
- Policy examples covering ownership, cross-tenant denial, and privileged override

## Reject or stop when

- Any path trusts a client-supplied tenant or owner identifier without server-side binding.
- A fallback or missing annotation bypasses the same authorization rule.

## Verification

- Test equivalent policy across every entry and storage path.
- Verify tenant lifecycle and cache or queue behavior with real identifiers.

## Counterexamples

- Do not treat route hiding as authorization.
- Do not choose database-per-tenant without evaluating cost, migration, and operational failure modes.
