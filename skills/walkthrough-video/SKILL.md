---
name: walkthrough-video
description: Record, inspect, and attach a candidate-bound video walkthrough for a new user-facing UX before its pull request is created or updated. Use when a change adds a screen, control, interaction, or materially new visual journey that reviewers need to see in motion. Fixes may use visual-proof's paired screenshots instead unless the user asks for video.
---

# walkthrough-video

A new UX pull request carries a short movie of the real feature. The movie
helps a reviewer understand the journey; `development-loop`'s live-proof
receipt remains the authority that the journey worked.

## 1. Confirm that video is required

Video is required when the change adds or materially expands a user-facing
visual journey: a new screen, control, interaction, transition, or multi-step
flow. A visual fix may use `visual-proof`'s before/after screenshots. Pure API,
service, or CLI behavior with no graphical UX does not require a movie.

Record the classification in the change baton before creating or updating the
pull request. When required, name the journey the movie will show, its start
state, important interactions, terminal state, and forbidden surfaces. Plan
the journey early, but record only after `development-loop` freezes the final
reviewed candidate.

Complete when the baton says `walkthrough: required` or `walkthrough: not
required` with a reason, and a required walkthrough has a defined journey.

## 2. Bind and rehearse the real candidate

Use the product repository's existing journey runner, browser harness, or
native recording path. Bind the recorder to the exact frozen candidate and
running process using the same identity evidence as the live-proof receipt.
Complete authentication, MFA, account selection, and other protected input
before recording.

When no supported route can record the real surface, follow `visual-proof`
section 3a: add a debug-gated, repository-owned journey and recording route,
document it, and validate it as product code. An unbound desktop recording or
one-off external script does not prove which candidate was shown.

Run the entire journey once without recording. A rehearsal failure is product
or harness evidence to diagnose and fix, not a reason to hide the failed step,
prewarm data, select friendlier data, or trim the error away. After any fix,
rerun affected checks and the complete rehearsal.

Complete when the current candidate finishes the ordinary journey with every
named checkpoint visible and no forbidden or sensitive surface exposed.

## 3. Record a reviewable walkthrough

Reset to the declared start state and record one continuous pass through the
supported journey. Keep it concise, but preserve enough time to read each
important state. Show the trigger, meaningful interactions, and terminal
result. Do not include passwords, tokens, private messages, one-time codes, or
authentication screens.

Prefer MP4 or MOV using a broadly supported H.264 or HEVC video stream. Store
the movie and its receipt outside build inputs so recording does not change the
candidate fingerprint.

Complete when one final movie represents the full successful journey without
cuts that conceal product behavior.

## 4. Validate and inspect the movie

Run the bundled verifier:

```bash
python3 "<walkthrough-video-skill>/scripts/verify-walkthrough-video.py" \
  <movie.mp4> \
  --output <movie-receipt.json>
```

The verifier requires `ffprobe` and `ffmpeg`, fully decodes the video stream,
and records its hash, codec, dimensions, duration, and size. Then render and
inspect the beginning, every important interaction, and the terminal state.
Record falsifiable visual claims for those frames and confirm that no sensitive
or forbidden surface appears.

Extend the verifier's media receipt into a walkthrough receipt that also
contains:

- exact candidate and running-process identities;
- journey and checkpoint names;
- verifier receipt path and movie SHA-256;
- inspected frame times and pixel-derived claims;
- sensitive-content review result.

Complete when full decode passes, the inspected frames cover the journey, the
claims match the pixels, sensitive-content review passes, and the receipt binds
the movie to the exact candidate. The agent-written identity and claims are
evidence fields, not verifier conclusions.

## 5. Put the movie in the pull request

Use the host's PR-media uploader. On GitHub, use the built-in
`github-pr-media` skill to upload the binary to the repository's user
attachments before creating the PR, or to update an existing PR. A local path,
CI artifact that reviewers cannot open, or prose saying a movie exists does not
satisfy this gate.

Create a `## Walkthrough` section in the PR body containing:

- the hosted video URL on its own line so GitHub renders the player;
- the journey shown;
- the exact candidate commit;
- a link or stable path to the walkthrough receipt when available.

Open the PR page and confirm the movie player or link is present and reachable.
If later edits change the demonstrated journey, record and attach a successor
movie from the new frozen candidate. Documentation-only or test-only deltas
that cannot affect the journey may retain the original movie when the receipt
records why.

Complete when the PR body visibly contains a reachable video for the current
candidate and identifies what the reviewer should watch.

## Pitfalls

- **A polished failure.** The movie is evidence; it cannot hide a broken product
  path.
- **Video replacing proof.** Pixels do not prove every tool call, persistence
  boundary, or forbidden outcome. Keep the live-proof receipt.
- **Recording authentication.** Prepare protected input before capture.
- **Stale candidate.** A movie from another commit is not current evidence.
- **Unattached artifact.** The PR must contain the hosted movie, not only a
  filesystem path.

## Verification

The walkthrough is complete when the real frozen candidate passes rehearsal,
the final movie fully decodes and has been visually and sensitivity reviewed,
its receipt binds the artifact to the candidate, and the pull request's
`## Walkthrough` section contains the reachable movie and journey description.
