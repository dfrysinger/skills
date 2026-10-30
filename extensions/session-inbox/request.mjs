#!/usr/bin/env node

// Preserve wake requests from watcher processes loaded before the
// session-inbox to session-control rename.
await import("../session-control/request.mjs");
