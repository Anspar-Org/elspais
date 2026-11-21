# The automain trunk and pre-releases

`automain` is a second trunk beside `main`. Autonomous agents merge their
pull requests into it. A maintainer promotes it to `main` through a pull
request that the maintainer reviews. `automain` has the checks of `main`, it
never releases, and each commit that passes its checks is published to PyPI
as a pre-release that other repositories can pin (REQ-o00080, REQ-o00081).

## Checks

A pull request, a merge-queue candidate and a push targeting `automain` run
every check that they run for `main` (REQ-o00080-A+B+C):

- `ci.yml` runs on every pull request and merge-queue candidate whatever the
  base, and on a push to `main` or `automain`. A push to `automain` runs the
  impacted unit tests, or every tier where the merged pull request carries the
  label `publish` or `baseline`, as a push to `main` does. See
  [Test Impact Analysis](test-impact-analysis.md#ci).
- `pr-validation.yml` runs on every pull request and merge-queue candidate
  whatever the base.

The promotion pull request targets `main`, so the checks of `main` apply to
it in full.

## What publishes

Only `main` releases. A change to `automain` publishes its pre-release and
nothing else (REQ-o00080-D+E):

| Workflow | What it publishes | Runs for |
| --- | --- | --- |
| `auto-release.yml` | the tag and the GitHub release | a passing push run of CI on `main` |
| `publish-pypi.yml` | the release on PyPI, the Homebrew tap | a commit that `main` contains; its gate refuses any other |
| `ci.yml`, `promote-image` | the production CI image tag | `main` |
| `ci.yml`, baseline recording | the TIA baseline that runs select from | a full run of `main` |
| `build-ci-image.yml` | the production CI image tag | `main` |
| `prerelease-pypi.yml` | the pre-release on PyPI, built by `ci.yml`'s `prerelease-build` | a passing push run of CI on `automain` |

## Pre-releases

`prerelease-pypi.yml` runs after each push run of CI on `automain` that
passed. It publishes that commit to PyPI as the PEP 440 developmental release
`X.Y.Z.devN` (REQ-o00081-A):

- `X.Y.Z` is the version that the commit declares in `pyproject.toml`. Where
  PyPI already carries a release at or above it, `X.Y.Z` is the patch after
  the newest release. So a pre-release sorts above every release, and below
  the release `X.Y.Z` that follows it.
- `N` is the count of first-parent commits on `automain` at that commit. It
  increases with every merge into `automain` and names one commit.
- A version that PyPI carries or carried is never used again
  (REQ-o00081-C). PyPI keeps a number for ever, even after a yank, so the
  workflow refuses such a version rather than renumbering. A re-run for a
  commit that already has its pre-release therefore fails and publishes
  nothing. A release made from `main` while the commit's CI runs can also
  move `X.Y.Z` between the build and the publication; the package then
  carries a version the workflow no longer computes, so it is refused, and a
  re-run of that commit's CI builds and publishes it under the new base.

`python -m tools.prerelease_version` computes the version. The workflow
makes no tag, no GitHub release and no Homebrew update.

### Who runs what

A commit on `automain` has passed CI, but no maintainer has reviewed it. So
its code never runs where the PyPI credential is readable
(REQ-o00081-D):

- The `prerelease-build` job of `ci.yml` runs on a push to `automain`. It
  holds no publishing credential. It writes the pre-release version into its
  checkout of `pyproject.toml`, builds the package and uploads it as the
  `prerelease-dist` artifact. The version is never committed.
- `prerelease-pypi.yml` holds the credential and runs only code from `main`:
  the version tool, the lock and the workflow itself. It reads the commit as
  data, computes the version again, and downloads the artifact. It publishes
  the files only where they are one wheel and one sdist of elspais whose
  metadata carries that version.

### Installing a pre-release

pip and uv select a developmental release only for a requirement that names
a pre-release (REQ-o00081-B). An ordinary install or upgrade never reaches
one:

```sh
pip install elspais                    # the newest release
pip install --upgrade elspais          # the newest release
pip install "elspais==0.130.9.dev812"  # that pre-release
```

A repository's `automain` work may pin a pre-release this way. Its `main`
depends only on releases, so the promotion of a consumer to `main` moves each
pin to a released version. elspais is promoted and released first.

## Repository settings

A repository administrator sets these, not a pull request:

- The `automain` branch, created from `main`. Its creation is a push, so
  the first pre-release is of the commit `main` held then.
- A ruleset on `automain` with the protection of `main`: the same required
  status checks, the merge queue, no deletion and no force-push.
- Every change reaches `automain` through a merge commit, the merge of
  `main` into it included. A rewrite or a fast-forward of `automain` can lower
  the first-parent count, and the workflow then refuses each number that PyPI
  already carries.
- A `publish` environment that holds `PYPI_TOKEN` and `HOMEBREW_TAP_TOKEN`,
  with a deployment policy that admits the branch `main` and the tags `v*`
  alone, and a tag ruleset that lets only maintainers create `v*` tags. The
  repository holds neither secret outside that environment. A workflow file
  on `automain`, or on any pull request branch, then cannot read either token,
  so its code cannot publish. The release and the pre-release jobs name this
  environment.
