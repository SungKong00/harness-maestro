# Untrusted Data And Output Controls

## Purpose

Choose parsing, canonicalization, schema and semantic validation, parameterization, sanitization, and context-specific encoding at trust boundaries.

## Use when

- input security
- untrusted data
- output encoding
- file upload security
- 입력 보안
- 신뢰할 수 없는 데이터
- 출력 인코딩
- 파일 업로드 보안

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Framework and sink-specific official behavior
- Representative malicious, ambiguous, oversized, and alternate-encoding inputs

## Decision checks

- Identify the trust boundary, parser, canonical representation, semantic constraints, and downstream sinks.
- Use allowlist schema and semantic validation while preserving sink-specific parameterization and encoding.
- Treat files, URLs, archives, templates, commands, queries, and rendered markup as distinct sink classes.
- Define size, recursion, resource, timeout, and failure limits before expensive processing.

## Required evidence

- Framework and sink-specific official behavior
- Representative malicious, ambiguous, oversized, and alternate-encoding inputs

## Reject or stop when

- Validation exists only in the client.
- A denylist or generic sanitization is presented as protection for every sink.

## Verification

- Exercise parser differentials, canonicalization, sink injection, oversized input, and rejected-file paths.
- Confirm rejected data cannot reach a privileged sink through another entry path.

## Counterexamples

- Do not HTML-encode data intended for a SQL parameter.
- Do not reject all rich content when a scoped sanitizer and output contract are required.
