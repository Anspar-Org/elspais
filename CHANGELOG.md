# Changelog

All notable changes to elspais will be documented in this file.

## [Unreleased]

### Added

- **A daemon auto-started for a session records that session's identity and does not outlive it (REQ-o00074)** — a background daemon is spawned detached (`start_new_session=True`), so once it is running nothing in its process tree can say whose death should end it; the identity therefore has to be handed over at the moment of the spawn or it is unrecoverable. A daemon started implicitly on behalf of a session — any CLI command that auto-starts one — now records that session's PID as `spawner_pid` in `.elspais/daemon.json`, and a low-frequency watchdog inside the daemon shuts it down once that PID is gone. The identity is resolved from evidence available at spawn time only, in one order: the `ELSPAIS_SPAWNER_PID` environment variable (an explicit declaration by a session or IDE, and always decisive — a value that is not a usable PID yields no identity rather than falling through), then the nearest ancestor process named `claude` when `CLAUDECODE` is set, then the controlling-terminal session leader when it has a tty; the last two steps read `/proc` and a POSIX session id, so where those are unavailable only the environment variable can resolve. When none of those resolve, the daemon starts with no identity rather than a guessed one. Servers started deliberately — `elspais daemon restart`, a manual `elspais mcp serve`, the viewer — record no identity and keep their idle-timeout-only lifetime. The watchdog is independent of the idle timeout, so `cli_ttl = -1`, which disables the timeout entirely, no longer means a daemon can outlive every session that ever used it. With nothing pending, the daemon shuts down at its next check (the watchdog checks about once a minute). A daemon holding unsaved in-memory mutations instead writes a warning to `.elspais/daemon.log` naming how many mutations are actually pending — the true whole-log count, not a windowed one — and the deadline after which they go, waits a bounded five-minute grace period, then exits **without** saving and **discards** them; nothing is ever persisted on a caller's behalf, because a watchdog writing a caller's spec files unattended is a worse failure than the loss it would prevent. A daemon outlives its spawner precisely so a later session can adopt it, so a mutation applied after the session was seen gone counts as proof that a writer is present: the daemon keeps serving and the grace countdown restarts from that mutation. Only applied changes do this — reads and polling move nothing, so a client that merely queries the daemon cannot hold an orphan open. Save your pending work (`save_mutations` over MCP, Save in the viewer, or `elspais daemon restart --persist`) before your session ends rather than relying on the daemon to hold it. Documented under `elspais docs commands` and `elspais docs concurrency`.
- **`window.unloadWarningState()` — the viewer's navigation warning now explains itself (REQ-d00267-D)** — a tab that would not close was reported from the field, and no fix for it ships here: the cause is not established, and nothing in this change makes that tab close. Two explanations remain open — the `beforeunload` handler armed and its dialog never rendered, or the page never got as far as deciding — and they look identical from outside, so the next occurrence has until now been undiagnosable after the fact. The edit-mode viewer therefore reports the state behind the decision instead of leaving it to be inferred from what the page happens to be showing. `unloadWarningState()`, callable from the browser console, returns `willWarnOnClose`, `pendingCount`, `countKnown`, `countEstablishedAt` (ISO-8601 timestamp of the last pending-count outcome, success or failure, which the 30-second poll refreshes every cycle — so a stale timestamp means the page stopped asking), `countSource` (`'server'`, `'unreachable'`, or `null` before the first read), and `lastSeenTip`. It reports; it does not decide — the arming rule is unchanged. The `beforeunload` handler emits a `console.info` at the moment navigation is attempted saying whether it warned and why, naming the pending count when it warned and naming the count as unknown when it did not, so the presence or absence of that line distinguishes "the decision was reached" from "the page never got there". Edit mode prints a one-line hint on load pointing at the function. Backing this, `editState` gained `dirtyCountSource` and `dirtyCountAt`. Documented under `elspais docs concurrency`.

### Fixed

- **The spawner watchdog could discard an accepted mutation, misread an active writer as idle, and stop checking after one error (REQ-o00074)** -- four corrections to the shutdown path. The decision to terminate is now taken while holding the same lock every writer holds, and the pending state is re-read inside it: deciding from a snapshot taken outside the lock could terminate the daemon holding a mutation that had already been accepted and acknowledged to its writer. A change that lands between the two reads keeps the daemon alive. Writer activity is now tracked by a monotonic revision counter on the mutation log rather than by the log's tip identity, because an apply followed by an undo restores the previous tip exactly: a writer working in that pattern read as idle and could have its work discarded. A failed liveness check no longer kills the watchdog thread; it warns and retries at the next interval, so the daemon cannot silently become immortal. And a spawner PID of 1 or below is refused at the daemon as it already was at the resolver, since watching PID 1 would mean a daemon that never terminates.
- **An explicit reload was immediately followed by a redundant second rebuild (TOOL-11, REQ-p00004-O)** — the mtime snapshot the daemon compares against on every request lived on `AppState` and was refreshed only by the freshness path's own rebuild, so a reload reached any other way — `POST /api/reload`, `POST /api/revert`, MCP `refresh_graph`, or an MCP tool rebuilding after writing spec files — left the snapshot naming the files as they were *before* the reload. The very next request then saw those files as stale and rebuilt the whole graph again for nothing. Reloading is now one routine, `rebuild_shared_graph()` in `mcp/shared_state.py`, which publishes config, graph and `build_time` under the shared write lock and then runs the holder's new `post_rebuild_hooks` — where `AppState` registers its mtime re-snapshot, so every reload surface absorbs its own change instead of each caller remembering to. Nine hand-rolled rebuild-and-swap sites (only one of which was complete) now reach it, and the private `mcp/server.py::_refresh_graph` helper is deleted.
- **After an explicit reload, `daemon.json`'s `config_hash` stayed behind and the CLI restarted an already-fresh daemon (TOOL-11, REQ-p00004-O)** — only the automatic freshness rebuild synced the running daemon's recorded config fingerprint, so a reload through the viewer's `/api/reload` route or through MCP `refresh_graph` re-read `.elspais.toml` from disk without updating the fingerprint the CLI's staleness check reads. The next CLI invocation concluded the daemon had been started against a different configuration and tore down a server that was already serving exactly that configuration. The fingerprint sync is now a post-rebuild hook registered by the server that owns the record, so every rebuild that server performs — through any surface — brings it forward. It is deliberately registered rather than performed by the rebuild routine itself: a separate process rebuilding its own private graph in the same repository (a stdio MCP server, for instance) must never stamp the record as current, because a falsely-current fingerprint suppresses a restart that is genuinely needed, which is worse than the needless restart a stale one costs.
- **The daemon's automatic freshness check reported a failed rebuild as a successful one (TOOL-50, REQ-p00015-F)** — `AppState.ensure_fresh()` returned `True` whenever it decided the graph was stale, including when the rebuild it then attempted raised: the caller was told a rebuild had happened while the old graph was still the one being served, the phantom-success shape REQ-p00015-F exists to prevent. The same failure half-published its state, because `self.config` was swapped to the freshly read on-disk config *before* `build_graph()` ran — so a failed rebuild left the shared holder advertising a configuration that no answer it was serving had been computed from. `ensure_fresh()` now returns `True` only when the new graph is the one being served (a skipped rebuild and a failed one both return `False`), and `_rebuild()` builds config and graph into locals and publishes them together, so a failure leaves config, graph, `build_time` and the mtime snapshot all untouched and the next freshness check retries. The stderr warning naming the cause is unchanged.
- **`elspais pdf` discloses referenced content it cannot place instead of dropping it silently (REQ-p00080-H/I/J/K)** — every image (`.png/.jpg/.jpeg/.gif/.svg`) and Mermaid (`.mmd`) reference is resolved before pandoc runs: against the declaring spec file's own directory, then its owning repository's root, and — for images — the resource-path set (each federated repo's root and its `spec/` directory), which the assembler owns and hands to pandoc as `--resource-path` so both surfaces agree on what "not found" means. Mermaid sources are not searched on the resource path, since pandoc can place an image but cannot render a diagram. In a federated project each spec file resolves against **its own** repository, so an associate's figures come from the associate repo. A reference no repository can satisfy is reported on stderr naming the reference as written, the declaring spec file, the owning repository, every location searched, the cause, and the remedy; a Mermaid diagram whose source is found but cannot be rendered (`mmdc` missing or failing) is reported the same way. When anything was omitted the completion line is qualified — `PDF written to out.pdf (INCOMPLETE: 2 references omitted -- see warnings above)` — because a document missing content it was asked to carry is not an unqualified success. The exit code stays `0`: the document is still produced, and the degradation is disclosed rather than fatal. Pandoc's own warnings (e.g. `Could not fetch resource X: replacing image with description`) reach stderr regardless of pandoc's exit code, since it reports a dropped image and still exits `0`. The same disclosure now covers whole spec files: a single run from the root repository compiles every federated repository into one document, reading each spec file from **its own** repository (Topic Index entries for associate-owned requirements carry a `[<repo-name>]` prefix), and a spec file that cannot be found in its owning repository is reported as a `source-file` reference through that same stderr block, `INCOMPLETE:` completion line and exit code — naming the repository it was expected in and every location searched. Previously such a file contributed an empty section, so a misconfigured associate path could take an entire repository's requirements out of the document with no message at all. A configured associate that fails to load has no files to fail on -- its requirements never enter the graph -- so the absent repository is itself reported, by name and with the path that was tried, and counted toward `INCOMPLETE:`. Resources pandoc could not fetch (media types outside the compiler's reference grammar such as `.webp`, `.pdf` and `.eps`, and reference-style `![alt][key]` links, which pandoc resolves through the resource path) are folded into the same report and the same count, deduplicated against the compiler's own findings so a single missing file counts once. Percent-encoded references (`img/with%20space.png`) resolve correctly and are never reported: every existence check uses the decoded form, which is what pandoc resolves against. References inside fenced code blocks (opened by three backticks or three tildes) are left completely alone -- neither rewritten nor reported -- so a Markdown code sample survives verbatim into the PDF; indented (four-space or tab) code blocks carry the same exemption, recognised as Markdown defines them -- an indented line following a blank line that does not continue a paragraph -- while indented continuation under a list item stays live prose. A code fence opened and never closed makes the rest of the file read as code, so requirement structure after it is not rendered as structure; that is reported as a `code-fence` reference naming the spec file. A missing absolute image path is reported by name before compilation and then fails the run (exit non-zero); an absolute path that exists is used as-is. A successful run prints only pandoc's own `[WARNING]`/`[ERROR]` lines, keeping a dropped-image line from being buried in the TeX engine's font chatter; a failed run prints the full engine output, where the cause usually lives. **Known limitation**: raw HTML image tags (`<img src="...">`) in spec files are not supported -- pandoc drops them silently into LaTeX and neither pandoc nor the compiler can report the loss, so authors must use Markdown image syntax. New docs topic: `elspais docs pdf`.
- **A single broken viewer endpoint pinned the unsaved badge to `?` indefinitely, and two destructive operations read that unknown count as zero (REQ-d00267-A/E)** — the 30-second poll called only `/api/check-freshness`, and marked the pending count unknown when that failed. So a freshness endpoint failing while `/api/dirty` answered perfectly left the badge stuck on `?` and the before-navigation warning disarmed for as long as the one broken endpoint stayed broken, with no path back. The poll now probes `/api/dirty` directly every cycle and records the outcome either way, so only the count endpoint speaks for the count and any usable answer restores it; a freshness failure no longer touches the count. That probe deliberately does not adopt the mutation-log tip, on success or failure — doing so would mark another writer's mutations as seen every cycle and retire the "Another writer changed the graph" banner permanently. **Behaviour change worth knowing about:** because the probe runs whether or not you touch the page, pending changes arriving through the shared daemon from another writer — an MCP agent, a second viewer — now appear in an idle tab's badge within 30 seconds and arm its before-navigation warning; a tab you have not touched can start warning you before it closes. This follows from the badge being server-truth rather than a tally of what this page did, but it is a real departure from a badge that moved only when this page acted. Separately, "Switch branch" and "Checkpoint" fell through their `count > 0` guards whenever the count was `null`, because `null > 0` is false — so a branch switch could strand pending changes on the branch being left, and a checkpoint could commit around them. Both now refuse with an error modal while the count is unknown, rather than prompting: a prompt's only remedy is to save first, and saving needs the same server whose silence caused the uncertainty. Note the deliberate opposite polarity from the navigation warning, which stays permissive under the same uncertainty because closing a tab destroys nothing. Save/Revert/Refresh need no such modal — each carries a freshly read mutation-log tip that degrades to `""` on a failed read, which the server rejects with a 409 if anything is actually pending. Finally, an `/api/dirty` answer whose `mutation_count` is missing or not a number is now treated as unknown instead of coerced to zero, a failed mutation response re-probes the count instead of assuming the server is gone (a null response also covers a reachable server that answered with an error), and the badge tooltip reads "unreachable or not answering" to match.

- **The viewer's unsaved-changes badge froze at a stale count whenever the server could not be reached, and the navigation warning stayed armed on it forever (REQ-d00267)** — the pending mutations the badge counts live in the viewer server process, not in the browser page, so a failed `/api/dirty` fetch left the page with no way to recompute the number; it returned early, and the badge went on presenting the last count as current fact, asserting unsaved work that might exist in no process. The `beforeunload` warning read that badge's text, so it stayed armed on the stale claim and an operator could be left unable to leave the page. The badge now distinguishes three states instead of two: nothing pending (hidden), N pending (`N`, red), and count unknown (`?`, amber, tooltip naming the last confirmed count). Zeroing on a failed fetch is deliberately not done — that would hide genuinely pending work behind a momentary blip — and any answer from the server supersedes the unknown presentation. The 30-second poll is the page's only heartbeat for the count — `refreshDirtyCount()` otherwise runs at load and after mutations, so an idle page whose server died would never notice. The navigation warning now arms only on a count the server actually reported, read from page state rather than parsed from badge text: closing the tab destroys nothing, so obstructing an exit over an unverifiable claim buys no safety. A failed read does not advance the mutation-log tip the page has seen, and Save/Undo keep their last enabled state rather than claiming there is nothing to save.
- **The daemon's `/mcp` endpoint rejected every MCP session (TOOL-49, REQ-o00062-Q)** — two stacked defects made the daemon's HTTP MCP surface dead on arrival: FastMCP's internal default path stacked under the outer mount, so the endpoint answered at `/mcp/mcp` while the documented `/mcp` returned 404; and the mounted sub-app's lifespan was never run by Starlette, so the session manager was uninitialized and terminated every `initialize` even at the buried path. Since the daemon is the shared-graph process the whole concurrency contract protects, agents could not actually reach it over MCP — the cross-writer guarantee was unreachable in real deployment. The mount now serves at `/mcp` with its lifespan wired into the outer app, a mount that cannot be built is reported to stderr instead of silently omitted, and an e2e suite drives a real `mcp` client against a live daemon: initialize + tools/list at the documented endpoint, an MCP-HTTP mutation visible in the viewer's `/api/dirty`, a stale viewer write rejected 409 against the agent's token, and two concurrent HTTP sessions playing out the conflict-and-reconcile story.
- **The viewer's three HTTP history routes were unguarded — the GUI Save button could persist work its user had never seen (CUR-1829, REQ-o00062-N)** — `/api/save`, `/api/revert`, and `/api/reload` took no token at all while the equivalent MCP tools already required the mutation-log tip, so a viewer user clicking Save would persist (or Revert/Refresh would discard) every writer's pending mutations sight unseen — including an agent's in-flight edits arriving through the same daemon. All three routes now require `if_tip_mutation_id` in the JSON body (`""` = nothing pending) and reject a stale or missing tip with HTTP 409 whose body is identical to the MCP `mutation_log_conflict` rejection. The viewer JS threads the tip automatically (reading `/api/dirty` before each history call), and the daemon's save helper sends it, so interactive use is unchanged — only a genuinely concurrent unseen mutation now blocks.
- **`restore_from_safety_branch` overwrote files and discarded pending work with no check (CUR-1829, REQ-o00062-N)** — the MCP restore tool took only a branch name, so a caller could roll spec files back over a mutation set it had never seen. It now requires `if_tip_mutation_id` with the same semantics as the other history-level tools: a mismatch returns `mutation_log_conflict` with `current_tip` and `unseen`.
- **The viewer's auto-refresh silently discarded pending mutations (CUR-1829, REQ-o00062-N)** — the mtime-triggered rebuild (`AppState.maybe_refresh`) rebuilt the graph from disk whenever any spec file's mtime moved, throwing away every writer's unsaved in-memory mutations with no guard — the exact loss the mutation-history guards exist to prevent, reachable by merely touching a file while edits were pending. The auto-refresh now never rebuilds over pending mutations; discarding requires an explicit, tip-guarded revert/reload/forced-refresh. Rebuild failures in the same path were also silently swallowed (`except Exception: pass`); they now print a visible warning while keeping the previous graph.
- **Journey mutations left the journey's cached body stale — silent data loss and a frozen version token over MCP (CUR-1829, REQ-d00131-L)** — a journey renders (and derives its concurrency version) from its cached `body` field, but title updates, renames, VALIDATES edge add/delete/change-kind/change-targets, and `fix_broken_reference` never folded the new state back into that cache: the mutation reported success while the render — and the next save — silently kept the pre-mutation text, and the version token never moved, so other clients' optimistic locks could not even detect the change. Every such mutation now reconciles the journey's cached body (and moves the token); undo restores the journey body byte-exactly from a snapshot rather than re-reconstructing (forward reconciliation canonicalizes, so reconstruction would not round-trip the original text). A third defect in the same path: body reconstruction rendered each VALIDATES edge as a bare whole-requirement reference, so `Validates: REQ-x-A+B` assertion targets were lost (degrading to duplicate whole-req refs); reconstruction now aggregates assertion targets per source, mirroring `_derive_refs_for_edge_kind` in `graph/render.py`.
- **Undoing `delete_requirement` restored a detached node that the next save would silently drop (CUR-1829, REQ-o00062-P)** — the undo put the requirement back in the graph index but reattached none of its edges, so it came back with no FILE parent (rendering into no file), no traceability edges in either direction, and its assertion children still deleted. The undo now restores full structural attachment — file membership, both edge directions with their metadata and assertion targets, assertion children, orphan bookkeeping, and root membership — the same contract journey deletion already honored. A regression test asserts the file renders back byte-identically after delete + undo.
- **Deletion tools returned no resulting version, forcing a re-read mid-sequence (CUR-1829, REQ-o00062-K revised)** — a deletion's target no longer exists, so the tools returned nothing to thread into the next mutation, breaking the one-read-per-sequence contract. Per the revised assertion, a deletion now reports the version of the surviving container that absorbed the change: `mutate_delete_assertion` and `mutate_delete_remainder` return the owning requirement's resulting `version`; `mutate_delete_requirement` returns the containing FILE's.
- **`elspais associate --all` crashed when any sibling directory carried a stale or invalid `.elspais.toml` (CUR-1829, REQ-d00202-I)** — `discover_associate_from_path()` called `load_config()` with no error handling, so one unparseable sibling config (unknown keys, missing namespace, TOML syntax error) aborted the entire scan. The scan now completes: such candidates are skipped with a printed reason (`Skipping: Cannot load associate config in <path>: <reason>`) and the command exits 0. Sibling directories without a `.elspais.toml` remain silently ignored, as before.
- **`elspais fix` claimed to fix associate-owned requirements it would never write (CUR-1829, REQ-d00253-F)** — on a federated project with `federation.write_associates = false`, the report printed `Fixing <id>` (or `Would fix <id>` in dry-run) for requirements in associate repos even though `render_save()` skips their files. Those lines now read `[skipping] <id>: <detail> (associate-owned; write_associates=false)`, using the same ownership resolution the writer uses, so the log never claims an associate fix was applied.
- **Deleting a node's last `Implements:`/`Refines:` edge left the rendered reference — and the concurrency version token — unchanged (CUR-1829, REQ-d00132-F/G)** — `_derive_refs_for_edge_kind` fell back to the stored parsed refs whenever no matching edges existed, resurrecting a deleted reference; the same conditional silently dropped an author's broken (unresolved) reference whenever it coexisted with a valid one, so a rewrite would delete the typo'd line. Rendered reference lists are now the union of live graph edges and unresolved leftovers: deleting the last edge removes the reference (and moves `node_version()`), while broken references always survive a rewrite, alone or alongside valid ones.
- **Renames and deletes desynced broken references from the rendered text (CUR-1829, REQ-d00132-G)** — found by the post-implementation review of the fix above: `rename_node` retargeted the broken-reference report but not the stored leftover the render uses (so the report said the new ID while the file kept the old one), missed assertion-suffixed broken targets (`REQ-x-Z` when renaming `REQ-x`), and silently dropped the `diagnostic`/`presumed_foreign` fields when rebuilding entries; undoing a rename never reversed the retargeting at all; and `delete_requirement` left broken-reference entries sourced from the deleted node in the report. Retargeting now lives in one helper that syncs report and leftovers together (including suffixed targets, preserving all fields), is replayed in reverse on undo, and deletion retires the node's broken references with undo restoring them.
- **The browser test tier's dependency was declared nowhere (CUR-1829)** — `playwright` and `pytest-playwright` appeared in no extra, so a fresh virtualenv silently **deselected all 13 `@pytest.mark.browser` tests and still reported green**. A green run was therefore not evidence the tier had run. Added a `browser` extra (`pip install -e ".[browser]"`, plus `playwright install chromium` once) and documented in CLAUDE.md that `0 selected`/`skipped` means the tier did not run.
- **`mutate_add_remainder` and `mutate_delete_remainder` raised `AttributeError` and could never succeed (CUR-1829)** — both called `graph.add_remainder(...)` / `graph.delete_remainder(...)`, which existed on `TraceGraphBuilder` but were never delegated on `FederatedGraph`. Every call failed, over MCP and over HTTP (`/api/mutate/remainder/delete` returned 500). Both delegations are added.
- **`/api/dirty` reported at most 1 pending mutation (CUR-1829)** — it computed the count from a `limit=1` log query, so any number of pending mutations reported as `1`. It now reports the true count and also returns `tip`, the mutation-log tip that the history-level guards require callers to send.
- **`/api/mutate/requirement/add` never validated `file_id` (CUR-1829)** — an unknown destination file returned 200 and created the requirement unparented. The destination is now resolved before the mutation.
- **`/api/mutate/move-to-file` created the destination file before authorizing the move (CUR-1829)** — a first move into a new file was impossible to authorize (the caller cannot know the version of a node that did not exist when it made the request), and the resulting rejection left an empty spec file stranded on disk. All three guards now run before anything is created, and a destination created by the move itself requires no token, since it has no prior state to clobber.
- **Undoing a journey deletion left the journey orphaned, losing it on the next save (CUR-1829, REQ-o00062-P)** — `_undo_delete_journey` restored the node to the graph index but reattached none of its edges, so the journey came back with no FILE parent and rendered into no file. The undo reported success; the next `render_save()` would silently drop the journey. `delete_journey` now captures both edge directions with their metadata and assertion targets, and undo replays them along with root membership. A second defect in the same path: `assertion_targets` is a first-class `Edge` attribute rather than edge metadata, so `Validates: REQ-x-A+B` was silently degrading to blanket whole-requirement validation on undo — which also shifted the computed version of untouched requirements, breaking optimistic locks held by other clients across a supposed no-op. Both are covered by regression tests that fail against the previous behavior, including one asserting the file renders back byte-identically.

