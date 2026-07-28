# Secure playback

## Purpose

Keep Mux playback policy, application authorization, signing credentials,
purpose-bound tokens, expiry, and refresh behavior aligned across protected
server and browser boundaries.

## Use when

Use for signed playback, DRM playback, restricted thumbnails or storyboards,
viewer entitlements, expiring playback sessions, or token refresh failures.

## Inputs

- Playback ID and configured playback policy.
- Application user, entitlement, tenant, and media authorization rules.
- Protected signing service and key identifier.
- Required token audiences such as playback, thumbnail, storyboard, or DRM.
- Expected content duration, session duration, clock tolerance, and revocation
  or access-change semantics.

## Decision checks

1. Authorize the application user and requested media before issuing any Mux
   token. A valid token is not a replacement for product authorization.
2. Mint tokens only in a protected server environment. Keep private signing
   keys out of client bundles, public environment variables, logs, fixtures,
   and error messages.
3. Match the playback ID policy. Do not add a token to a public ID as if that
   converted it to signed playback, and do not request a signed ID without the
   required token.
4. Bind each token to the intended audience and resource. Do not reuse a
   playback token for thumbnails, storyboards, or DRM requests.
5. Choose expiry from the authorized viewing window and playback behavior.
   Cover permitted playback without creating unnecessarily long-lived bearer
   access.
6. Define refresh timing, deduplication, cancellation, and failure behavior.
   Avoid refresh loops and avoid replacing a newer token with a slower stale
   response.
7. Return the minimum token material to the browser over an authenticated,
   protected transport and prevent cache sharing across users.
8. Treat signing-key rotation, clock skew, revoked authorization, and expired
   sessions as explicit operational states.

## Required evidence

- The Mux playback policy for the exact playback ID.
- A server-side authorization and signing boundary with secret scanning or
  bundle inspection evidence.
- Token claim and audience inspection without recording live secrets.
- Executed allow, deny, expired, refresh, stale-response, and key-rotation
  checks appropriate to the implementation.

## Reject or stop when

- Token signing is proposed in browser code.
- The playback policy, token audience, key ID, or authorization owner is
  unknown.
- A token lifetime is chosen without considering authorized playback duration.
- Browser or CDN caching can serve one viewer's signed material to another.
- A DRM requirement is assumed without current Mux and platform evidence.

## Verification

Inspect the production client bundle and public configuration for secrets.
Exercise authorized and unauthorized requests, expiry before and during
playback, concurrent refreshes, logout or entitlement loss, and signing-key
rotation. Confirm that logs expose identifiers and failure classes without
token values or private keys.

## Counterexamples

- A public marketing video using a public playback ID does not need signed
  playback.
- General session authentication design remains an application security
  concern.
- A visual paywall layout belongs to `product-design`; this Guide governs only
  the Mux access boundary behind it.
