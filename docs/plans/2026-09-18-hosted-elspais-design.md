# Hosted elspais — Governing Design

**Date:** 2026-09-18
**Status:** Draft for review
**Scope:** A browser-reachable elspais for Anspar employees. Settled decisions only.

## What it is

A website. A user logs in, picks a repository from a list, and the interactive
elspais viewer opens in their browser against a daemon running on the server.
They read and edit requirements, create branches, push, and open pull requests.
They generate reports, adjust columns and filters, regenerate, and download the
result.

## Decisions

| Decision | Choice |
|----------|--------|
| Surface | Interactive viewer only |
| Users | Anspar employees, org-wide GitHub access; no public access |
| Login | A verified identity assertion from the access proxy |
| GitHub credentials | Per-user OAuth token, for clone, push and PR |
| Workspace | Private to one user; one project, one branch |
| Collaboration | Pushing and pulling branches |
| Undo | Session-limited, as it is today |
| Auto-save | Optional, time-based, to local disk |
| Push | User-initiated only |
| Store between sessions | The server's persistent disk |
| Isolation | One operating-system process per workspace |
| Deployment | A single small GCE VM in the existing GCP project |
| Packaging | A separate hub package in the Cure-HHT organization, depending on elspais |

## Workspaces

A workspace is a directory holding the project's repository plus its transitive
associates, resolved by `plan_federation()`, with `.elspais.local.toml`
generated to carry absolute paths. Clones come from a shared bare mirror. One
elspais daemon process serves one workspace, and the hub router maps
`/w/<workspace-id>/*` to it.

States are `creating`, `ready`, `idle`, `stopped`. A cold start of up to a
minute is acceptable; the user sees a preparing-workspace page until the viewer
is ready. Going idle stops the process and leaves the directory untouched.

A workspace is deleted only when its user asks, never automatically. If it
holds work that is not pushed, the confirmation names what will be lost — files
saved but not committed, or commits ahead of the remote — and the user decides.
Discarding work is a legitimate outcome; it is what keeps unwanted branches off
GitHub.

## Persistence

Auto-save writes pending mutations to disk through the existing
`persist_pending()` path. Nothing is committed and nothing is pushed
automatically, so the remote stays clean.

Because unpushed work lives only on the server's disk, that disk is snapshotted
on a schedule, and the landing page shows each workspace's state — unsaved,
saved but uncommitted, committed but unpushed, or clean — including the time of
its last automatic save.

## Git

Branch, commit, push, pull and checkout are the viewer's existing `/api/git/*`
routes. Pull remains fast-forward only; when a fast-forward is not possible the
viewer tells the user to push the branch and finish the work in a local
checkout. Pull-request creation is new.

## Deployment

A single small GCE VM in the existing GCP project, with an access proxy
(Cloudflare Access and Tunnel) in front of it. No load balancer, no public IP.
The hub router verifies the proxy's signed assertion rather than trusting a
header, holds the GitHub tokens, and supplies a short-lived credential for each
git operation rather than placing one in a workspace's environment. Each
workspace process carries a memory and CPU limit. Target cost is tens of
dollars a month.

The hub lives in the Cure-HHT organization, alongside the repositories it
serves and the existing Terraform that controls deployment.

## Changes in elspais

- Base-path mounting, so routes and the viewer's API base sit under `/w/<id>/`.
- Injected identity, so the comment author comes from the session rather than
  server-side git config.
- Session-based liveness: a held SSE stream counted through the existing
  `extra_liveness_fn` seam, which also replaces the 30-second poll.
- `POST /api/git/pr`.
- A report export route rendering markdown, CSV and PDF.
- An optional time-based auto-save.

## Out of scope

Static site generation. Shared workspaces. Undo that survives a restart.
Work-in-progress branches and automatic pushing. A GitHub App. Containers, a
warm pool, and a load balancer.