### Changed

- **`POST /api/revert` now re-reads configuration from disk (TOOL-11, REQ-p00004-O)** — revert rebuilt the graph from the config object the server was holding, so a revert issued after `.elspais.toml` (or `.elspais.local.toml`, or an environment overlay) changed produced a graph built to the old configuration while claiming to have reverted "from disk". Revert reaches the same rebuild routine as reload and therefore re-reads config exactly as reload does. Reverting no longer preserves a superseded configuration; if you want the old one back, change the file.
- **A revert and an MCP refresh now reload the comment layer with the graph (TOOL-11)** — `load_comments()` was called by the automatic freshness rebuild and by `/api/reload`, but not by `/api/revert` or by MCP `refresh_graph`. Either of those therefore swapped in a graph with an empty annotation layer, so `/api/comments` went blank for the viewer until some later rebuild happened to take the path that loads them. All rebuilds now load comments, because there is only one rebuild.
- **MCP `refresh_graph` on an unparseable `.elspais.toml` now keeps the graph it was serving (TOOL-11, REQ-p00004-O)** — a config parse error made the tool swap an empty graph into the shared holder and return `CONFIG ERROR: ...`, so a typo in a config file silently emptied the live graph for every reader on the daemon, the viewer included, and only a corrected file plus another refresh brought it back. The failure is now reported without publishing anything: `success` is `False`, `message` carries the same `CONFIG ERROR: ...` text, and the previously served graph stays live. The tool's signature is unchanged.
- **BREAKING: `/api/save`, `/api/revert`, `/api/reload`, and `restore_from_safety_branch` now require the mutation-log tip (CUR-1829, REQ-o00062-N)** — the viewer's three HTTP history routes take `if_tip_mutation_id` in the JSON body, and the MCP restore tool takes it as a required parameter. `""` is the wire spelling of "I believe nothing is pending" — with no mutations pending it succeeds; with any pending it is an ordinary conflict (HTTP 409 / `mutation_log_conflict`, identical body on both surfaces, carrying `current_tip` and `unseen`). An absent JSON body counts as `""`. **Migration**: read `/api/dirty`'s `tip` (or `get_mutation_log()`'s last entry id) and send it; the viewer's own JS and the daemon's save helper already do this automatically.
- **MCP gains the viewer's two remaining placement capabilities (CUR-1829, REQ-o00062-O)** — `mutate_add_requirement` accepts an optional `file_id` placing the new requirement into a chosen file (when given, `if_version` guards that FILE's token, since placement changes the file's composition; `parent_id` remains the guarded node otherwise). `mutate_move_node_to_file` now creates a missing destination file exactly like the HTTP route: the path is validated against the scanning config, every guard runs before anything touches disk, and the brand-new destination requires `if_target_version=""` since it has no prior state to clobber. The new-spec-path validation now has a single home — `utilities/spec_paths.py::validate_new_spec_path` — shared by both surfaces so they accept and reject identically.
- **MCP/HTTP mutation parity (CUR-1829, REQ-o00062-O)** — five mutations were reachable through the viewer's HTTP interface but not through MCP: the `**Template**` toggle and the four journey mutations. They existed only as module-level helpers that nothing ever registered as tools. They are now MCP tools — `mutate_set_stereotype`, `mutate_update_journey_field`, `mutate_journey_section`, `mutate_add_journey`, `mutate_delete_journey` — and, being registered after the concurrency contract landed, carry the required `if_version` from birth rather than being retrofitted. `mutate_add_journey` guards its parent FILE, since the journey it creates has no prior version. A parity test derives the route list from `server/app.py` at test time, so a route added without a matching tool fails rather than drifting. The claim is deliberately one-way: MCP remains a superset (`apply_link`, `rename_node`, `change_edge_kind`, `save_mutations` and others have no HTTP equivalent).
- **BREAKING: the viewer's HTTP mutation routes now require the same tokens as MCP (CUR-1829, REQ-o00062-O)** — all 19 `/api/mutate/*` routes take `if_version` (or `if_mutation_id` for `/api/mutate/undo`, or the three tokens for `/api/mutate/move-to-file`), and a stale or missing token returns **HTTP 409** whose JSON body is byte-identical to the MCP rejection — the routes call the same `_guard_version`/`_guard_mutation_tip` helpers rather than reimplementing the check, and a test asserts full-dict equality between the two surfaces so a hand-rolled body cannot pass. An unknown node returns **404** with `code: "node_not_found"`. Successful mutations return the new `version`. The browser client sends tokens, threads the returned one forward, and on 409 re-reads the card from the rejection's `current_state` instead of retrying blind — a retry would re-apply an edit composed against text that has since changed. This closes the actual multi-writer hole: the GUI and an agent share one daemon, and until now either could silently overwrite the other.
- **Read surfaces now report version tokens (CUR-1829, REQ-o00060-G)** — `get_requirement`, `get_node`, and `get_subtree` (structured `flat`/`nested` formats) carry a `version` for every node returned, so a caller never has to fetch a node twice to be allowed to change it. Requirement payloads additionally carry `file_version`, the containing FILE's token, so `mutate_move_node_to_file`'s `if_source_file_version` needs no extra read; it is `None` for INSTANCE and unlinked nodes rather than absent or raising. Sub-node reads resolve to the owning requirement's version, matching the rule the mutation guards use. New `get_versions(node_ids)` returns tokens without content for cheap refresh, resolving sub-nodes the same way and **omitting** unknown IDs rather than raising, so one renamed or deleted ID cannot defeat a refresh of the rest. The `markdown` subtree format is unchanged — it is rendered prose and cannot carry per-node tokens without corrupting the rendering.
- **BREAKING: undo, forced refresh, and save now require the mutation-log tip (CUR-1829, REQ-o00062-N)** — `undo_last_mutation(if_mutation_id)`, `undo_to_mutation(mutation_id, if_tip_mutation_id)`, `save_mutations(if_tip_mutation_id, ...)` and `refresh_graph(force=True, if_tip_mutation_id=...)` require the caller to name the end of the mutation history it believes it is acting on. These four affect **every** writer's pending work, not just the caller's: you cannot now unwind, discard, or persist a mutation set you have never seen. A mismatch returns `{"code": "mutation_log_conflict", ...}` carrying `current_tip` and `unseen` — the entries recorded since your position, so you can see exactly what you were about to act on. `""` is the wire spelling of "I believe nothing is pending", so an omitted tip is an ordinary conflict rather than a separate error kind; a tip the log never contained is treated as a position before the start, reporting everything pending, since under-reporting what is about to be discarded is the failure this prevents. `refresh_graph`'s tip is required only for `force=True`; the non-force pending-mutations refusal is unchanged. `save_mutations` checks the tip **before** creating any safety branch, so a rejected save leaves no branch behind and no bytes changed. This also closes a live gap: `refresh_graph(force=True)` previously discarded all pending mutations with no check whatsoever.
- **BREAKING: edge, creation, file, and disk-backed mutations now require `if_version` (CUR-1829, REQ-o00062-M)** — completes the guard across every mutation tool. **Edge mutations** (`mutate_add_edge`, `mutate_change_edge_kind`, `mutate_delete_edge`, `mutate_change_edge_targets`, `mutate_fix_broken_reference`) guard the **source only**: only the source's rendered `Implements:`/`Refines:` line changes, so requiring a target token would reject writes that cannot clobber anything. Note `mutate_add_edge`'s parameter order changed — `if_version` precedes `assertion_targets`, since a required parameter cannot follow a defaulted one. **Creation mutations** guard the parent (`mutate_add_assertion`, `mutate_add_remainder` on `req_id`); `mutate_add_requirement` takes `if_version` as optional and enforces it only when `parent_id` is supplied, because a parentless creation has nothing to clobber. **File mutations**: `mutate_rename_file` guards the FILE; `mutate_move_node_to_file` now requires three tokens — `if_version`, `if_source_file_version`, `if_target_version` — because a move changes the node, the file it leaves, and the file it joins, and its placement in the destination depends on what else arrived there. **Disk-backed tools** (`apply_link`, `change_reference_type`, `move_requirement`) are guarded too, and the guard matters more there: they write to disk before rebuilding the graph, so a lost update is already persisted by the time the rebuild happens. `apply_link` guards the FILE it edits rather than the requirement, whose rendered form does not change. A coverage test enumerates every registered `mutate_*` tool and asserts it accepts `if_version`, so a future unguarded tool fails loudly.
- **BREAKING: content and metadata mutation tools now require `if_version` (CUR-1829, REQ-o00062-I/J/K/L)** — `mutate_rename_node`, `mutate_update_title`, `mutate_change_status`, `mutate_delete_requirement`, `mutate_update_assertion`, `mutate_delete_assertion`, `mutate_rename_assertion`, `mutate_update_remainder`, and `mutate_delete_remainder` all take a required `if_version` argument: the version of the target from your last read. If it does not match current state the mutation is refused with `{"code": "version_conflict", ...}` carrying `current_version` and `current_state` (the existing `get_requirement`/`get_node` payload), so the caller can reconcile and retry in one round-trip. A mutation naming a node that does not exist returns `{"code": "node_not_found"}` instead, since retrying cannot resolve that. **Assertion and remainder mutations take the PARENT REQUIREMENT's version**, because sub-nodes carry the version of the authoring unit that renders them. Every successful mutation now also returns `version` — thread it into your next call and a sequence of edits costs one read at the start rather than one per mutation. **Migration**: read the node first and pass the `version` you were given; there is no deprecation window and no flag to disable the guard, because an unguarded mutation is the blind write this exists to prevent. Rationale: a single daemon serves MCP agents and the viewer simultaneously, and nothing else could detect two clients reading the same state before both writing it.
- **Coverage headlines move to the generous footing; vocabulary retires "Validated" (CUR-1568, REQ-d00258)** — `elspais trace`, `elspais summary`, MCP `get_project_summary`, and the HTML viewer now headline coverage on the generous footing (direct + indirect evidence), appending a `~` marker to any text-surface count whose evidence is not fully direct (REQ-d00069-L/REQ-d00258-A). The five coverage display terms across every surface are now exactly **Implemented / Tested / Passing / UAT Covered / UAT Passed** — "Validated" no longer denotes test coverage anywhere (assertion badges, `elspais health` dimension labels, the Legend's "Result Status" button group, and `help.toml` wording were all swept). **Passing is the union of result-verified and line-coverage-credited evidence**: `tested_and_passing()` (`graph/metrics.py`) merges the `verified` and `lcov_tested` dimensions (max per-assertion fraction, OR'd `has_failures`), and the viewer's "Passing" badge/bucket now reads from that union instead of the raw `verified` dimension, so a requirement covered only via line coverage (no `Verifies:` reference at all) correctly shows a full "Passing" badge rather than degrading to partial. `elspais summary`'s "External integrations" table now earns the "Passing" header (previously "verified (no lcov)") — `integrates_rollup()`/`integrates_by_associate()` (`graph/metrics.py`) now fold the library node's `tested_and_passing()` union across federation instead of the raw `verified` dimension, so a library requirement whose only evidence is line-coverage credit (e.g. an aggregate-tooling repo with no `Verifies:`-based results) correctly propagates as passing coverage to integrating consumers (REQ-d00252-D/F, REQ-d00258-B). The `IntegratesRollup`/`AssociateIntegration` field names (`verified_covered`/`verified_total`) are kept unchanged for MCP/GUI wire compatibility, but their semantics changed accordingly — see the updated docstrings in `graph/metrics.py`. Both rollups also gain an additive `has_failures` flag (OR'd from the union): the union's covered count uses a per-assertion max, so a library assertion with a failing `Verifies:` result but full lcov credit still reads as covered — the flag is the only red signal and is surfaced everywhere the figures are (summary's integrations table marks failing rows with `!` plus a footnote, the MCP `integrates_rollup` payload carries `has_failures`, and the viewer's "Integrated coverage" row shows a FAILING badge). The CLI summary, MCP project summary, and viewer now derive their statistics from one shared aggregation module (`graph/aggregation.py`) so identical questions get identical answers (REQ-d00258-C); the viewer header's title counts (PRD/OPS/DEV/total) now count only coverage-included requirements, matching CLI/MCP (previously included Draft and other coverage-excluded statuses).
- **Assertion separator / multi-separator combinations now parse in the reference grammar (CUR-1568)** — `Implements:`/`Refines:` references combining the assertion-letter separator and the multi-assertion separator (e.g. `REQ-p00001-A+B, REQ-p00001-C`) previously failed to parse in some combinations; the reference grammar now handles them correctly.
- **CI: Slack notifications use shared `slack-notify` action with bookmarks** (CUR-1360) — release-success messages from `publish-pypi.yml` and the channel-test message from `test-slack.yml` now route through `Cure-HHT/hht_workflows/.github/actions/slack-notify`, driven by a new `.github/slack-channels.yml` (channel-bound events route to `#dev`). The success notification upserts a channel bookmark titled "elspais latest release" pointing at the new message's permalink (replaces the legacy "pin the deploy message" pattern). Failure notifications DM the PR author via `slackapi/slack-github-action` (with a `::warning::` and no fallback if the author can't be resolved on Slack) — the shared action only routes named channels, so DMs stay on the direct slackapi call. The dispatchable DM test in `test-slack.yml` is likewise retained on `slackapi/slack-github-action`. Removes dependency on `SLACK_CHANNEL_DEV` / `SLACK_CHANNEL_DEVOPS` / `SLACK_CHANNEL_INCIDENTS` channel-ID secrets. Requires bot scopes `channels:read`, `channels:join`, `bookmarks:read`, `bookmarks:write` in addition to existing `chat:write` (channels:read/join + bookmarks needed only on the success path).
- **Test-target `match` value `"precise"` renamed to `"source"`** (CUR-1533) — the per-test attribution mode is now `match = "source"` (it falls back to file granularity for shared/parameterized suites, so `"precise"` overclaimed). `match = "precise"` is no longer accepted (`match must be "source" or "aggregate"`). **Migration**: change `match = "precise"` → `match = "source"` in your `[[scanning.test.targets]]` entries; `match = "aggregate"` is unchanged.
- **BREAKING: `[project].name` is now required in `.elspais.toml`** (CUR-1357) — `load_config()` now rejects configs that omit `[project].name` or leave it blank. **Migration**: run `elspais init` to generate a starter config, or add `name = "..."` under `[project]` in your existing `.elspais.toml`. `elspais init` auto-derives the name from the user's invocation directory and always emits a non-empty value.
- **BREAKING: `Satisfies:` now requires `**Template**` on the target** (CUR-1353) — a `Satisfies: X` declaration where `X` is not marked with `**Template**` on its metadata line now emits a typed broken-reference diagnostic and fails `elspais checks`. Previously any requirement could be a `Satisfies:` target (the pre-CUR-1353 auto-mark fallback silently stereotyped any satisfied target as a template). **Migration**: add `**Template**` to the pipe-separated metadata line of every requirement used as a `Satisfies:` target. The diagnostic message names the missing flag verbatim: *"X is not marked **Template**; mark X with **Template** if it's intended to be satisfiable."* See REQ-p00014 for the full validation matrix.
- **TermsConfig restructured** — flat severity fields (`duplicate_severity`, `undefined_severity`, `unmarked_severity`) replaced with nested `[terms.severity]` sub-table containing 6 fields: `duplicate`, `undefined`, `unmarked`, `unused`, `bad_definition`, `collection_empty`. New top-level fields: `markup_styles` (which markdown delimiters count as marked) and `exclude_files` (glob patterns to skip during scanning).
- **no_traceability_severity** — new `[rules.format]` option to configure severity for code/test files lacking traceability markers (default: None, uses check default of "warning").
- **Config migration v3→v4** — automatic migration of flat `duplicate_severity`/`undefined_severity`/`unmarked_severity` under `[terms]` to nested `[terms.severity]` sub-table. `CURRENT_CONFIG_VERSION` bumped to 4.
- **`SATISFIES_FIELD` PIPE-stop semantics** — lexer regex tightened from `[^\n]+` to `[^|\n]+` so `**Satisfies**: X | **Status**: Y` no longer greedy-consumes subsequent piped fields. The standalone `satisfies_line` grammar rule and transformer handler were removed; `Satisfies` is now a regular `_field` extracted via `_extract_metadata` alongside Level/Status/Implements/Refines.

