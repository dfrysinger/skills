---
name: macos-photos-library
description: Query a local macOS Photos library with osxphotos and import screenshots or image files into a Photos album using the local import helper. Use when you need to read Photos metadata, verify an album exists, or save app-test screenshots into Photos for iPhone/iCloud review.
platforms: [macos]
---

# macos-photos-library

Use `osxphotos` for read-only Photos library metadata and `copilot-photos-import` for writing screenshots or image files into Photos. Do not browse photo contents unless the user explicitly asks for a specific album, image, or metadata query.

## When to use

- The user wants app-test screenshots visible on their iPhone through iCloud Photos.
- The user asks whether an album exists, how many items it has, or whether an import worked.
- The user asks to import an existing PNG/JPEG into Photos.
- The user asks to capture the current screen and add it to a Photos album.

## Prerequisites

- macOS with Photos.app available.
- `osxphotos` installed and on `PATH`.
- Full Disk Access granted to the terminal app running the agent for `osxphotos` metadata queries.
- The bundled `scripts/copilot-photos-import` helper is on `PATH` (or invoked by its full path). One-time install:
  ```bash
  mkdir -p ~/.local/bin
  ln -sf "$(pwd)/scripts/copilot-photos-import" ~/.local/bin/copilot-photos-import
  ```
- Default import album: `Copilot App Tests` (override with `COPILOT_PHOTOS_ALBUM`).
- Default staging folder: `~/Pictures/Copilot-App-Test-Screenshots` (override with `COPILOT_PHOTOS_STAGING`).

## Quick start

```bash
# List albums and counts.
osxphotos albums

# Capture the current screen and import it to the default album.
copilot-photos-import

# Import existing images to the default album.
copilot-photos-import /path/to/screenshot.png /path/to/another.jpg

# Override album or staging folder for one run.
COPILOT_PHOTOS_ALBUM="Copilot App Tests" \
COPILOT_PHOTOS_STAGING="$HOME/Pictures/Copilot-App-Test-Screenshots" \
copilot-photos-import /path/to/screenshot.png
```

## Workflow

1. For read-only checks, use `osxphotos` metadata commands. Bound every call:
   on a large library, or when Photos holds the database lock, `osxphotos` runs
   for minutes with no output and looks like a hang.
   Stock macOS ships no `timeout`, so bound it with perl's alarm:
   ```bash
   bounded() { perl -e 'alarm shift; exec @ARGV' "$@"; }   # exit 142 on timeout
   bounded 60 osxphotos albums | grep -E '^Copilot App Tests'
   bounded 120 osxphotos query --album "Copilot App Tests" --json
   ```
   Exit 142 means the library is busy or large, not that the album is missing — quit Photos and retry once, then report the library as
   unavailable rather than concluding the album has no matches. Exit 1 with a
   permissions error means Full Disk Access is missing for the calling process;
   that needs the user, so ask rather than retrying.
2. For a new screenshot, run `copilot-photos-import` with no arguments. It captures the current screen to the staging folder, then imports it into the target album.
3. For generated or existing screenshots, pass the files explicitly:
   ```bash
   copilot-photos-import "$HOME/Pictures/Copilot-App-Test-Screenshots/example.png"
   ```
4. Confirm the import with `osxphotos albums` or a targeted `osxphotos query --album ...` check.

## Pitfalls

- `osxphotos import` may fail without Full Disk Access because it reads `Photos.sqlite` for duplicate detection. Prefer `copilot-photos-import` for writes because it uses Photos.app AppleScript import.
- Photos.app import can launch or activate Photos. That is expected.
- iCloud sync is asynchronous, so a successful import can take a moment to appear on the phone.
- Do not import black/blank diagnostic screenshots. View or otherwise verify screenshots before importing them.
- Avoid broad photo browsing. Use album-scoped metadata queries unless the user asks for wider inspection.

## Verification

```bash
osxphotos albums | grep -E '^Copilot App Tests'
```

The album count should increase after import, and Photos.app should contain the new media item in the target album.
