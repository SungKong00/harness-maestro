# Playback integration

## Purpose

Create one explicit boundary between application media state and Mux Player so
playback identity, policy, stream behavior, media assets, and diagnostics do not
drift across components.

## Use when

Use for Mux-backed VOD or live playback, a Mux Player framework integration, a
player migration, or custom controls and overlays around a Mux player.

## Inputs

- Target framework, rendering model, and installed Mux Player package version.
- Playback ID and its public, signed, or DRM policy.
- VOD, live, or on-demand stream semantics.
- Video title, viewer and video metadata, captions, poster, storyboard, and
  accent or theme requirements.
- Existing loading, permission, unavailable, offline, and fatal error states.

## Decision checks

1. Treat the playback ID as the media identifier. Keep policy-specific URL or
   token assembly behind one typed application boundary.
2. Select the framework package and rendering boundary that match the target
   runtime. Account for client-only APIs and server rendering explicitly.
3. Pass stream type, metadata, captions, poster, storyboard, and purpose-bound
   tokens as declared inputs. Do not let unrelated components reconstruct them.
4. Prefer native Mux Player behavior for playback controls, captions, keyboard
   input, screen-reader semantics, timeline preview, error recovery, and Mux
   Data integration before replacing it.
5. When custom overlays are required, preserve focus order, accessible names,
   caption access, pointer and keyboard controls, full-screen behavior, and
   responsive containment.
6. Define player lifecycle ownership. Event subscriptions, timers, observers,
   and token refresh callbacks must be released or replaced on media changes.
7. Separate application authorization errors, provider playback errors, network
   failures, and unsupported browser behavior in UI state and telemetry.

## Required evidence

- The package and API reference used for the target framework.
- A concrete playback ID policy and test media in the intended Mux environment.
- Rendered player evidence at representative widths and keyboard focus states.
- Runtime evidence for ready, playing, paused, ended, denied, unavailable, and
  fatal error paths that are reachable in the product.

## Reject or stop when

- The playback ID policy or target Mux environment is unknown.
- Signing credentials or stream keys are proposed for browser delivery.
- The framework/runtime boundary is incompatible with the selected player
  package and no current compatibility evidence exists.
- Custom controls remove required captions, keyboard access, accessible naming,
  or user control over playback.

## Verification

Render with real authorized and unauthorized media. Verify metadata, captions,
poster and storyboard behavior; keyboard and focus flow; responsive sizing;
full-screen and media changes; cleanup after unmount; and distinct error
handling. Confirm that Mux Data receives the intended non-sensitive identity
metadata.

## Counterexamples

- A decorative background video with no Mux integration belongs to product
  design and ordinary frontend implementation.
- Choosing card layout, typography, or content hierarchy around an existing
  player belongs to `product-design`.
- Generic browser media testing belongs to `software-qa`.