### Added

- **Node version tokens for concurrency control (CUR-1829, REQ-d00131-L)** — every graph node now has a 16-char `version` derived from its rendered text plus its outgoing traceability references (`node_version()` in `graph/render.py`; digest primitive `compute_version_hash()` in `utilities/hasher.py`). The version changes when, and only when, the node's on-disk representation would change — unlike the content hash, which covers body and assertions only and is unmoved by title, status, rename, and edge changes. Because it is content-derived rather than a counter, rebuilding from unchanged content yields unchanged versions, so a routine `refresh_graph` does not invalidate versions held by clients. ASSERTION and REMAINDER nodes resolve to the version of the REQUIREMENT/USER_JOURNEY that renders them; CODE/TEST use `raw_text` (never their ID, which embeds an absolute path); FILE nodes use path plus ordered child IDs — identity and composition only, so editing prose inside one requirement does not invalidate a pending file-level operation. This ships the primitive only; the mutation preconditions that consume it follow in the same ticket.

- **`elspais docs concurrency` — agent-facing documentation for the optimistic-concurrency protocol (CUR-1829)** — a new docs topic covering the full read → mutate → thread-the-returned-token protocol: where version tokens come from on every read surface, the reconcile-on-`version_conflict` rule (re-check intent against `current_state`; never retry blind with the token from the error), which token guards which node (edge mutations guard the source, creation guards the parent, moves take three tokens), the mutation-log tip and the empty-tip convention, and HTTP 409 parity on the viewer routes. Registered in `TOPIC_ORDER` (`docs_loader.py`) and the `DOCS_TOPICS` CLI literal (`args.py`), so it is served by `elspais docs` and the MCP `docs` tool. The MCP surface teaches the same protocol everywhere agents learn: `agent_instructions()` now always returns a built-in `concurrency_protocol` section, `faq("concurrency")` answers the common conflict questions (and the stale persist-changes answer now names the required tips), the server's startup instructions gained an "Optimistic Concurrency" section with corrected tool signatures, and `docs/cli/mcp.md` documents the token fields and a Concurrency Control overview.

- **`elspais docs authoring` — requirement authoring decision guide** (CUR-1643) — a new tool-generic docs topic covering the *judgment* of authoring (as opposed to the grammar in `format`/`hierarchy`/`assertions`): when to mint a new requirement, add an assertion to an existing one, or cite a parent, and at what level. Introduces the two-axis model (level/audience vs. verifiability distance), an ordered decision funnel with an invariant/reimplementation test and an arbitrariness/blank-fill test, the "why" stopping rule (Rationale vs. promoting a shared anchor), and the rule that tests attach to leaves. Schema-agnostic: PRD/OPS/DEV/etc. appear only as a configurable exemplar. Registered in `TOPIC_ORDER` (`docs_loader.py`) and the `DOCS_TOPICS` CLI literal (`args.py`), so it is served by `elspais docs` and the MCP docs surface. `hierarchy` gains a complementary "Levels Are Configurable" note clarifying that the built-in PRD/OPS/DEV set is a default exemplar and that leaf-ness is independent of level.

