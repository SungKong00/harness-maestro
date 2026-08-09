# Authentication And Session Lifecycle

## Purpose

Choose authentication assurance, recovery, federation, session binding, timeout, reauthentication, and revocation from risk.

## Use when

- authentication design
- session lifecycle
- oauth security
- account recovery
- 인증 설계
- 세션 수명주기
- OAuth 보안
- 계정 복구
- OAuth 로그인 세션

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Identity flows, assurance assumptions, session stores, and revocation paths
- Current IdP, protocol, and platform documentation

## Decision checks

- Map user and action risk to an explicit authentication assurance need.
- Define enrollment, recovery, authenticator replacement, federation, and compromised-account response.
- Choose session creation, storage, binding, renewal, idle and absolute timeout, reauthentication, and revocation behavior.
- Apply OAuth-specific best current practice only when OAuth is actually in scope.

## Required evidence

- Identity flows, assurance assumptions, session stores, and revocation paths
- Current IdP, protocol, and platform documentation

## Reject or stop when

- Recovery is weaker than the protected authentication level without explicit risk treatment.
- Logout or compromise response cannot revoke or contain active sessions.

## Verification

- Exercise enrollment, recovery, expiry, reauthentication, logout, revocation, and stolen-token paths.
- Confirm missing or invalid identity context fails closed.

## Counterexamples

- Do not apply federal assurance requirements blindly to every private product.
- Do not treat authentication as proof of resource authorization.