- **Viewer severity colors via theme catalog + Legend, severity-aware coverage filter with a Failing option (CUR-1568, REQ-d00258-D/E)** — per-dimension coverage tiers resolve to colors through the theme catalog by severity name (tier → configured severity → named catalog entry) instead of hard-coded color values, and the resulting severity/tier states appear in the viewer Legend. The coverage filter buckets requirements by tier semantics (full = any full tier, partial, none) plus a dedicated "Failing" overlay bucket, rather than matching on color strings, and `combined_bucket` derives from the worst configured severity rather than the raw tier so info/ok-severity gaps (e.g. UAT dimensions under the default config) no longer drag a fully-covered requirement's bucket down to "partial".
- **Gap surfaces annotate partially-conducted assertions (CUR-1568)** — `elspais gaps` and related coverage-gap surfaces now show the fractional credit an assertion has already received via REFINES conduction (REQ-d00069-J), instead of presenting a partially-covered assertion identically to an entirely uncovered one.
- **Python per-test line attribution via `coverage.py` contexts (CUR-1568)** — when running the Python test suite with `coverage.py` dynamic contexts enabled, `lcov_tested` credit is now attributed per test (which lines each individual test executed) rather than per file, so line-coverage credit for an assertion reflects the specific test(s) that exercise it. Note: the coverage.py JSON report with `show_contexts` grows impractically large on big suites (9+ GB for elspais's own ~4600-test suite, with graph builds peaking at ~22 GB RSS), so ingestion instead reads contexts directly from the compact `.coverage` SQLite database via coverage.py's public API (new `CoverageSqliteParser`, format detected by SQLite magic bytes; requires the new `elspais[coverage]` extra, degrading gracefully with `code_tested.direct` staying `0` and a single install-hint warning when it's absent). elspais's own dogfood config (`.elspais.toml`) now points its `elspais-unit` target's `coverage` key at `.coverage` instead of the JSON report, restoring `code_tested.direct` for elspais's own suite.
- **`Integrates:` external-library references** (CUR-1419) — a requirement in a consumer repo may declare `Integrates: <associate REQ id>` to record that its implementation is provided by a configured associate (external library) repo, without the library needing any reference back to the consumer. Spec: REQ-d00252. The reference parses, stores as `integrates_refs` on the requirement, and renders from that field (round-trips through `elspais fix`). It is external-only (a same-repo target is a broken reference), wires a dedicated `INTEGRATES` edge during federation so the consumer requirement counts as implemented, and propagates the library's implemented/verified coverage to the consumer via a live-query overlay (`integrates_rollup()`). Coverage reports surface this: `elspais summary` gains an "External integrations (by associate)" section with a federation total, `elspais gaps` lists integrating requirements under "Covered via external associate" (instead of flagging them as gaps), `elspais checks` counts them as implemented, and the MCP/GUI expose the per-node inherited rollup. Unresolved targets split hard (a configured associate claims the ID format but lacks the ID) vs soft (`presumed_foreign`, non-failing) when no associate claims the format. The HTML viewer surfaces it too: a consumer requirement's card shows an "Integrated coverage" line (inherited implemented/verified counts), the `INTEGRATES` relationship renders as a read-only "Integrates" row on both the consumer and library cards (and no longer leaks into the structural Children list), and the legend gains an `Integrates` edge badge. The relationship stays spec-authored — it is intentionally not offered in the GUI edit UI's relationship picker. The `spec.hierarchy_levels` check excludes `INTEGRATES` edges, so integrating a higher-level library requirement from a lower-level consumer is not reported as a spurious level deviation (the library lives in a separate repo's hierarchy).
- **Defined-term hyperlinks in the file-viewer Rendered pane** — `fvRenderMarkdown` now passes its output (and every pipe-table cell) through `_annotateTermsInString`, so terms matched in a `.md` file's rendered view become clickable `.defined-term` spans with the same hover-tooltip and click-to-open-term-card behaviour as the card stack. The delegated click handler is scoped to `document.body` instead of `#card-stack-body` so clicks land regardless of which pane the term appears in.
- **Pipe tables render inside assertion cards** — assertion text now passes through `simpleMarkdown(text, true)` in view mode, so embedded pipe tables, bold, and term annotation appear in-card. Entering edit mode swaps each assertion span back to the raw escaped source via `_activateEditMode`; `onAssertionBlur` continues to read `el.textContent`, so the source roundtrips unchanged. `.card-assertion-text` gains `white-space: pre-wrap` so multi-line assertions (and the now-rendered table block) actually show their line breaks.
- **File-viewer Rendered mode handles pipe tables** — multi-line constructs broke under the per-line `fvRenderMarkdown` loop. Rendered mode now detects pipe-table blocks (header + separator + body), passes the whole block to `fvRenderMarkdown` so the table parses, and emits a stacked source-line gutter next to the rendered table. A post-render JS pass (`_alignTableGutter`) measures each rendered row's vertical offset and absolutely positions the matching source line number to land vertically centered on that row. Pipe tables also gain a slim visible separator row (matching the markdown `| --- |` line) so the separator's line number has its own row to align against. Every gutter number keeps its `id="fv-line-N"` anchor so jump-to-line still works for every source line inside a table block.
- **Pipe-table rendering in the viewer** — markdown pipe tables in requirement bodies, journey context, and the file-viewer's "rendered" mode now render as full-grid HTML tables with a thin 1px border on every cell (internal and external). New JS partial `_md-table.js.j2` provides `extractMdTables(lines, cellTransform)` and `reinsertMdTables(output, chunks)`; `simpleMarkdown` and `fvRenderMarkdown` extract tables before their per-line pipelines run, term-annotate cell content per-cell, and reinsert the rendered table HTML so the global term-annotation pass doesn't touch table markup. Styles live in a new `_md-tables.css.j2` partial with dark-theme variants.
- **Cross-repo template instantiation** (CUR-1353) — requirements can be marked `**Template**` on the metadata line; downstream repos declare `**Satisfies**: <template_id>` to instantiate the template subtree as in-memory INSTANCE clones with composite IDs (`declaring::original`). Single-REQ scope strictly enforced (templates have no descendant REQs). Coverage on INSTANCE assertions inherits from the template original via the `INSTANCE` edge (computed as a query — no new persisted metric). Federation via `[associates.*]` sections in `.elspais.toml`; cross-cutting evidence pattern: CODE/TEST may target template assertions directly and the evidence applies to every satisfier. Cycle detection and missing-associate diagnostics surface through `elspais health` / `elspais checks` with actionable diagnostic text. Viewer affordance: instance cards render a "Template defined in `<repo>`" provenance row with a link to the template original; instance assertion cards show inherited-coverage tooltip. New `[associates]` cross-repo template behaviour documented in `docs/cli/satisfies.md` and `docs/configuration.md`.
- **Fix idempotency regression test** — new `tests/e2e/test_e2e_idempotency.py` runs `elspais fix` twice on a fixture exercising fenced code blocks, emphasis-wrapped glossary terms, an emphasized journey actor, and REMAINDER prose with emphasis, asserting byte-equality of all files between runs so the second invocation is a complete no-op.
- **`check_spec_satisfies_resolve` health check** — new per-repo check that walks REQs declaring `Satisfies:` references and warns when any target fails to resolve to an existing requirement or assertion. Mirrors `check_spec_refines_resolve`; followup command is `elspais broken`.
- **`strip_emphasis()` utility** — new `src/elspais/utilities/markdown.py` module exposing `strip_emphasis(s: str) -> str`, which removes balanced `**`, `__`, `*`, `_` wrappers from string boundaries, trims outer whitespace, leaves unbalanced wrappers intact, and is idempotent.
- **Terms tab in viewer** — new Terms tab in the nav tree (between Journeys and the spacer) showing an alphabetical list of defined terms grouped by letter heading with reference count badges. Text filter narrows terms by name substring. Expand/collapse, tree/flat toggle, and filter groups are hidden when the Terms tab is active. Terms data loaded from `GET /api/terms` on page init.
- **Terms API endpoints** — `GET /api/terms` returns all defined terms sorted alphabetically (term, key, definition_short, defined_in, namespace, collection, indexed, ref_count); `GET /api/term/{term_key}` returns full term detail with definition and references array (node_id, node_title, namespace, marked, line). Returns 404 for nonexistent terms.
- **Term cards in viewer** — clicking a term in the Terms tab opens a read-only card in the card stack via `openTermCard(termKey)`. Card displays term name header, definition text, defined-in link (clickable to open source REQ card), namespace, and a "Collection" badge for collection terms. References section groups by namespace with each reference clickable to open its node card. Empty references show "No references resolved yet".
- **Inline term highlighting** — defined terms in remainder sections and journey bodies are wrapped in clickable, hoverable spans with class `defined-term`. Longest-first matching with word-boundary anchoring and case-insensitive lookup. Each span carries `data-term-key` and `data-tip` (truncated definition) attributes. Clicking opens the term card; hovering shows a tooltip. Term cards themselves are excluded to prevent recursion. Regex built once from `termsLookup`, cached as `termsRegex`, and invalidated on reload.
- **Comment/review system** — threaded comments on requirements, assertions, edges, and body sections, persisted as append-only JSONL in `.elspais/comments/`
  - Data layer: `CommentEvent` (frozen), `CommentThread`, `CommentIndex` with iterator-only API
  - Storage: JSONL I/O, anchor parsing, thread assembly, comment ID generation via `comment_store.py`
  - Promotion engine: validates anchors against live graph, promotes orphaned comments to nearest ancestor, updates anchors on rename
  - Graph integration: TraceGraph/FederatedGraph delegates for comment queries, anchor-based routing, rename hooks
  - API: POST `/api/comment/add`, `/reply`, `/resolve`; GET `/api/comments`, `/comments/card`, `/comments/orphaned` — author resolved server-side
  - Viewer: `data-anchor` attributes on all commentable elements, margin column with speech bubble indicators, inline thread rendering with Reply/Resolve controls
  - Comment mode: press `C` in Edit Mode or click toolbar button, then click any element to add a comment (one-shot)
  - Lost Comments card: warning card for orphaned comments, shown at top of card stack on page load
  - CLI: `elspais comments compact` strips resolved threads and collapses promote chains
  - Comments loaded automatically at viewer startup, on refresh, and on reload

### Fixed

- **Implemented coverage no longer counts test `Verifies:` references (CUR-1568, REQ-d00084-D / REQ-d00258-B)** — a test that `Verifies:` an assertion used to inflate the **Implemented** dimension: the annotator emitted its coverage as `CoverageSource.DIRECT`, which `RollupMetrics.finalize()` buckets into `implemented`, so a requirement with a verifying test but zero implementing code reported `implemented` credit it had not earned. Test evidence now flows through dedicated `CoverageSource.TEST_DIRECT` / `TEST_INDIRECT` sources (mirroring how `VALIDATES` uses distinct UAT sources) that populate only the **Tested** dimension, never **Implemented**. Implemented is once again strictly CODE/REQ evidence (`Implements:` references, conducted, or inherited) per REQ-d00084-D, restoring the Implemented-vs-Tested distinction REQ-d00258-B rests on. The transitive path (CODE implements an assertion AND that CODE is verified by a TEST) is unaffected — its implemented credit comes from the CODE `Implements:` edge, not from the verifying test. Impact on elspais's own repo: headline Implemented drops from ~96% to ~81% (558/687 vs the previously-inflated 660/687) — the removed credit was being carried by tests, not code; Tested is unchanged.
- **Genuinely-local broken references no longer suppressed as "cross-repo" (CUR-1568, REQ-d00252-G)** — `FederatedGraph._annotate_presumed_foreign_refs` no longer presumes a broken reference foreign just because it fails to parse under the source repo's `IdResolver`. With no configured associates at all (e.g. an empty `[associates]` table), nothing can be presumed foreign since there's no other repository the reference could belong to. Even with associates configured, a target whose leading token matches the declaring repo's own namespace is treated as a malformed local reference (carrying a diagnostic pointing at the likely `[id-patterns.assertions]` separator/multi_separator mismatch) rather than a cross-repo one, unless another configured associate shares that namespace. Previously, `validation.allow_unresolved_cross_repo` could silently suppress dozens of genuinely-local broken references as "N cross-repo suppressed" in `elspais checks`, masking real regressions.
- **`dart_prescan` handles multiline/raw strings and block comments (CUR-1568)** — the Dart test-file prescanner (CUR-1533) now tracks string/comment state across `'''`/`"""` triple-quoted and `r'...'`/`r"..."` raw-string literals and `/* */` block comments when brace-matching `test()`/`testWidgets()` boundaries, so a brace inside a multiline string or block comment no longer misattributes a test's line range or `// Verifies:` comment.
- **`match = "source"` resolves results per test, not just per file (CUR-1533)** — source matching for test_id-less reporters (`flutter-machine`) now correlates each result to the specific `test()` by its source location, with file-granular fallback when it can't resolve (shared-helper or generated suites). This required teaching elspais to see Dart test-case boundaries: a new `dart_prescan` (regex + string/comment-aware brace matching, no Dart parser) routes `.dart` test files so each `test()`/`testWidgets()` becomes its own TEST node anchored on the call-site line, and `// Verifies:` comments attribute to individual tests. The builder resolves each result by `(source_file, line)`, then by `(root_file, root_line)` — the latter recovers `testWidgets` tests, whose reported `line` points at the `flutter_test` framework wrapper while `root_line` holds the user's call site — then falls back to every TEST in the file; each result is stamped `match_scope` (`"test"`/`"file"`). **Crediting follows resolution:** a per-test-resolved result credits inline (its pass credits only its assertions; its fail flags only its own), while file-scope results keep the all-pass/any-fail file-level crediting via the annotator's `source_file_index` (no double-counting — the two are complementary). This also wires the real RESULT→TEST `YIELDS` edges the viewer's per-assertion Verified panel reads (`_get_assertion_test_map` → `_serialize_test_info`), which were previously absent for `flutter-machine`. `test_id`-linked reporters (junit/pytest) are unchanged. `REQ-d00254-G` amended accordingly.
- **Jump-to-line works inside a rendered pipe-table block** — `fvScrollAndFlash` now falls back to `#fv-line-N` (the gutter span's id) when `.source-line[data-line="N"]` isn't found, and highlights the nearest `.source-line` ancestor. Previously only the block's first source line was addressable; jumping to a line inside the table body was a silent no-op.
- **Pipe-table placeholders survive DOM serialization** — `extractMdTables` / `reinsertMdTables` switched the internal placeholder from a NUL-byte-wrapped sentinel to ASCII-only `[[ELSPAISMDTABLE_N]]`. NUL chars are valid in JS strings but can be stripped or normalized when assigned to `innerHTML` in some browsers, which would leave the placeholder literally rendered in place of the table. The bracket wrappers are non-word characters so the term-annotation regex's `\b…\b` still can't match the inner token. Reinsertion uses `split`/`join` for defensive multi-occurrence safety.
- **JS-string-safe escaping for paths in inline onclick handlers** — file paths interpolated into `onclick="showSource('…')"` now route through a new `escapeJsInAttr` helper that backslash-escapes `\` and `'` (plus `\n`/`\r`) before HTML-attribute escaping. `escapeHtml` and `escapeAttr` only handle the HTML layer; an embedded `'` in a path (`it's-a-spec.md`) would otherwise terminate the JS string literal early and break the handler (or, in the worst case with adversarial paths, enable script injection). 11 card-stack call sites updated.
- **VS Code link targets the correct file in associate repos** — the file viewer's `vscode://file/...` button now uses the server-resolved `abs_path` from `/api/file-content` instead of prepending `document.body.dataset.basePath` (which only knows the federation root) to the relative path. Opening an associate-repo card and clicking the VS Code link now opens the actual associate file in VS Code.
- **Term auto-marker no longer double-wraps inside outer emphasis** — `_canonicalize_text` now scans every `**…**` / `__…__` / `*…*` / `_…_` span up front and skips wrapping a term occurrence whose match falls strictly inside one. Previously, when a defined term appeared inside a longer bold phrase (e.g. `**Diary Start Day**` with defined term `Diary`), the unmarked-occurrence pass re-wrapped it, producing `****Diary** Start Day**` which pandoc rendered as literal asterisks. The guard refreshes emphasis-span ranges after every text mutation so subsequent term iterations see the updated structure.
- **Term-index bullet separation** — `generate_term_index` (and `generate_collection_manifest`) now emit a blank line between each `**namespace:**` header and its bullet list, and after the list. Without the leading blank, pandoc treated the bullets as paragraph continuation of the bold header rather than as a list, so references collapsed visually. Bug surfaced in `_generated/term-index.md` rendering Chapter 9 (pages 267-303) of the URS-1 export.
- **Glossary blank line between terms** — `generate_glossary` (`elspais glossary`, `elspais fix` auto-generation) now appends a blank line after each term's metadata block. Without it, two adjacent `: definition` lines rendered as a single definition-list item in pandoc/markdown viewers.
- **Term-card "Defined in" link routes to the correct federated repo** — `defined_in` on a `TermEntry` can be either a REQ id or a FILE id, and FILE ids legitimately collide across federated repos (`FederatedGraph._ownership` silently keeps whichever repo iterated first for structural-prefix collisions). The previous fix stripped `file:` unconditionally and trusted `repo_root_for(node_id)`, which silently 404'd for REQ-ancestor terms and routed to the wrong repo for colliding FILE ids. The proper fix: `TermEntry` carries `repo_name` (stamped in `FederatedGraph._merge_terms`); `api_term` resolves `defined_in_path`/`defined_in_line` server-side and returns `repo_name`; `/api/file-content` accepts a `repo_name` query param that takes precedence over `node_id` and resolves strictly against `iter_repos()`-by-name (no `allowed_roots` fallback when an owner is named). The JS `showSource(filePath, lineNumber, nodeId, repoName)` and `fvState` thread the new param end-to-end.
- **File-viewer refresh preserves `node_id`** — `showSource(filePath, lineNumber, nodeId)` now persists `nodeId` to `fvState.currentNodeId`, and `refreshFileViewer` threads it back on re-fetch. Previously a refresh after opening an associate file would drop the node id and reroute the request to the federation root, which could collide on shared relative paths (e.g. `spec/prd.md`).
- **Term-scanner startup performance** — `_build_emphasis_pattern` in `graph/term_scanner.py` re-compiled the same `(delimiter, term)` regex inside `scan_text_for_terms`'s per-region loop, so a federation with ~hundreds of terms × thousands of text regions × four emphasis delimiters compiled ~100k+ patterns at every `FederatedGraph.from_single()` (i.e. every MCP server / viewer / checks startup). Added `@functools.cache` so each unique `(delimiter, term)` pair compiles exactly once per process. Benchmark: 400k lookups go from many seconds to 28ms.
- **Term card "Defined in" link opens the source file** — previously the link called `openCard(<file-node-id>)` which loaded an empty FILE card. It now strips the `file:` prefix and calls `showSource(path, line, fileNodeId)`, so clicking the link opens the file in the right pane (and routes through the owning associate via the file node id). Display text also drops the `file:` prefix for readability.
- **`/api/file-content` path-only fallback for associate files** — when a caller has a bare file path and no graph node id (test/code reference clicks whose graph node id wasn't captured), the server now tries the federation root first and then walks `state.allowed_roots` until the path resolves. Security guard (path must land under some allowed root) is intact. Resolves the 404s observed on `apps/.../test/...` paths from federated test-coverage cards.
- **PDF cross-repo content rendering** — `elspais pdf` now embeds requirement bodies from associate repos instead of only referencing them. `MarkdownAssembler` threads each file's owning-repo root through `_render_file`, `_resolve_path`, `_resolve_mermaid_images`, and `_topics_from_file` so paths resolve against the associate's filesystem when known, with an `iter_repos()` fallback for callers without ownership context. The Topic Index now prefixes cross-repo entries with `[<repo_name>]` (e.g. `[callisto] [REQ-p00099](#REQ-p00099)`); root-repo entries render unchanged. Legacy callers that pass a bare `TraceGraph` retain prior single-repo behaviour via `getattr`-guarded federation lookups.
- **PDF relative image paths** — `elspais pdf` now passes `--resource-path` to pandoc with every federated repo's root and `spec/` directory (de-duplicated). Pandoc previously resolved relative image references against the temporary assembled-markdown file's directory in `/tmp/`, silently dropping every non-mermaid image (e.g. `![alt](../docs/images/foo.png)`). Mermaid images were unaffected because the assembler already rewrites those to absolute paths.
- **Viewer file-content cross-repo resolution** (CUR-1357) — `/api/file-content` now accepts an optional `node_id` query parameter and uses `FederatedGraph.repo_root_for(node_id)` to resolve files against the owning associate's repo root, fixing "Failed to load file" for any card whose source lives outside the federation root. JS callers in `_file-viewer.js.j2` and `_card-stack.js.j2` thread the node id through `showSource()`. Path-only callers (the `vscode://` intercept and term-reference links) fall back to `state.repo_root` unchanged, preserving prior behaviour for root-repo paths. Security guard (`state.allowed_roots`) is unaffected.
- **INDEX.md cross-repo attribution** — `elspais index` no longer emits an `### Unknown Source` section for foreign-repo requirements (e.g. `REQ-CAL-*` from a `callisto` associate). Repo classification now consults the FederatedGraph ownership map (`graph.repo_for(node_id).name`) instead of matching FILE-node `absolute_path` against the primary repo's `spec_dirs`, so cross-repo REQs render under their owning repo's section.

- **Term name emphasis stripping** — term names captured during definition-block parsing now pass through `strip_emphasis()`, so `**Email Address**` and `Email Address` no longer collide as distinct terms in the glossary and term index.
- **Journey field and reference emphasis stripping** — journey actor/goal/context values and `reference term`/`reference source` values now pass through `strip_emphasis()`, eliminating unbalanced `**` leakage into `INDEX.md` actor cells and replacing the prior asymmetric `.strip("_").strip("*")` that mangled unbalanced wrappers.
- **Fenced code block preservation** — `elspais fix` no longer overwrites the contents of fenced code blocks with `<!-- fenced -->` placeholders. The neutralization step used during parsing is now confined to the parser, and the original source is used when capturing remainder text so fenced bodies round-trip unchanged through regenerations.
- **Piped `Satisfies` metadata parse error** — `elspais fix` no longer rejects `**Satisfies**: REQ-X` when placed on the piped metadata line alongside Level/Status/Implements/Refines (`Unexpected token Token('SATISFIES_FIELD', ...)`). Authors using the piped form were previously blocked from running `fix`; Satisfies now flows through the same path as Implements/Refines. Standalone `Satisfies: REQ-X` on its own line continues to parse via the unified metadata-line rule -- no migration required.

## [0.112.34]

### Added

- **`elspais errors` command** — drill-down from `elspais checks` showing specific requirements with format rule violations and missing assertions. Supports `--format text|markdown|json`, `--status`, and `-o` output file.

### Fixed

- **N/A hash sentinel** — unhashable content (e.g. requirements with no assertions in normalized-assertions hash mode) now receives an `N/A` hash instead of raising an error or producing a misleading value.
- **Active REQ changelog enforcement explanation** — `elspais fix` error message now explains that `[changelog] hash_current` is enabled and that Draft/Deprecated requirements update without requiring a message.
- **Global fix defers Active REQs with changelog** — global fix mode defers Active requirements that have changelog enforcement enabled, showing per-REQ guidance instead of silently skipping them.
- **REFORMATTED vs FIXED labeling** — `elspais fix` output now distinguishes formatting-only changes (REFORMATTED) from hash-changing fixes (FIXED), and only reports succeeded fixes.

## [0.108.6]

### Changed

- Migrate all config consumers to v3 schema paths:
  - `doctor.py`: `check_associate_paths()`, `check_associate_configs()`, `check_cross_repo_in_committed_config()` now use `get_associates_config()` and `scanning.spec.directories`
  - `index.py`: `_resolve_spec_dir_info()` now uses typed `ElspaisConfig` instead of raw dict access
  - `validate.py`: Associate path checks now use `get_associates_config()` instead of `associates.paths` array
  - `associate_cmd.py`: `cmd_list()` now uses `get_associates_config()`
  - `associates.py`: Remove legacy `associates.paths` array fallback
- Update all tests from v2 `associates.paths` array format to v3 named `[associates.<name>]` sections

## [0.108.5]

### Removed

- Delete `reference_config.py` (`ReferenceConfig`, `ReferenceOverride`, `ReferenceResolver`) - fully replaced by Lark parser and `IdResolver`.
- Delete legacy `CodeParser` (`graph/parsers/code.py`) and `TestParser` (`graph/parsers/test.py`) - replaced by Lark `FileDispatcher`.
- Remove `ReferencesConfig` from Pydantic schema and `[references]` section from config. Existing configs with `[references]` are silently stripped for backwards compatibility.
- Delete associated test files: `test_reference_config.py`, `test_code_parser.py`, `test_test_parser.py`, `test_colon_optional.py`.

## [0.108.4]

### Changed

- Remove `ReferenceResolver` construction and legacy `code_registry`/`test_registry` from `factory.py`. Remove unused `CodeParser`, `TestParser`, and `ReferenceResolver` imports.

## [0.108.3]

### Changed

- Remove `ReferenceConfig`/`ReferenceResolver` from result parsers (`JUnitXMLParser`, `PytestJSONParser`). ID extraction now uses `IdResolver.search_regex()` and `normalize_ref()` directly.
- `IdResolver.search_regex()` now matches both hyphen and underscore separators (e.g. `REQ-p00001` and `REQ_p00001`) with a negative lookahead to prevent false assertion captures.

## [0.108.2]

### Changed

- Remove `ReferenceConfig` parameter from `GrammarFactory` and `FileDispatcher`. Comment styles and reference keywords are now hardcoded (Implements/IMPLEMENTS, Verifies/VERIFIES, Refines/REFINES).

## [0.108.1]

### Changed

- Extract prescan/language detection utilities from legacy `CodeParser` and `TestParser` into standalone `prescan.py` module. Lark `FileDispatcher` now imports from `prescan` instead of legacy parsers.

## [0.108.0]

### Changed

- **BREAKING: ElspaisConfig v3 restructuring** -- Major config schema reorganization with 6 structural changes:
  - **New `levels` top-level field** -- `dict[str, LevelConfig]` replaces `[patterns.types]`. Each level declares `rank`, `letter`, `display_name`, and `implements` rules (hierarchy rules moved here from `[rules.hierarchy.allowed_implements]`).
  - **New `scanning` top-level field** -- Unified `ScanningConfig` with per-kind subclasses (`spec`, `code`, `test`, `result`, `journey`, `docs`), each with `directories`, `file_patterns`, `skip_files`, `skip_dirs`. Global `skip` list replaces `[ignore]` and `[directories].ignore`.
  - **New `output` top-level field** -- `OutputConfig` with `formats` and `dir`, replacing `[traceability].output_formats` and `output_dir`.
  - **Removed `[directories]`** -- Absorbed into `[scanning.<kind>].directories`.
  - **Removed `[spec]`** -- Replaced by `[scanning.spec]` (with `index_file`, `skip_files`, etc.).
  - **Removed `[testing]`** -- Split into `[scanning.test]` (test discovery) and `[scanning.result]` (result files).
  - **Removed `[ignore]`** -- Absorbed into `[scanning].skip` and per-kind `skip_files`/`skip_dirs`.
  - **Removed `[graph]`** -- `satellite_kinds` hardcoded internally.
  - **Removed `[traceability]`** -- Output fields moved to `[output]`; scan patterns absorbed into `[scanning.code]`.
  - **Removed `[core]` and `[associated]`** -- No more core/associated project type distinction.
  - **`IdPatternsConfig` updated** -- Added `separators`, `prefix_optional`; removed `types` (now `levels`) and `associated`; canonical template uses `{level.letter}` instead of `{type.letter}`.
  - **`HierarchyConfig` simplified** -- Removed per-level keys; only boolean flags remain (`allow_circular`, `allow_structural_orphans`, `cross_repo_implements`). Implements rules moved to `levels.<name>.implements`.
  - **`ReferencesConfig` simplified** -- Only `enabled` + `case_sensitive`; removed `defaults` and `overrides` sub-sections.
  - **`ProjectConfig` simplified** -- Removed `version` (now top-level) and `type` (no core/associated distinction).
  - **`AssociateEntryConfig` simplified** -- Only `path` + `namespace`; removed `git` and `spec` fields.
  - **Config version defaults to 3**.

## [0.107.0]

### Added

- **`LevelConfig` schema model** -- Per-level Pydantic model with `rank`, `letter`, `display_name`, and `implements` fields for declarative hierarchy level configuration.
- **Unified `ScanningConfig` schema models** -- `ScanningKindConfig` base class with `directories`, `file_patterns`, `skip_files`, `skip_dirs` fields, plus specialized subclasses: `SpecScanningConfig`, `CodeScanningConfig`, `TestScanningConfig`, `ResultScanningConfig`, `JourneyScanningConfig`, `DocsScanningConfig`. Composite `ScanningConfig` model groups all kinds with a global `skip` list.
- **`OutputConfig` schema model** -- Pydantic model for output configuration with `formats` and `dir` fields.
- **`ChangelogRequireConfig` schema model** -- Groups changelog requirement booleans (`reason`, `author_name`, `author_id`, `change_order`) into a `[changelog.require]` sub-section.

### Changed

- **`ChangelogConfig` field renames (BREAKING)** -- `enforce` renamed to `hash_current`, `require_present` renamed to `present`. Per-field requirement booleans (`require_reason`, `require_author_name`, `require_author_id`, `require_change_order`) moved into a nested `require` sub-model (`[changelog.require]` in TOML). Old field names are no longer accepted.

### Added

- **Viewer config-driven dropdowns** -- Requirement types, relationship kinds, and allowed statuses are now derived from `ElspaisConfig` and passed to the viewer template context (REQ-d00211).
- **`docs.config_drift` health check in `elspais doctor`** -- Compares `ElspaisConfig` schema sections against `docs/configuration.md` and reports undocumented and stale sections. Ensures documentation stays in sync with the config schema (REQ-d00210).
- **Schema-driven `elspais init` template generation** -- `generate_config()` now walks the `ElspaisConfig` Pydantic model to produce TOML configuration instead of using hardcoded template strings. This ensures `elspais init` always generates config that validates against the current schema.
- **`elspais config schema` subcommand** -- Exports the JSON Schema for `.elspais.toml` to stdout (or to a file with `--output`/`-o`). The committed schema file `src/elspais/config/elspais-schema.json` stays in sync with the Pydantic model via CI test. A `$schema` key is injected into the generated schema for IDE support.
- **Tyro core dependency** -- Added `tyro>=0.9` to `pyproject.toml` core dependencies for declarative CLI generation replacing argparse (CONFIG-SCHEMA Phase 3).
- **CLI arg dataclasses** (`commands/args.py`) -- Tyro-compatible dataclass definitions for all 23 top-level subcommands and nested subcommands (config, rules, mcp, link, install, uninstall). `GlobalArgs` is the root dataclass with `Command` Union type for subcommand dispatch.
- **Pydantic v2 core dependency** -- Added `pydantic>=2.0` to `pyproject.toml` core dependencies in preparation for declarative config schema validation (CONFIG-SCHEMA Phase 1).
- **Pydantic config schema** (`config/schema.py`) -- All Pydantic models for `.elspais.toml` validation: `ElspaisConfig` root with nested models for project, ID patterns, spec, rules, testing, ignore, references, keywords, validation, graph, changelog, directories, traceability, associates. `extra="forbid"` catches unknown keys; `frozen=True` ensures immutability; `Field(alias=...)` handles TOML hyphenated keys.
- **Cross-field config validators** -- `@model_validator` on `ElspaisConfig` enforces `project.type='associated'` requires `[core]` section.
- **Version-gated migration system** -- `CURRENT_CONFIG_VERSION` and `MIGRATIONS` registry in `config/__init__.py` replaces direct `_migrate_legacy_patterns()` call with sequential version-gated migration in `load_config()`. Fixed latent bug where absent `[id-patterns]` section blocked migration.
- **Pydantic-validated config loading** -- `load_config()` now validates `.elspais.toml` through `ElspaisConfig.model_validate()` and returns a plain `dict[str, Any]` via `model_dump(by_alias=True, exclude_none=True)`. Unknown top-level keys are rejected. Legacy keys (`patterns`, `requirements`, `paths`) are stripped before validation and restored afterward for backward compatibility.

### Changed

- **CLI rewrite: argparse replaced with Tyro** -- `cli.py` now uses `tyro.cli(GlobalArgs)` for argument parsing. `OmitSubcommandPrefixes` and `OmitArgPrefixes` markers maintain clean `elspais health --format json` syntax. Compatibility shim converts typed dataclasses to `argparse.Namespace` for existing command `run()` functions. All CLI flag names and short aliases (`-o`, `-v`, `-q`, `-C`, `-n`, `-m`, `-a`) preserved via `tyro.conf.arg()`.
- **`graph/factory.py` config migration** -- Converted 21 `config.get()` call chains to typed `ElspaisConfig` attribute access in `build_graph()` and `_resolve_spec_dir_config()`. Added `_validate_config()` helper for safe Pydantic conversion at function boundaries.
- **`mcp/server.py` config migration** -- Converted 21 config dict access calls across 10 MCP workspace/tool functions to typed `ElspaisConfig` attribute access.
- **Consumer config migration (Tasks 9-12)** -- Migrated all remaining `config.get()` calls to typed `ElspaisConfig` attribute access across `commands/health.py`, `commands/doctor.py`, `commands/fix_cmd.py`, `commands/changed.py`, `commands/example_cmd.py`, `commands/validate.py`, `graph/annotators.py`, `graph/analysis.py`, `associates.py`, `validation/format.py`, `content_rules.py`.

### Fixed

- **`content_rules.py` config loading** -- `load_content_rules()` callers now pass `config.get_raw()` instead of `ConfigLoader` object, fixing `AttributeError: 'ConfigLoader' has no attribute 'items'` in `rules list`.
- **`TypeConfig.aliases` made optional** -- The Pydantic schema now allows `aliases` to be omitted in `[id-patterns.types]`, fixing validation failures for configs that don't explicitly define type letter aliases.
- **`ComponentConfig.max_length` added** -- The Pydantic schema now accepts `max_length` in `[id-patterns.component]`, fixing validation failures for named-component configs.

### Removed

- **Dead config helpers** -- Deleted `get_project_name()`, `validate_project_config()`, and `ConfigValidationError` from `config/__init__.py`. Their functionality is now handled by `ElspaisConfig` schema validation and typed attribute access.
- **`--set` CLI flag and `apply_cli_overrides()`** -- Removed the `--set key=value` runtime config override flag and its implementation. Use `.elspais.local.toml` for local config overrides instead (see [Configuration docs](docs/configuration.md)).
- **`completion` command and argcomplete support** -- Removed the `elspais completion` subcommand, `[completion]` pip extra, and argcomplete integration. Shell completion based on argcomplete is incompatible with the Tyro CLI framework.
- **`ConfigLoader` class and `DEFAULT_CONFIG` dict** -- Removed from `config/__init__.py`. `load_config()` now returns a plain `dict[str, Any]`. Defaults are derived from the `ElspaisConfig` Pydantic model via `config_defaults()`. All consumers updated to use plain dicts.

### Docs

- **`spec/requirements-spec.md`** -- Added `Validates:` field documentation in the JNY format section with multi-assertion syntax example (`Validates: REQ-xxx-A+B`), new "User Journeys Declaring Validation Relationships" subsection, and updated relationship table to include UAT coverage role. Updated "non-normative" note to clarify JNYs may declare `Validates:` references.
- **`CLAUDE.md`** -- Fixed `TEST_RESULT` → `RESULT` in Render Protocol description; added `VALIDATES` to `_TRACEABILITY_EDGE_KINDS` list with explanatory note distinguishing VERIFIES (automated) from VALIDATES (UAT/JNY).
- **`KNOWN_ISSUES.md`** -- Marked JNY Validates task complete (`[x]`) with implementation summary.

### Added

- **UAT section in `_get_test_coverage()` MCP tool** -- Returns a `"uat"` dict alongside existing test data containing `jny_nodes`, `covered_assertions`, `covered_count`, `referenced_pct` (from VALIDATES edges), and `validated_pct` (from `RollupMetrics.uat_validated_pct`).
- **`source` parameter in `_get_uncovered_assertions()` MCP tool** -- Accepts `'test'` (default, backward-compatible), `'uat'` (JNY Validates coverage only), or `'both'` (union). MCP tool wrapper `get_uncovered_assertions` forwards the parameter. Return dict now includes both `"assertions"` and `"uncovered_assertions"` keys (same list, alias for clarity).

- **`_compute_coverage_from_source()` helper in `annotators.py`** -- Extracted shared algorithm for computing coverage contributions from outgoing REQ edges. Parameterized by edge kind and source types, used by both the VERIFIES (TEST) and VALIDATES (JNY) paths.
- **JNY `Validates:` coverage path in `annotate_coverage()`** -- VALIDATES edges (REQ→JNY) now contribute `UAT_EXPLICIT` (assertion-targeted) and `UAT_INFERRED` (whole-REQ) coverage to `RollupMetrics`. JNY result nodes are checked for pass/fail to set `uat_validated` and `uat_has_failures`.
- **UAT roll-up through IMPLEMENTS in `annotate_coverage()`** -- When a child REQ implements a parent REQ, UAT_EXPLICIT/UAT_INFERRED contributions are also added to the parent, mirroring the automated EXPLICIT/INFERRED roll-up pattern.

- **`CoverageSource.UAT_EXPLICIT` and `CoverageSource.UAT_INFERRED`** -- Two new enum values in `CoverageSource` for UAT coverage originating from JNY `Validates:` references. `UAT_EXPLICIT` covers assertions explicitly named (e.g., `Validates: REQ-xxx-A`); `UAT_INFERRED` covers all assertions implied by a whole-REQ reference (e.g., `Validates: REQ-xxx`).
- **7 UAT fields in `RollupMetrics`** -- `uat_covered`, `uat_direct_covered`, `uat_inferred_covered`, `uat_referenced_pct`, `uat_validated`, `uat_has_failures`, `uat_validated_pct`. Computed by `finalize()` from UAT contributions; `uat_validated` and `uat_validated_pct` set by annotator post-finalize (same pattern as `validated`/`validated_with_indirect`).

### Changed

- **`EdgeKind.ADDRESSES` replaced with `EdgeKind.VALIDATES`** -- JNY→REQ edges now use `VALIDATES` (value `"validates"`) instead of `ADDRESSES` (value `"addresses"`). `VALIDATES` contributes to coverage rollup (UAT coverage). All 5 `spec/journeys/` files migrated from `Addresses:` to `Validates:`. `JourneyParser` updated to parse `Validates:` field. `builder.py`, `html/generator.py`, and `mcp/server.py` updated. All test helpers and callsites updated.
- **`NodeKind.TEST_RESULT` renamed to `NodeKind.RESULT`** -- Pure symbol rename; the string value `"result"` is unchanged. All internal references updated across `graph/`, `html/`, `mcp/`, and `commands/` modules.

### Added

- **`FederatedGraph` class** -- New `graph/federated.py` module with `RepoEntry` dataclass and `FederatedGraph` wrapper. Wraps one or more `TraceGraph` instances with per-repo config isolation. Implements all read-only methods with documented federation strategies (by_id, aggregate). Includes `from_single()` for federation-of-one, `repo_for()`, `config_for()`, `iter_repos()`. Error-state repos (graph=None) are skipped during aggregation.
- **Legacy sponsor system removed** -- Removed YAML-based `sponsors.yml`/`sponsors.local.yml` loading, `Sponsor`/`SponsorsConfig`/`AssociatesConfig` aliases, `load_associates_config()`, `resolve_associate_spec_dir()`, `parse_yaml()`, and the `scan_sponsors` parameter from `build_graph()`. All multi-repo federation now uses `[associates]` TOML config exclusively. `Associate`, `discover_associate_from_path()`, and `get_associate_spec_directories()` (path-based loading) are retained.
- **Cross-graph edge wiring** -- `FederatedGraph` detects ID conflicts across repos and wires cross-graph edges by resolving broken references. `TraceGraph.add_edge()` gains `target_graph` parameter for cross-graph resolution. After wiring, only genuinely unresolvable references remain as broken.
- **Multi-repo federation build** -- `build_graph()` now builds separate `TraceGraph` per associate repository when `[associates]` config is present. Each associate gets its own config, resolver, and graph. Missing associates create error-state `RepoEntry` (soft fail). `strict=True` raises `FederationError` on missing associates.
- **`[associates]` config section** -- `get_associates_config()` reads `[associates.<name>]` sections from `.elspais.toml` with `path` (required) and `git` (optional) fields. Returns empty dict when no associates are configured. `validate_no_transitive_associates()` raises `FederationError` if an associate declares its own associates.
- **Per-repo health check delegation** -- Config-sensitive health checks (hierarchy levels, format rules, reference resolution, structural orphans, changelog) now run per-repo using each repo's own config via `FederatedGraph.iter_repos()`. Non-config-sensitive checks (file parseability, duplicates, hash integrity, index) run once on the full federation. `HealthFinding` gains optional `repo` field for per-repo attribution. `check_broken_references` distinguishes within-repo broken refs (error severity) from cross-repo broken refs where the target repo is in error state (warning severity).
- **MCP federation support** -- `get_workspace_info()` includes a `federation` section with repo names, paths, error states, and git origins when multiple repos are present. `refresh_graph()` syncs `_state["config"]` from the rebuilt federation's root repo config after every rebuild, preventing config staleness. `_get_workspace_info` derives root config from FederatedGraph when not provided explicitly.
- **Server federation and staleness** -- New `/api/repos` endpoint returns federated repo list with name, path, status, git_origin, error, and staleness info (branch, remote_diverged, fast_forward_possible) for repos with a configured git origin. `/api/status` now includes `repos` field from `iter_repos()`, replacing the legacy `associated_repos` field.
- **Federation-aware `render_save()`** -- File path resolution now uses the owning repo's root path from `FederatedGraph.repo_for()`, preparing for multi-repo file persistence. `repo_root` parameter now defaults to `graph.repo_root`.
- **`build_graph()` returns `FederatedGraph`** -- Factory wraps result in `FederatedGraph.from_single()`. All consumer type hints updated from `TraceGraph` to `FederatedGraph` across commands, graph modules, MCP server, Flask app, and HTML/PDF generators. `FederatedGraph` exported from `graph/__init__.py`.
- **`FederatedGraph` mutation methods** -- All TraceGraph mutations (rename, update, delete, edge ops, assertions) delegate to the correct sub-graph via ownership mapping. Unified `FederatedMutationLog` tracks mutations across repos with lightweight pointers. `undo_last()`/`undo_to()` delegate to the correct sub-graph. `add_requirement()` accepts `target_repo` parameter. `clone()` deep-copies the entire federation.
- **Branch selection** -- Click the branch badge in the viewer header to switch between local and remote git branches. Modal shows a filterable list grouped by local/remote, handles checkout, graph reload with config refresh, and full UI state refresh. Refuses to switch when unsaved mutations exist. Detached HEAD shown as "no branch selected" with tooltip.
- **`list_branches()` git utility** -- Lists local and remote branches, strips `origin/` prefix, deduplicates.
- **`GET /api/git/branches`** -- Returns branch list for the viewer.
- **`POST /api/git/checkout`** -- Switches branches with mutation guard and remote fallback.
- **`/api/reload` config refresh** -- Re-reads `.elspais.toml` from disk before rebuilding the graph, supporting branch-specific configuration.
- **`move_node_to_file()` graph mutation** -- Moves a requirement between FILE nodes by re-wiring the CONTAINS edge. Full undo support.
- **`rename_file()` graph mutation** -- Renames a FILE node (updates ID, index, paths). `render_save()` handles disk rename. Full undo support.
- **`change_edge_targets()` mutation** -- Modifies assertion targets on IMPLEMENTS/REFINES edges without requiring delete+add. Full undo support.
- **MCP tools** -- `mutate_move_node_to_file`, `mutate_rename_file`, `mutate_change_edge_targets` for graph manipulation via MCP.
- **Flask API endpoints** -- `/api/mutate/move-to-file`, `/api/mutate/rename-file` for viewer-driven mutations.
- **Viewer UI** -- "Move to file" button, file rename button, assertion targets display in the card view.

## [0.104.17] - 2026-03-14

### Added

- **Help mode** -- "? Help" in hamburger menu activates a fixed help bar below the header. Hovering over controls shows extended descriptions. Native browser tooltips are suppressed while help mode is active and restored on deactivation.

## [0.104.16] - 2026-03-14

### Added

- **CLI config overrides** -- `--set key=value` repeatable flag overrides any config value at runtime. Supports dotted paths, JSON lists, and booleans. Precedence: `--set` > env vars > `.elspais.local.toml` > `.elspais.toml` > defaults. *(Removed in [Unreleased] -- use `.elspais.local.toml` instead.)*

## [0.104.15] - 2026-03-14

### Added

- **Viewer refresh-from-disk** -- "Refresh" button in header reloads graph from disk. `/api/check-freshness` endpoint detects stale spec files. Client polls every 30s and shows a non-intrusive banner when files change on disk. Warns before discarding pending mutations.

## [0.104.14] - 2026-03-14

### Fixed

- **Mutation refresh gaps** -- Status and title changes now refresh the nav tree and all open cards (not just the mutated card). Edge mutations (add/delete/change kind) and undo refresh all open cards. Save and revert refresh the file viewer panel. Added `refreshAllOpenCards()` and `refreshFileViewer()` helpers.

## [0.104.13] - 2026-03-14

### Fixed

- **Card scroll-to targeting** -- `focusCard()` now renders the card stack before scrolling, preventing stale scroll position when `renderCardStack()` replaced the target DOM element.

## [0.104.12] - 2026-03-14

### Fixed

- **Test scanner class context** -- Python test files now use `ast.parse()` for pre-scanning, fixing incorrect TEST node IDs when multiline strings contained unindented content (e.g., `## REQ-d00001:` at column 0 inside a `"""` heredoc). Previously, the text-based indent tracker incorrectly exited class scope, producing 123 class-less TEST node IDs and 111 broken YIELDS references.

### Added

- **Configurable test pre-scan command** -- `[testing].prescan_command` config option for non-Python test files. The command receives file paths on stdin and outputs a JSON array describing test structure (`[{file, function, class, line}]`), enabling accurate test discovery for any language.

## [0.104.11] - 2026-03-14

### Changed

- **Traceability classification redesign** -- Split `spec.orphans` health check into distinct checks with appropriate severities:
  - `spec.structural_orphans` (error) -- nodes without FILE ancestor (build bugs)
  - `spec.broken_references` (warning) -- edges targeting non-existent nodes
  - `tests.unlinked` (info) -- tests not linked to any requirement
  - `code.unlinked` (info) -- code refs not linked to any requirement
- **Removed** `tests.references_resolve` and `code.references_resolve` checks (subsumed by `*.unlinked` + `spec.broken_references`)
- **Config** `allow_orphans` replaced by `allow_structural_orphans` (backward compatible)

### Added

- **Graph API** -- `is_reachable_to_requirement()`, `iter_unlinked()`, `iter_structural_orphans()` methods on TraceGraph
- **Edge kind constants** -- `_STRUCTURAL_EDGE_KINDS` and `_TRACEABILITY_EDGE_KINDS` in builder.py for classifying edge types
- **MCP tool** -- `get_unlinked_nodes(kind?)` lists CODE/TEST nodes not linked to any requirement

## [0.104.10] - 2026-03-14

### Added

- **Comprehensive mutation round-trip scenario test** -- E2E test exercising 70+ mutations across all types (status, title, assertion CRUD, edge CRUD, requirement CRUD, undo) through the Flask API layer, with intermediate checkpoints, save-reload verification, and a second mutation round proving saved state is mutable (REQ-d00134-A through REQ-d00134-F)

### Fixed

- **Scenario test `.elspais.toml`** -- `build_graph` reload in scenario test now creates a `.elspais.toml` config file so `_find_repo_root` can locate the spec directory

## [0.104.9] - 2026-03-13

### Added

- **MCP FILE node integration** -- `get_subtree()` uses filtered traversal: FILE roots walk CONTAINS edges (file contents view), REQUIREMENT roots walk domain edges (IMPLEMENTS, REFINES, STRUCTURES). FILE nodes do not appear in `search()` results. `get_graph_status()` reports FILE node counts. (REQ-d00133-A through REQ-d00133-F)
- **`_SUBTREE_KIND_DEFAULTS` for FILE** -- Conservative kind defaults for FILE root subtree traversal include REQUIREMENT, ASSERTION, and REMAINDER (REQ-d00133-C)
- **`_SUBTREE_EDGE_DEFAULTS`** -- New edge-kind filter map determines which edge types to follow per root kind during subtree extraction (REQ-d00133-A, REQ-d00133-B)

### Added (spec)

- **REQ-d00133** -- New requirement "MCP FILE Node Integration" with assertions A-F covering subtree filtered traversal, search exclusion, graph status reporting, and serialization

## [0.104.8] - 2026-03-13

### Added

- **DEFINES edges for template instances** -- Template instantiation (`_instantiate_satisfies_templates()`) creates DEFINES edges from the declaring requirement's FILE node to each INSTANCE node in the cloned subtree (REQ-d00128-J)
- **`file_node()` returns None for INSTANCE nodes** -- INSTANCE nodes are virtual and have no physical file; `file_node()` now explicitly returns None for them. Navigate via INSTANCE edge to the original node to find the source file (REQ-d00128-L)

### Added (spec)

- **REQ-d00128-J, K, L** -- New assertions for DEFINES edges from FILE to INSTANCE nodes, INSTANCE nodes having no CONTAINS edges, and `file_node()` returning None for INSTANCE nodes

## [0.104.7] - 2026-03-13

### Added

- **Render-based save** -- `render_save()` persists dirty FILE nodes to disk by rendering their CONTAINS children, replacing the old `persistence.py` text surgery approach (REQ-d00132-A)
- **Consistency check** -- Optional rebuild-and-compare check after save proves round-trip fidelity; enabled via `consistency_check=True` parameter with a `rebuild_fn` callback (REQ-d00132-C)
- **Edge-derived references** -- Implements and Refines reference lists are derived from live graph edges during rendering, ensuring edge mutations are correctly reflected in output (REQ-d00132-F)

### Removed

- **BREAKING: `persistence.py` deleted** -- The `replay_mutations_to_disk()` and `check_for_external_changes()` functions are removed. All persistence is now handled by `render_save()` in `graph/render.py` (REQ-d00132-D)

### Changed

- **Mutation log cleared after save** -- The mutation log is cleared after a successful `render_save()`, consistent with the old behavior (REQ-d00132-E)
- **Safety branches** -- Safety branch creation remains in the MCP `save_mutations()` tool, called before `render_save()` (REQ-d00132-B)
- **`test_server_persistence.py` migrated** -- All persistence tests now use `render_save()` instead of `replay_mutations_to_disk()`

## [0.104.6] - 2026-03-13

### Added

- **Render protocol** -- Each `NodeKind` has a `render_node()` function that produces its text representation, enabling graph-to-file serialization (REQ-d00131-A)
- **REQUIREMENT rendering** -- Full requirement block rendering: header, metadata line, body text, assertions from STRUCTURES children, named sections, `*End*` marker with hash (REQ-d00131-B)
- **REMAINDER rendering** -- Raw text rendered verbatim (REQ-d00131-D)
- **USER_JOURNEY rendering** -- Full journey block rendering from stored body text (REQ-d00131-E)
- **CODE/TEST rendering** -- Comment line(s) rendered from stored `raw_text` field (REQ-d00131-F, REQ-d00131-G)
- **FILE rendering** -- `render_file()` walks CONTAINS children sorted by `render_order` edge metadata and concatenates their rendered output (REQ-d00131-I)
- **Order-independent assertion hashing** -- `compute_requirement_hash()` sorts individual assertion hashes lexicographically before combining, ensuring assertion reorder does not trigger change detection (REQ-d00131-J)
- **Builder stores render data** -- CODE and TEST nodes now store `raw_text`, REQUIREMENT nodes store `implements_refs`, `refines_refs`, `satisfies_refs` for render protocol

## [0.104.5] - 2026-03-13

### Added

- **Parameterized `iter_roots(kind)`** -- `TraceGraph.iter_roots()` accepts optional `NodeKind` filter: `iter_roots(NodeKind.FILE)` returns FILE nodes, `iter_roots(NodeKind.REQUIREMENT)` returns only REQ roots, etc. Default (no argument) preserves backward compatibility (REQ-d00130-A through REQ-d00130-D, REQ-d00130-F)
- **`iter_by_kind(kind)`** -- New iterator-API-consistent method equivalent to `nodes_by_kind()`, aligned with `iter_roots`/`iter_children` naming convention (REQ-d00130-E)

## [0.104.4] - 2026-03-13

### Removed

- **BREAKING: `SourceLocation` class deleted** -- File paths now accessed via `node.file_node().get_field("relative_path")` instead of `node.source.path` (REQ-d00129-A)
- **BREAKING: `GraphNode.source` field deleted** -- Line numbers now accessed via `node.get_field("parse_line")` and `node.get_field("parse_end_line")` (REQ-d00129-B, REQ-d00129-C)

### Changed

- **Consumer migration** -- All ~15 consumers (annotators, serializers, commands, MCP server, HTML/PDF generators, test-code linker, link suggester) migrated to use `file_node()` for file paths and `get_field("parse_line")` for line numbers (REQ-d00129-D, REQ-d00129-E, REQ-d00129-F)
- **`GraphNode.depth` excludes FILE parents** -- FILE nodes (structural containment) no longer count toward domain hierarchy depth
- **`_collect_source_files`** -- HTML generator now resolves relative paths from repo_root when collecting source files

## [0.104.3] - 2026-03-13

### Added

- **FILE node creation in build pipeline** -- `factory.py` creates `NodeKind.FILE` nodes with ID `file:<repo-relative-path>` for every scanned file (REQ-d00128-A)
- **FILE node content fields** -- Each FILE node stores `file_type`, `absolute_path`, `relative_path`, `repo`, `git_branch`, `git_commit` (REQ-d00128-B)
- **CONTAINS edges** -- FILE nodes are connected to top-level content nodes (REQUIREMENT, USER_JOURNEY, CODE, TEST, file-level REMAINDER) via `EdgeKind.CONTAINS` with `start_line`, `end_line`, and `render_order` metadata (REQ-d00128-D, REQ-d00128-E)
- **RemainderParser mandatory** -- RemainderParser is now always registered for SPEC, JOURNEY, CODE, and TEST file types, ensuring every line is claimed by some parser (REQ-d00128-G)
- **Git info captured per repo** -- `git_branch` and `git_commit` captured once per repository via `get_current_commit()` utility (REQ-d00128-C)
- **`GraphBuilder.register_file_node()`** -- New method to register FILE nodes in the builder's index without adding them to orphan candidates

### Changed

- **Orphan detection** -- Validate command now ignores FILE parents (CONTAINS edges) when checking for orphan requirements, preserving existing behavior (REQ-d00128-I)

## [0.104.2] - 2026-03-13

### Changed

- **BREAKING: `add_child()` removed** — All parent-child relationships now use `link()` with a typed `EdgeKind`; edge-less parent-child links eliminated (REQ-d00127-A)
- **BREAKING: `remove_child()` renamed to `unlink()`** — API symmetry with `link()`; identical behavior retained (REQ-d00127-B)
- **TEST_RESULT edge kind** — TEST_RESULT nodes now linked from TEST via `EdgeKind.YIELDS` (not `CONTAINS`), correcting the semantic relationship (REQ-d00127-E)
- **Builder assertions/sections** — Assertions and sections in `_add_requirement()`, `add_assertion()`, and template instantiation now use `link(..., EdgeKind.STRUCTURES)` instead of `add_child()`

### Added

- **Filtered traversal** — `iter_children()`, `iter_parents()`, `walk()`, `ancestors()` accept optional `edge_kinds` parameter; when provided, only nodes reachable via those edge kinds are returned; unfiltered (None default) is backwards compatible (REQ-d00127-C)
- **`file_node()` convenience** — `GraphNode.file_node()` walks incoming edges to find nearest `NodeKind.FILE` ancestor; returns None when no FILE parent exists (REQ-d00127-D)

## [0.104.1] - 2026-03-13

### Added

- **NodeKind.FILE** — New `FILE` enum member in `NodeKind` for representing source files as first-class graph nodes (REQ-d00126-A)
- **FileType enum** — New `FileType` enum (`SPEC`, `JOURNEY`, `CODE`, `TEST`, `RESULT`) classifying source files by domain role (REQ-d00126-B)
- **Structural edge kinds** — `EdgeKind.STRUCTURES`, `DEFINES`, `YIELDS` for domain-internal hierarchy, virtual node provenance, and test-result linking; none contribute to coverage (REQ-d00126-C, REQ-d00126-D)
- **Edge.metadata** — `dict[str, Any]` field on `Edge` dataclass for mutable annotations (line ranges, render order); excluded from `__eq__`/`__hash__` (REQ-d00126-E)

## [0.104.0] - 2026-03-12

### Added

- **ID Pattern System** — New `IdPatternConfig`, `IdResolver`, `ParsedId`, `TypeDef`, `ComponentFormat`, `AssertionFormat` dataclasses replacing `PatternConfig`/`PatternValidator`/`normalize_req_id`. Supports named aliases, configurable output forms, template compilation with short-form parsing, component normalization, and multi-assertion expansion via a single `IdResolver` authority class.

## [0.103.17] - 2026-03-12

### Added

- **Stereotype enum** — `Stereotype` enum (`CONCRETE`, `TEMPLATE`, `INSTANCE`) in `graph/relations.py` classifies nodes in the template-instance pattern (REQ-p00014-C)
- **INSTANCE EdgeKind** — `EdgeKind.INSTANCE` for connecting cloned template nodes to their originals; does not contribute to coverage (REQ-p00014-C)
- **Template instantiation** — `Satisfies: X` declarations now clone the template's REQ subtree with composite IDs (`declaring_id::original_id`), creating INSTANCE nodes with SATISFIES/INSTANCE edges; coverage computed through standard mechanism (REQ-p00014-B, REQ-d00069-H)
- **File-based attribution** — `Implements:` refs targeting template assertions are redirected to the correct instance clone using sibling refs in the same source file (REQ-p00014-D)
- **MCP stereotype serialization** — `_serialize_node_generic()` includes `stereotype` field in REQUIREMENT properties; INSTANCE edges included in parent/links sections
- **Viewer satisfies support** — card label updated to "Implements / Refines / Satisfies"; edge toggle cycles through all three kinds; add-relationship form includes Satisfies option

## [0.101.0] - 2026-03-09

### Added

- **Satisfies relationship** — `Satisfies:` metadata field declares compliance with a cross-cutting template requirement; per-instance `satisfies_coverage` metric tracks what fraction of the template's leaf assertions are covered within the declaring requirement's subtree; N/A declarations (`REQ-xxx-Y SHALL be NOT APPLICABLE`) exclude template assertions from the coverage denominator; `check_template_coverage()` health check reports gaps; template hash changes flag declaring requirements for review
- **Theme catalog system** — `theme.toml` and `help.toml` TOML data files as single source of truth for all UI colors, symbols, labels, and descriptions; `LegendCatalog` Python class with cached loader, CSS variable generation, and catalog entry lookup (REQ-p00006-A)
- **Multi-theme support** — arbitrary named themes via `.theme-*` CSS class selectors replacing the old `.dark-theme` approach; theme buttons in hamburger menu generated from catalog (REQ-p00006-A)
- **Dynamic page title** — browser tab shows `Elspais {version} ({repo_name}) -- PRD: N OPS: N DEV: N` in edit mode and `Elspais {version} -- Requirements Traceability` in view mode (REQ-p00006-A)
- **Foundation analysis command** — `elspais analysis` ranks requirements by structural importance using PageRank centrality, fan-in branch count, and uncovered dependent metrics; supports `--top`, `--weights`, `--level`, `--show`, `--include-code`, and `--format json` options (REQ-d00125)

### Changed

- **CSS custom properties migration** — all ~176 hardcoded hex colors across 16 CSS partial files replaced with `var(--token)` references generated from `theme.toml` (REQ-p00006-A)
- **Legend modal rewrite** — hardcoded legend content replaced with catalog-driven template loop over `catalog.grouped_entries()` (REQ-p00006-A)
- **Validation color descriptions** — `compute_validation_color()` now sources descriptions from catalog `validation_tiers` entries instead of hardcoded strings (REQ-p00006-A)

### Removed

- **`_dark-theme.css.j2`** — 287-line dark theme override file deleted; dark mode now handled entirely by CSS custom properties in `theme.toml` (REQ-p00006-A)

## [0.100.0] - 2026-03-09

### Added

- **Viewer branch indicator badge** — shows current branch name with colored status dot (green=clean, blue=dirty spec files, red=on main), pull button when remote is fast-forwardable, and warning icon when remote has diverged; polls `/api/git/status` every 60 seconds (REQ-p00004-C)
- **Viewer branch creation modal** — prompts for a branch name when toggling edit mode on main or when the viewer loads on main with dirty spec files; edit mode only activates after branch creation succeeds (REQ-p00004-D)
- **`git_status_summary()` utility function** — returns current branch name, main-branch detection, dirty spec file list, and remote divergence state; supports the viewer branch indicator badge (REQ-p00004-C)
- **`create_and_switch_branch()` utility function** — creates a new git branch and switches to it, using stash to preserve dirty working tree changes across the switch; supports the viewer branch creation modal (REQ-p00004-D)
- **`commit_and_push_spec_files()` utility function** — stages all modified spec files, commits with a message, and optionally pushes; refuses to operate on main/master branches; supports the viewer push modal (REQ-p00004-E)
- **`pull_ff_only()` utility function** — fetches from the remote tracking branch and merges with `--ff-only`; aborts if the merge is not fast-forwardable; handles timeout, no-remote, and diverged-history error cases; supports the viewer refresh/pull action (REQ-p00004-F)
- **Flask git sync endpoints** — `GET /api/git/status`, `POST /api/git/branch`, `POST /api/git/push`, `POST /api/git/pull` routes in the viewer server; delegates to git utility functions; push on main/master returns 403 (REQ-p00004-C, REQ-p00004-D, REQ-p00004-E, REQ-p00004-F)
- **Viewer push modal** — Push button in header (disabled on main or no dirty spec files) opens a modal showing branch name, modified spec files, and commit message input; flow: save mutations, commit, push; includes error handling and loading state (REQ-p00004-E)
- **Unsaved changes warning** — `beforeunload` handler warns when pending mutations exist (unsaved badge > 0) or uncommitted spec files exist (blue dot indicator), preventing accidental data loss (REQ-p00004-E)
- **E2E integration test for viewer git sync** — full workflow test covering `git_status_summary`, `create_and_switch_branch`, and `commit_and_push_spec_files` in sequence: init on main, dirty spec, create branch, verify carry, commit without push, verify clean (REQ-p00004-C, REQ-p00004-D, REQ-p00004-E)

## [0.99.0] - 2026-03-08

### Added

- **Viewer edit mode: pencil icons** — blue pencil icons on editable fields (title, assertion text) that scale on hover; visible whenever edit mode is active
- **Viewer edit mode: delete buttons** — delete assertions (× on each row) and requirements (× in card header) with confirmation dialogs and undo support
- **Viewer edit mode: relationship editor** — toggle implements/refines type with one click, delete relationships, add new relationships via inline form with searchable requirement dropdown and optional assertion-level targeting
- **Searchable requirement picker component** — reusable `createReqPicker()` with type-ahead search, keyboard navigation, 300ms debounce, and assertion list fetching

### Fixed

- **Edit-only elements not visible in edit mode** — inline `style="display:none;"` was overriding CSS rules due to higher specificity; now uses CSS-only visibility via `body.edit-mode .edit-only`

## [0.98.0] - 2026-03-08

### Added

- **Flask API: delete assertion and requirement endpoints** — `POST /api/mutate/assertion/delete` and `POST /api/mutate/requirement/delete` with `confirm=true` validation
- **Default viewer port changed from 5000 to 5001** — avoids conflict with macOS AirPlay Receiver

## [0.97.0] - 2026-03-08

### Added

- **7 e2e subprocess tests** for JUnit/SARIF formats and `--include-passing-details` flag — validates XML/JSON output, file output via `-o`, and flag acceptance

## [0.96.0] - 2026-03-08

### Added

- **`--skip-passing-details` / `--include-passing-details` for `elspais health`** — controls whether passing checks include verbose detail in output. `--skip-passing-details` is the default, suppressing per-finding detail for passing checks. `--include-passing-details` adds detail keys (text), `<details>` blocks (markdown), or `<system-out>` elements (junit). JSON always includes full findings; SARIF always omits passing checks

## [0.95.0] - 2026-03-08

### Added

- **`--format sarif` for `elspais health`** — SARIF v2.1.0 JSON output for GitHub Code Scanning and static analysis dashboards. One `reportingDescriptor` per unique failing check, one `result` per `HealthFinding` with physical locations (file path, line number). Passing checks omitted. Severity mapped to SARIF levels (`error`→`"error"`, `warning`→`"warning"`, `info`→`"note"`). Coverage stats in `run.properties`

## [0.94.0] - 2026-03-07

### Added

- **Health check findings enrichment** — all check functions now populate `HealthFinding` instances with per-item detail (node IDs, file paths, line numbers) for duplicates, unresolved references, hierarchy violations, orphans, format rules, code/test references, and test results

## [0.93.0] - 2026-03-07

### Added

- **`HealthFinding` dataclass** — per-finding detail model with `message`, `file_path`, `line`, `node_id`, and `related` fields; serialized in JSON `to_dict()` output; prerequisite for SARIF format support

## [0.92.0] - 2026-03-07

### Added

- **`--format junit` for `elspais health`** — JUnit XML output for CI test-reporting dashboards (GitHub Actions, Jenkins, GitLab CI). Categories map to `<testsuite>` elements, checks to `<testcase>` elements, failures to `<failure>`, warnings to `<system-err>`, and info to `<system-out>`
- **REQ-p00013: Automated Testing requirement** — new PRD-level requirement covering unit, e2e, self-validation, workflow, and MCP protocol testing
- **E2E test infrastructure** — `tests/e2e/` directory with shared conftest (`run_elspais()`, skip markers, path constants)
- **27 CLI subprocess tests** — end-to-end tests covering version, doctor, summary, trace, graph, config, example, docs, changed, rules, health, init, and fix commands
- **`browser` pytest marker** — for Playwright-based browser tests
- **11 self-validation tests** — e2e tests running elspais against its own repository (health, doctor, summary, trace, graph, subdirectory detection)
- **6 multi-command workflow tests** — cross-command consistency tests (init→health, health/summary consistency, trace JSON/CSV format, init→config, fix→health, summary idempotency)
- **`--port` argument for viewer command** — specify server port directly, bypassing interactive port conflict prompts
- **6 Playwright browser tests** — viewer page load, API endpoints, search filtering, and requirement detail interaction
- **8 extended MCP protocol tests** — search, get_requirement, get_hierarchy, project_summary, cursor pagination, and mutation/undo roundtrip via stdio transport

## [0.85.5] - 2026-03-06

### Removed

- **`analyze` command** — deleted entirely; hierarchy views available via `trace --view`, coverage via `coverage`
- **`validate` CLI entry point** — removed subparser and dispatch; validation logic retained as library module for `fix` command

### Changed

- **CLI epilog** — updated examples to reference `health`, `coverage`, and composable reports
- **docs/cli/** — updated 7 doc files to reference `health` instead of `validate`/`analyze`

## [0.85.4] - 2026-03-06

### Changed

- **Extract viewer command** — moved Flask server logic from `trace.py` to `commands/viewer.py`
  - `elspais viewer` now dispatches to `viewer.run()` instead of `trace.run_viewer()`
  - `trace --edit-mode` and `trace --server` delegate to `viewer._run_server()`
  - `trace --view` and `--embed-content` remain on trace (static HTML generation)

## [0.85.3] - 2026-03-06

### Added

- **Composable multi-section reports** — `elspais health coverage trace --format markdown` (REQ-d00085)
  - Multiple section names as positional args, rendered in order and concatenated
  - Shared flags (`--format`, `-o`, `-q`, `-v`, `--lenient`) apply globally across sections
  - Exit code is worst-of-all-sections (non-zero if any section has errors/warnings)
  - Single-section invocation behaves identically to standalone command
  - Invalid format/section combinations produce clear errors
  - `render_section()` API on health, coverage, and trace for programmatic use

### Changed

- **`elspais trace`** — `--report` renamed to `--preset`, added `--body`/`--assertions`/`--tests` detail flags, coverage columns (Implemented, Validated, Passing) from RollupMetrics (REQ-d00084-B+C+D)

## [0.85.2] - 2026-03-06

### Changed

- **`elspais health` exit codes** — warnings now cause non-zero exit by default (REQ-d00080-A)
  - `--lenient` flag allows warnings to pass without affecting exit code
  - `-q`/`--quiet` flag for summary-line-only output
  - `--format text|markdown|json` replaces `-j`/`--json` (still supported as alias)
  - Markdown output format for health reports

## [0.85.1] - 2026-03-06

### Added

- **`elspais coverage`** — new coverage report command with text, markdown, json, csv output (REQ-d00086)
  - Per-level summary: requirements, assertions, implemented/validated/passing percentages
  - Per-requirement assertion coverage: implemented (code refs), validated (test refs), passing (test results)
  - Excludes Draft/Deprecated requirements from counts

## [0.85.0] - 2026-03-06

### Changed

- **Spec: Unified Report System** — new requirements for composable CLI report output (REQ-d00085, REQ-d00086)
  - REQ-d00085: Unified Report Composition — multi-command composition, shared flags, `--lenient`
  - REQ-d00086: Coverage Report Section — per-level and per-assertion coverage in text/markdown/json/csv
  - REQ-d00084: Trace Command — added column presets, detail flags, coverage columns
  - REQ-d00080: Exit codes — warnings cause non-zero by default, `--lenient` to relax
  - REQ-d00083: Validate Command — deprecated, superseded by health
- Removed `--depth` dead code from CLI and reformat_cmd

## [0.84.3] - 2026-03-04

### Fixed

- **`fix REQ-xxx` fails with "belongs to a different requirement"**: Subheadings inside a requirement body (e.g., `### OS-Level Notifications`) were falsely detected as requirement boundaries because `_find_next_req_header` used the overly broad regex `^#+ [A-Z]+-`. Narrowed the pattern to only match headings with the configured requirement prefix (CUR-1003, REQ-p00004-A)

## [0.84.2] - 2026-02-26

### Fixed

- **CI-unsafe exit codes**: `doctor`, `health`, and `validate` now exit non-zero on misconfigured projects (CUR-1036, REQ-d00080)
  - Reclassified 7 doctor checks from `severity="warning"` to `severity="error"` so `HealthReport.is_healthy` reflects failures
  - `validate` exits 1 when spec directories contain zero requirements
  - `doctor` validates `[associated]` section for associated project types
  - `validate --mode combined` exits 1 for missing, misconfigured, or empty associate paths

## [0.84.0] - 2026-02-21

### Added

- **`trace --path DIR`**: Specify repository root for trace output without `cd`-ing into it; works with all trace modes (`--format`, `--view`, `--server`, `--graph-json`) (REQ-p00003-A)

## [0.83.0] - 2026-02-21

### Fixed

- **MCP coverage always 0%**: Moved `annotate_coverage()` into `build_graph()` so all consumers (MCP, HTML, Flask) get coverage metrics automatically (REQ-d00055-D, REQ-o00061-B)
- **Graph JSON serialization**: Filter non-JSON-serializable metric values (like `RollupMetrics`) from `serialize_node()` output

### Removed

- Redundant `_annotate_coverage()` calls from `HTMLGenerator.generate()` and Flask server `_build_review_context()`

## [0.80.0] - 2026-02-20

### Added

- **Multi-term search engine** (`mcp/search.py`): Query parser with AND/OR operators, parenthesized grouping, exclusion (`-term`), exact keyword matching (`=term`), and quoted phrases (`"phrase"`) (REQ-d00061-F through REQ-d00061-M)
- **Relevance scoring**: Search results scored by field match quality (ID=100, title=50, keyword-exact=40, keyword-substring=25, body=10) and sorted by score descending (REQ-d00061-L)
- **Flask search passthrough**: `/api/search` now accepts `limit` and `regex` query parameters (REQ-d00061-E, REQ-d00061-C)
- **GUI tree text filter**: Toolbar text input filters the nav tree via server-side search with debounced API calls, intersecting with existing button/dropdown filters (REQ-o00060-C)

### Changed

- **MCP tool docstrings**: Updated `search()`, `scoped_search()`, and `discover_requirements()` to document multi-term query syntax and scoring

## [0.79.0] - 2026-02-20

### Added

- **`elspais associate` command**: Manage associated repo links
- **Environment variable overrides**: Now support JSON lists and booleans

## [0.78.0] - 2026-02-20

### Added

- **`elspais doctor` command**: Environment and installation diagnostics
- **Configuration refactor**: Checks moved from `health` to `doctor` (shared between both commands)
- **Diagnostic messages**: Lay-person friendly output

## [0.73.2] - 2026-02-17

### Added

- **`elspais pdf --overview`**: Generate stakeholder-oriented PDFs with only PRD-level requirements. Optional `--max-depth` flag limits core PRD graph depth while always including associated-repo PRDs (REQ-p00080-F)

### Fixed

- **Homebrew pipeline**: Use PAT for PR creation and label automation to enable fully hands-free pipeline

## [0.73.1] - 2026-02-17

### Fixed

- **Homebrew pipeline**: Fully automated bottle build and publish (no manual labeling step)
- **Formula conflicts**: Added `conflicts_with` between `elspais` and `elspais-core` formulas

## [0.73.0] - 2026-02-15

### Added

- **`elspais pdf` command**: Compile spec files into a professional PDF document using Pandoc + xelatex. Groups requirements by level (PRD/OPS/DEV), orders files by graph depth, generates table of contents, per-requirement page breaks, and an alphabetized topic index with hyperlinks. Custom LaTeX template included (REQ-p00080)

## [0.72.0] - 2026-02-14

### Changed

- **MCP server instructions**: Document `scoped_search`, `minimize_requirement_set`, and `discover_requirements` tools in Quick Start, Tools Overview, and Common Patterns sections

## [0.71.0] - 2026-02-14

### Added

- **`discover_requirements` MCP tool**: Chains `scoped_search` with `minimize_requirement_set` to search within a subgraph and return only the most-specific matches, pruning ancestor requirements superseded by more-specific descendants (REQ-o00071, REQ-d00079)

## [0.70.0] - 2026-02-14

### Added

- **Cursor support for `scoped_search`**: Register `scoped_search` as a cursor query type, enabling paginated iteration through scoped search results via `open_cursor("scoped_search", {...})` (REQ-o00068-F, REQ-d00076-B)

## [0.69.0] - 2026-02-14

### Added

- **`scoped_search` MCP tool**: Restricts keyword search to descendants or ancestors of a scope node, preventing over-matching across unrelated parts of the graph. Supports assertion text matching via `include_assertions` parameter (REQ-o00070, REQ-d00078)

## [0.68.0] - 2026-02-14

### Added

- **`minimize_requirement_set` MCP tool**: Prunes a set of requirement IDs to most-specific members by removing ancestors covered by more-specific descendants. Returns minimal set, pruned items with `superseded_by` metadata, and stats (REQ-o00069, REQ-d00077)

## [0.67.0] - 2026-02-14

### Changed

- **Extract `_matches_query()` helper**: Refactored per-node matching logic out of `_search()` into a reusable `_matches_query()` function for shared use by `search()` and future `scoped_search()` (REQ-d00061-B, REQ-d00061-C, REQ-p00050-D)

## [0.65.0] - 2026-02-13

### Added

- **CLI-based associate registration**: Register associate repositories via `elspais config add associates.paths /path/to/repo` instead of manually editing config files. Auto-discovers associate identity (name, prefix, spec path) from the target repo's `.elspais.toml` (REQ-p00005-C, REQ-p00005-D)
- **Structured error reporting for associate paths**: Invalid associate paths return error messages instead of silently skipping, enabling CI pipelines to detect misconfigured associates (REQ-p00005-E)
- **Subtree extraction MCP tool**: `get_subtree(root_id, depth, include_kinds, format)` extracts a subgraph rooted at any node with three output formats (markdown, flat JSON, nested JSON). Supports depth limiting, kind filtering, DAG deduplication, and includes coverage summary stats (REQ-o00067, REQ-d00075)
- **Cursor protocol for incremental iteration**: Three new MCP tools (`open_cursor`, `cursor_next`, `cursor_info`) enable LLMs to iterate query results one item at a time. Supports 6 query types (subtree, search, hierarchy, query_nodes, test_coverage, uncovered_assertions) and 3 batch_size modes for controlling item granularity (REQ-o00068, REQ-d00076)

## [0.63.3] - 2026-02-12

### Changed

- **Cleanup and file renames**: Renamed `_header-edit.css.j2` to `_header.css.j2` and `_file-viewer-edit.css.j2` to `_file-viewer.css.j2` since they now serve both modes. Deleted dead `_tabs.html.j2` (REQ-p00006-A)

## [0.63.2] - 2026-02-12

### Changed

- **Unified cookie persistence**: Single `elspais_trace_state` cookie shared between view and edit modes, replacing mode-specific `elspais_trace_edit_state`/`elspais_trace_view_state`. State (theme, font size, open cards, filters, panel widths) now seamlessly transfers between modes (REQ-p00006-A)
- Added `clearState()` function for programmatic cookie reset
- Cookie version bumped to v9

## [0.63.1] - 2026-02-12

### Added

- **Search in view mode**: Extracted search into shared `_search.js.j2` partial, enabling search in both static HTML and edit mode. `Ctrl+K` shortcut works in both modes (REQ-p00006-A, REQ-p00006-B)
- **New toolbar filter toggles**: Added Hide Deprecated, Hide Roadmap, Code Refs, and Indirect Coverage toggle checkboxes to the unified filter toolbar
- Cookie version bumped to v8 for new filter state keys

## [0.63.0] - 2026-02-12

### Changed

- **Unified 3-panel layout for both view and edit modes**: Replaced the view-mode table layout with the 3-panel layout (nav tree + card stack + file viewer) already used by edit mode. Both modes now share the same interactive layout, state management (`editState`), and cookie persistence (REQ-p00006-A, REQ-d00010-A)
- **Unified file viewer**: Single implementation using `apiFetch()` for both modes with vscode:// link interception, markdown rendering toggle, and syntax highlighting
- **Unified header and toolbar**: Edit-mode header (with dynamic stats via JS) and toolbar (git filters, status/coverage dropdowns) now serve both modes, with edit-specific buttons wrapped in mode conditionals
- **Dark theme support in view mode**: Added `pygments_css_dark` generation to HTMLGenerator for syntax highlighting in dark theme

### Removed

- View-mode table layout, flat/hierarchical view toggle, table column filters
- Dead CSS: `_table.css.j2`, `_tree-structure.css.j2`, `_code-test-rows.css.j2`, `_responsive.css.j2`, `_tabs.css.j2`, `_header.css.j2`, `_file-viewer.css.j2`
- Dead JS: `_filter-engine.js.j2`, `_journey-engine.js.j2`

## [0.62.0] - 2026-02-12

### Added

- **Embedded data layer for unified trace viewer**: View-mode static HTML now embeds node index, coverage index, and status data as JSON script tags, enabling a unified `apiFetch()` adapter that routes to embedded data in view mode and live API in edit mode (REQ-p00006-A, REQ-p00006-B, REQ-p00006-C)

## [0.61.0] - 2026-02-11

### Added

- **`elspais install local`**: Install local source as editable pipx/uv install, replacing the global PyPI version for dev testing
- **`elspais uninstall local`**: Revert to PyPI release version with optional `--version` pinning
- Auto-detects pipx/uv, source root via `pyproject.toml`, and currently installed extras

## [0.54.1] - 2026-02-10

### Changed

- **Python 3.10+ support**: Lowered minimum Python version from 3.12 to 3.10, added 3.10/3.11 to CI test matrix
- **Auto version bump**: PRs automatically get a version bump based on changed files — patch for docs/tests/specs, minor for source changes
- **Auto release**: Merging to main with a version change automatically creates a GitHub release, triggering PyPI publish and Homebrew tap update

## [0.54.0] - 2026-02-10

### Added

- **Trace-edit interactive server**: Interactive spec editing via Flask with `spec_writer` mutations (REQ-d00010-A, REQ-o00063-G/H/I)
- **Agent-assisted link suggestion engine**: Heuristic-based link suggestions for unlinked test nodes (REQ-o00065, REQ-d00072/73/74)
- **CI/CD pipelines**: CI and PR validation workflows, PyPI publish and Homebrew tap update automation (REQ-o00066)

### Changed

- **Replaced gitleaks with TruffleHog**: Secret scanning now uses TruffleHog (REQ-o00066-D)
- **Fixed code directory scanning**: `build_graph()` now correctly scans `[directories].code` config (REQ-d00054-A)

## [0.51.0] - 2026-02-07

### Changed

- **Consolidated spec file I/O**: All spec-file mutation helpers (`modify_implements`, `modify_status`, `move_requirement`, `change_reference_type`, `update_hash_in_file`) now live in `utilities/spec_writer.py`. Both CLI (`edit.py`, `hash_cmd.py`) and MCP (`server.py`) import from this single module.
- **Fixed encoding bug**: 4 spec-file writes in `edit.py` were missing `encoding="utf-8"` — now all writes go through `spec_writer` which uses explicit UTF-8 encoding.
- **Relocated `mcp/file_mutations.py`**: Core file I/O moved to `utilities/spec_writer.py`; `mcp/file_mutations.py` is now a backward-compatible re-export shim.

## [0.50.0] - 2026-02-07

### Added

- **MCP round-trip fidelity**: `get_requirement()` now returns enough data to reconstruct the original requirement from the graph. Parser computes line numbers on assertions and sections, builder creates `SourceLocation` on all child nodes with document-order insertion, and MCP serializer returns a flat `children` list with `kind`/`line` tags and `edge_kind` on parent entries.
- **Linking convention documentation**: New `docs/cli/linking.md` topic for `elspais docs linking` — authoritative reference for all requirement linking patterns (code comments, test names, multi-assertion syntax, direct vs indirect linking).

## [0.49.0] - 2026-02-07

### Added

- **Configurable satellite kinds**: `[graph].satellite_kinds` in `.elspais.toml` controls which node kinds are treated as satellite (don't count as meaningful children for root/orphan classification). Defaults to `["assertion", "result"]`.

## [0.48.0] - 2026-02-07

### Changed

- **Unified root vs orphan classification**: Parentless nodes are now classified as roots only when they have at least one meaningful (non-satellite) child. Nodes with only ASSERTION or TEST_RESULT children are classified as orphans. USER_JOURNEY nodes follow the same rule. This replaces the previous logic where all parentless REQUIREMENTs and all USER_JOURNEYs were unconditionally treated as roots.
- **Simplified orphan detection in CLI**: Removed domain-level REQUIREMENT orphan loops from `analyze.py` and `health.py` — the unified graph-level classification now handles all node kinds.

### Added

- **REQ-d00071** specification: Formal requirement for unified root vs orphan classification with 4 assertions (A-D).
- **`_SATELLITE_KINDS` constant**: Defines ASSERTION and TEST_RESULT as satellite kinds that don't count as meaningful children.

## [0.47.0] - 2026-02-06

### Added

- **Indirect coverage toggle** for trace view: whole-requirement tests (tests targeting a requirement without assertion suffixes) can now count as covering all assertions. A new "Indirect coverage" toggle in the toolbar switches between strict traceability view and a progress-indicator view.
- **`CoverageSource.INDIRECT`**: New coverage source type for whole-requirement test contributions, alongside existing DIRECT, EXPLICIT, and INFERRED sources.
- **Dual coverage metrics**: `RollupMetrics` now tracks both `referenced_pct` (strict, excludes indirect) and `indirect_referenced_pct` (includes indirect). `validated_with_indirect` counts assertions validated when including whole-req passing tests.
- **`data-coverage-indirect` attribute**: Tree rows carry both strict and indirect coverage data for client-side toggle without page reload.
- **JNY→REQ linking via `Addresses:` field**: User journeys can now reference the requirements they address using `Addresses: REQ-xxx, REQ-yyy` in the journey block. Parsed into `EdgeKind.ADDRESSES` edges in the traceability graph.
- **Trace view journey cards show linked REQs**: Addressed requirements appear as clickable pill badges on journey cards. Clicking navigates to the requirement in the requirements tab with a flash highlight.
- **Journey search includes addresses**: The journey tab search bar now matches against referenced requirement IDs.
- **Index regenerate includes Addresses column**: `elspais index regenerate` now includes an Addresses column in the User Journeys section.
- **Index validate checks JNY IDs**: `elspais index validate` now verifies that all JNY IDs in the graph appear in INDEX.md and vice versa.

## [0.46.0] - 2026-02-07

### Added

- **Inline file viewer panel** for `elspais trace --view --embed-content`: clicking file links now opens source files in a right-side panel with syntax-highlighted content and stable line numbers, instead of opening VS Code externally. Supports 500+ languages via Pygments.
- **Syntax highlighting** powered by Pygments (new optional dependency under `trace-view` extra). Highlighting runs at generation time — no client-side JS library needed.
- **Resizable split-pane layout**: drag the divider between the trace table and file viewer. Panel width persists via cookies.
- **Markdown rendered view**: `.md` files show a toggle between "Rendered" and "Source" views.
- **Graceful fallback**: without `--embed-content`, file links open in VS Code as before.

### Changed

- **Optional dependency**: Added `pygments>=2.0` to `trace-view`, `trace-review`, and `all` extras.

## [0.45.0] - 2026-02-06

### Fixed

- **TOML parser: multi-line arrays corrupted during `config add` round-trips** — replaced custom TOML parser/serializer with `tomlkit` library for full TOML 1.0 compliance. Multi-line arrays and arrays containing comma-delimited strings are now handled correctly. Comments and formatting are preserved during config modifications.

### Changed

- **Core dependency**: Added `tomlkit>=0.12` as the sole core dependency (pure Python, no transitive deps). The custom TOML parser has been removed.

## [0.44.0] - 2026-02-04

### Added

- **Configurable hash mode** (`[validation].hash_mode` in `.elspais.toml`):
  - `full-text`: Hash every line between header and footer, no normalization.
  - `normalized-text` (default): Hash assertion text only with cosmetic normalization. Invariant over trailing whitespace, line wrapping, multiple spaces, and non-assertion body text changes.
  - Documented in `spec/requirements-spec.md` Hash Definition section.

## [0.43.5] - 2026-01-29

### Changed

- **Generalized keyword search API for all node kinds** (`graph/annotators.py`):
  - `annotate_keywords()` now annotates ALL node kinds with text content:
    - REQUIREMENT: title + child assertion text
    - ASSERTION: SHALL statement (label)
    - USER_JOURNEY: title + actor + goal + description
    - REMAINDER: label + raw_text
    - CODE, TEST, TEST_RESULT: label only
  - `find_by_keywords()` accepts optional `kind: NodeKind | None` parameter
    - `kind=None` (default) searches all nodes
    - `kind=NodeKind.ASSERTION` searches only assertions
  - `collect_all_keywords()` accepts optional `kind` parameter similarly
  - 12 new tests in `tests/graph/test_keyword_extraction_generalized.py`

- **MCP server refactored to use public graph API**:
  - `_find_assertions_by_keywords()` now uses `find_by_keywords(..., kind=NodeKind.ASSERTION)`
  - `_get_uncovered_assertions()` uses `nodes_by_kind(NodeKind.ASSERTION)`
  - Removed direct `_index.values()` access (encapsulation violation)

## [0.43.4] - 2026-01-29

### Changed

- **TestParser, JUnitXMLParser, PytestJSONParser refactored** to use shared reference config:
  - All three parsers now accept optional `PatternConfig` and `ReferenceResolver`
  - Removed hardcoded regex patterns from all parsers
  - TestParser: Custom comment pattern for `# Tests REQ-xxx` syntax (no colon)
  - Result parsers: Use `extract_ids_from_text()` from reference_config.py
  - Backward compatible - all work without explicit config

### Fixed

- **Assertion matching negative lookahead**: Added `(?![a-z])` in `build_id_pattern()` to prevent
  matching lowercase letters as assertion suffixes (e.g., `test_REQ_p00001_login` no longer
  captures "l" as an assertion)

## [0.43.3] - 2026-01-29

### Changed

- **CodeParser refactored to use shared reference config** (`graph/parsers/code.py`):
  - Now accepts optional `PatternConfig` and `ReferenceResolver` in constructor
  - Patterns built dynamically per-file using `reference_config.py` infrastructure
  - Removed hardcoded class-level regex patterns (`IMPLEMENTS_PATTERN`, `VALIDATES_PATTERN`, etc.)
  - Preserves full multi-line block parsing capability
  - Backward compatible - works without config (uses defaults)
  - 20 new tests covering custom configs, separators, case sensitivity, and block styles

## [0.43.2] - 2026-01-29

### Added

- **Reference Pattern Builder Module** (`utilities/reference_config.py`): New module for unified pattern building
  - `ReferenceConfig` dataclass: Configuration for reference pattern matching (separators, case sensitivity, etc.)
  - `ReferenceOverride` dataclass: File-type/directory-based override rules with glob matching
  - `ReferenceResolver` class: Single entry point for parsers to get merged configuration
  - Pattern builder functions:
    - `build_id_pattern()`: Build regex for requirement IDs with configurable separators
    - `build_comment_pattern()`: Build regex for `# Implements:` style comments
    - `build_block_header_pattern()`: Build regex for multi-line block headers
    - `build_block_ref_pattern()`: Build regex for block reference lines
    - `extract_ids_from_text()`: Extract all requirement IDs from text
    - `normalize_extracted_id()`: Normalize IDs to canonical format
  - 40 comprehensive unit tests in `tests/core/test_reference_config.py`

## [0.43.1] - 2026-01-29

### Added

- **Unified `[references]` configuration**: New config section for configurable reference parsing
  - `references.defaults.separators`: Separator characters for requirement IDs (default: `["-", "_"]`)
  - `references.defaults.case_sensitive`: Case sensitivity for matching (default: `false`)
  - `references.defaults.prefix_optional`: Whether REQ prefix is required (default: `false`)
  - `references.defaults.comment_styles`: Recognized comment markers (default: `["#", "//", "--"]`)
  - `references.defaults.keywords`: Keywords for implements/validates/refines references
  - `references.overrides`: File-type specific override patterns (empty by default)

## [0.43.0] - 2026-01-29

### Fixed

- **TestParser regex bug**: Fixed assertion-level test references not being captured.
  - Tests named `test_REQ_d00060_A_description` now correctly validate assertion `REQ-d00060-A`
  - Supports multi-assertion syntax: `test_REQ_d00060_A_B_description` → validates `REQ-d00060-A-B`
  - Coverage percentage now correctly reflects assertion-level test coverage

### Added

- New tests for assertion-level reference parsing in `test_test_parser.py`
- Created `docs/NEW_SPECS.md` for tracking proposed requirements during coverage analysis

## [0.42.0] - 2026-01-29

### Added

- **MCP Test Coverage Tools (Phase 6)**: New tools for analyzing test-requirement relationships:
  - `get_test_coverage(req_id)` - Returns TEST nodes that reference a requirement:
    - Lists test_nodes with their file and name
    - Lists result_nodes with pass/fail status
    - Identifies covered and uncovered assertions
    - Calculates coverage percentage
  - `get_uncovered_assertions(req_id=None)` - Finds assertions lacking test coverage:
    - When req_id is None, scans all requirements
    - Returns assertion id, text, label, and parent requirement context
    - Results sorted by parent requirement ID
  - `find_assertions_by_keywords(keywords, match_all=True)` - Searches assertion text:
    - Complements `find_by_keywords()` which searches requirement titles
    - Supports AND (match_all=True) and OR (match_all=False) logic
    - Case-insensitive matching

### Specification

- Added requirements to `spec/08-mcp-server.md`:
  - REQ-o00064: MCP Test Coverage Analysis Tools (OPS level)
  - REQ-d00066: Test Coverage Tool Implementation
  - REQ-d00067: Uncovered Assertions Tool Implementation
  - REQ-d00068: Assertion Keyword Search Tool Implementation

### Technical

- 14 new tests in `tests/mcp/test_mcp_coverage.py` with REQ-assertion naming pattern
- All coverage tools use iterator-only graph API per REQ-p00050-B

## [0.41.0] - 2026-01-29

### Added

- **MCP Dogfooding (Phase 5)**: Validated MCP server utility by improving test traceability:
  - Added 5 new tests with REQ-assertion naming pattern (e.g., `test_REQ_d00050_E_idempotent`)
  - Tests for REQ-d00050-E (annotator idempotency) and REQ-d00051-F (no duplicate iteration)
  - TEST nodes now automatically link to requirements via name pattern matching

### Documentation

- `docs/phase5-dogfooding-report.md`: Comprehensive dogfooding analysis with:
  - Test-requirement mapping table for `tests/core/test_annotators.py`
  - MCP tool ergonomic issues and suggested improvements
  - Before/after traceability metrics verification

### Technical

- Graph node count increased from 346 to 398 after test improvements
- TEST nodes: 36 → 75, TEST_RESULT nodes: 17 → 30

## [0.40.0] - 2026-01-29

### Added

- **Keyword Extraction & Search (Phase 4)**: Automatic keyword extraction and search for requirements:
  - `extract_keywords(text)` - Extract meaningful keywords from text, filtering stopwords
  - `annotate_keywords(graph)` - Annotate all requirements with keywords from title and assertions
  - `find_by_keywords(graph, keywords)` - Find requirements matching keywords (AND/OR logic)
  - `collect_all_keywords(graph)` - Get all unique keywords in the graph
  - Keywords stored in `node.get_field("keywords")` as list of lowercase strings

- **MCP Keyword Search Tools**: New MCP tools for keyword-based requirement discovery:
  - `find_by_keywords(keywords, match_all)` - Search by keywords with AND/OR matching
  - `get_all_keywords()` - List all available keywords for discovery
  - Enhanced `search()` to support `field="keywords"` for keyword searches

### Technical

- 29 new keyword tests (19 annotator + 10 MCP)
- STOPWORDS constant with 100+ common words filtered from keywords

## [0.39.0] - 2026-01-29

### Added

- **MCP File Mutation Tools (Phase 3.1)**: File-based mutation API for AI agents to modify spec files on disk:
  - `change_reference_type(req_id, target_id, new_type, save_branch)` - Change Implements/Refines relationships
  - `move_requirement(req_id, target_file, save_branch)` - Relocate requirements between spec files
  - `restore_from_safety_branch(branch_name)` - Revert file changes from safety branch
  - `list_safety_branches()` - List available safety branches for rollback
  - Auto-refresh graph after file mutations (REQ-o00063-F)
  - Optional `save_branch=True` creates timestamped safety branch before modification

- **Git Safety Branch Utilities**: New utilities in `utilities/git.py` for file mutation safety:
  - `create_safety_branch(repo_root, req_id)` - Create timestamped safety branch
  - `list_safety_branches(repo_root)` - List all `safety/*` branches
  - `get_current_branch(repo_root)` - Get current branch name
  - `restore_from_safety_branch(repo_root, branch_name)` - Restore spec/ from branch
  - `delete_safety_branch(repo_root, branch_name)` - Remove safety branch

### Technical

- Implements REQ-o00063: MCP File Mutation Tools (4 new tools)
- 14 new file mutation tests, 82 total MCP tests

## [0.38.0] - 2026-01-28

### Added

- **MCP Graph Mutation Tools (Phase 3.2)**: Complete in-memory graph mutation API for AI agents:
  - **Node mutations**: `mutate_rename_node()`, `mutate_update_title()`, `mutate_change_status()`, `mutate_add_requirement()`, `mutate_delete_requirement()`
  - **Assertion mutations**: `mutate_add_assertion()`, `mutate_update_assertion()`, `mutate_delete_assertion()`, `mutate_rename_assertion()`
  - **Edge mutations**: `mutate_add_edge()`, `mutate_change_edge_kind()`, `mutate_delete_edge()`, `mutate_fix_broken_reference()`
  - **Undo operations**: `undo_last_mutation()`, `undo_to_mutation()`, `get_mutation_log()`
  - **Inspection tools**: `get_orphaned_nodes()`, `get_broken_references()`
  - All destructive operations require `confirm=True` for safety (REQ-o00062-F)
  - All mutations return `MutationEntry` for audit trail (REQ-o00062-E)
  - Pure delegation pattern - MCP layer only validates params and calls TraceGraph methods (REQ-d00065)

### Technical

- Implements REQ-o00062: MCP Graph Mutation Tools (17 new tools)
- Implements REQ-d00065: Mutation Tool Delegation pattern
- 39 new mutation tests, 68 total MCP tests

## [0.37.0] - 2026-01-28

### Added

- **MCP Server Documentation (Phase 2.2)**: Comprehensive documentation for AI agents and users:
  - `docs/cli/mcp.md` - User-facing documentation for the MCP server with all tool descriptions
  - MCP server `instructions` parameter for AI agents with quick start guide and usage patterns
  - New `elspais docs mcp` command to view MCP documentation from CLI
  - Updated docs topic list to include mcp topic (11 topics total)

### Technical

- 4 new documentation tests (64 total doc sync tests, 93 total MCP + doc tests)

## [0.36.0] - 2026-01-28

### Added

- **MCP Workspace Context Tools (Phase 2.1)**: New tools for workspace and project information:
  - `get_workspace_info()` - Returns repo path, project name, and configuration summary
  - `get_project_summary()` - Returns requirement counts by level, coverage statistics, and change metrics
  - Uses `count_by_level()` from annotators module per REQ-o00061-C
  - Reads config from unified config system per REQ-o00061-D
  - 10 new tests for workspace tools (29 total MCP tests)

### Technical

- Implements REQ-o00061: MCP Workspace Context Tools

## [0.35.0] - 2026-01-28

### Added

- **MCP Server Core Tools (Phase 1)**: Minimal MCP server implementation with graph-as-single-source-of-truth:
  - `get_graph_status()` - Node counts, root count, detection flags
  - `refresh_graph(full)` - Force graph rebuild from spec files
  - `search(query, field, regex)` - Search requirements by ID, title, or content
  - `get_requirement(req_id)` - Full requirement details with assertions
  - `get_hierarchy(req_id)` - Ancestors and children navigation
  - All tools consume TraceGraph directly via iterator-only API (REQ-p00060-B)
  - Serializers read from `node.get_field()` and `node.get_label()`
  - 19 tests verifying proper graph API usage

### Technical

- Implements REQ-o00060: MCP Core Query Tools
- Implements REQ-d00060-65: Tool implementations and serializers

## [0.34.1] - 2026-01-28

### Added

- **MCP Server Specification**: Created `spec/08-mcp-server.md` defining the MCP server architecture:
  - PRD-level: REQ-p00060 - MCP Server for AI-Driven Requirements Management
  - OPS-level: REQ-o00060 (Core Query), REQ-o00061 (Workspace Context), REQ-o00062 (Graph Mutations), REQ-o00063 (File Mutations)
  - DEV-level: REQ-d00060-65 (Tool implementations, serializers, mutation delegation)
- **Graph-as-Source-of-Truth**: MCP spec enforces REQ-p00050-B - all tools consume TraceGraph directly without intermediate data structures
- **Architecture Diagram**: Spec includes diagram showing MCP server layer consuming TraceGraph via iterator and mutation APIs

## [0.31.0] - 2026-01-28

### Added

- **MCP Mutator Tools**: The MCP server now exposes TraceGraph mutation methods for AI-driven requirement management:
  - **Node Mutations**: `mutate_rename_node()`, `mutate_update_title()`, `mutate_change_status()`, `mutate_add_requirement()`, `mutate_delete_requirement(confirm=True)`
  - **Assertion Mutations**: `mutate_add_assertion()`, `mutate_update_assertion()`, `mutate_delete_assertion(confirm=True)`, `mutate_rename_assertion()`
  - **Edge Mutations**: `mutate_add_edge()`, `mutate_change_edge_kind()`, `mutate_delete_edge(confirm=True)`, `mutate_fix_broken_reference()`
  - **Undo Operations**: `undo_last_mutation()` and `undo_to_mutation(mutation_id)` for reverting graph changes
  - **Inspection Tools**: `get_mutation_log(limit)`, `get_orphaned_nodes()`, `get_broken_references()` for graph state inspection
- **Safety Checks**: Destructive mutation operations (`mutate_delete_*`) require explicit `confirm=True` parameter to prevent accidental data loss
- **Mutation Serialization**: New `serialize_mutation_entry()` and `serialize_broken_reference()` functions in MCP serializers

## [0.30.0] - 2026-01-28

### Added

- **Edge Mutation API**: TraceGraph now supports edge (relationship) mutations:
  - `add_edge(source_id, target_id, edge_kind, assertion_targets)` - Adds new edge, creates BrokenReference if target doesn't exist
  - `change_edge_kind(source_id, target_id, new_kind)` - Changes edge type (IMPLEMENTS -> REFINES)
  - `delete_edge(source_id, target_id)` - Removes edge, marks source as orphan if no other parents
  - `fix_broken_reference(source_id, old_target_id, new_target_id)` - Redirects broken reference to new target
- **Orphan Management**: Edge mutations automatically update `_orphaned_ids` set when parent relationships change
- **Broken Reference Tracking**: `add_edge` to non-existent target creates BrokenReference; `fix_broken_reference` can redirect these

## [0.29.0] - 2026-01-28

### Added

- **Assertion Mutation API**: TraceGraph now supports assertion-specific mutations:
  - `rename_assertion(old_id, new_label)` - Renames assertion label (e.g., A -> D), updates edges
  - `update_assertion(assertion_id, new_text)` - Updates assertion text
  - `add_assertion(req_id, label, text)` - Adds new assertion to requirement
  - `delete_assertion(assertion_id, compact=True)` - Deletes assertion with optional compaction
- **Assertion Compaction**: When deleting middle assertion (e.g., B from [A,B,C,D]), subsequent labels shift down (C->B, D->C) and all edge references update automatically
- **Hash Recomputation**: All assertion mutations recompute parent requirement hash via `_recompute_requirement_hash()`

## [0.28.0] - 2026-01-28

### Added

- **Node Mutation API**: TraceGraph now supports CRUD operations with full undo:
  - `rename_node(old_id, new_id)` - Renames node and its assertion children
  - `update_title(node_id, new_title)` - Updates requirement title
  - `change_status(node_id, new_status)` - Changes requirement status
  - `add_requirement(...)` - Creates new requirement with optional parent link
  - `delete_requirement(node_id)` - Deletes requirement, tracks in `_deleted_nodes`
- **Mutation Logging**: All mutations log `MutationEntry` to `graph.mutation_log` for audit
- **Undo Support**: `graph.undo_last()` and `graph.undo_to(mutation_id)` for reverting changes
- **GraphNode.set_id()**: Mutable node IDs for rename operations
- **GraphNode.remove_child()**: Removes child node with bidirectional link cleanup

## [0.27.0] - 2026-01-27

### Fixed

- **trace --view**: Fixed Assoc (Associated) toggle - now uses HIDE semantic consistent with PRD/OPS/DEV badges
- **trace --view**: Fixed Core toggle - clicking now hides core (non-associated) requirements with proper styling
- **trace --view**: Added tree collapse/expand state persistence via cookies - tree state now survives page refresh
- **trace --view**: Children implementing multiple assertions now show single row with combined badges `[A][B][C]`
- **trace --report**: Implemented report presets that were previously ignored

### Changed

- **CLI**: Removed 19 dead arguments that were defined but never implemented:
  - `validate`: --fix, --core-repo, --tests, --no-tests, --mode
  - `trace`: --port, --mode, --sponsor, --graph, --depth
  - `reformat-with-claude`: Simplified to placeholder stub (entire command not yet implemented)
- **CLI**: `trace --report` now uses `choices` for tab completion - shows `{minimal,standard,full}` in help
  - `--report minimal`: ID, Title, Status only (quick overview)
  - `--report standard`: ID, Title, Level, Status, Implements (default)
  - `--report full`: All fields including Body, Assertions, Hash, Code/Test refs

- **trace --view**: Version badge now shows actual elspais version (e.g., "v0.27.0") instead of hardcoded "v1"

- **trace --view**: Replaced confusing "Files" filter with "Tests" filter
  - Shows TEST nodes in tree hierarchy (with 🧪 icon)
  - Badge displays count of test nodes instead of file count
  - Clicking badge shows test rows that validate requirements

## [0.26.0] - Previous

- Multiline block comment support for code/test references
- Various bug fixes and improvements
