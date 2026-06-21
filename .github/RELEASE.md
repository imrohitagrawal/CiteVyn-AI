# Release process

This document describes the CiteVyn release process for
**maintainers**. It is the playbook that backs
[§13 of the README](../README.md#13-release-process).

## Versioning

- **SemVer** (`MAJOR.MINOR.PATCH`). All releases are tagged with a
  `v` prefix: `v0.2.0`.
- **Pre-releases** use a hyphen suffix: `v0.2.0-rc1`,
  `v0.2.0-beta2`. The release workflow marks them as pre-release
  on GitHub automatically.
- The version string in `backend/pyproject.toml` **must** match
  the tag.

## Cutting a release

1. **Pre-flight** — open the [releases page](../../releases) and
   check there are no open "release-blocker" issues. Verify
   `main` is green on the [ci workflow](../../actions/workflows/ci.yml).

2. **Bump the version** in `backend/pyproject.toml`:

   ```toml
   [project]
   name = "citevyn-backend"
   version = "0.2.0"     # ← this
   ```

3. **Update the changelog** at the top of `CHANGELOG`. Add an
   entry under the new version following the existing format.
   PR titles use Conventional Commits, so the entries are
   grouped (`feat:`, `fix:`, `chore:`, `docs:`).

4. **Commit + tag**:

   ```bash
   git commit -am "chore: cut v0.2.0"
   git tag -s v0.2.0 -m "v0.2.0 — production-ready"
   git push --follow-tags
   ```

5. **CI kicks off the release workflow**:
   - Validates the tag.
   - Builds `citevyn/api:v0.2.0` and `citevyn/worker:v0.2.0`.
   - Pushes them to `ghcr.io/imrohitagrawal/citevyn-{api,worker}`.
   - Drafts a GitHub Release (kept as a draft until you publish).

6. **Publish the release** — review the auto-generated changelog
   body, edit if needed, and click "Publish release". This
   notifies watchers and pings Dependabot to open update PRs.

## Rolling forward on a host

```bash
# On the production host, with the env file in place
VERSION=v0.2.0 make refresh
```

The `refresh` target rebuilds from local source. Operators
should also consider:

```bash
# Pull the published image instead of rebuilding from local source
docker pull ghcr.io/imrohitagrawal/citevyn-api:v0.2.0
docker pull ghcr.io/imrohitagrawal/citevyn-worker:v0.2.0
# Then point the compose file at the pulled image and ``up -d``.
```

## Rolling back

```bash
# 1. Pin the compose env to the previous tag
$EDITOR infra/docker/.env     # VERSION=v0.1.0

# 2. Rebuild + re-deploy
make refresh

# 3. If a forward-only migration ran, restore from backup
make restore FILE=infra/docker/backups/citevyn-<pre-upgrade-ts>.dump
```

The full playbook is in [`docs/RUNBOOK.md`](../docs/RUNBOOK.md#5-release--rollback).

## Hotfix process

For a critical fix that can't wait for a normal release:

1. Branch from the most recent release tag:
   ```bash
   git checkout v0.1.0 -b hotfix/cve-2026-XXXX
   ```
2. Land the fix, write a regression test, and re-run `make verify`.
3. Tag the hotfix:
   ```bash
   git tag -s v0.1.1 -m "v0.1.1 — security hotfix for CVE-2026-XXXX"
   git push --follow-tags
   ```
4. Merge `hotfix/…` back into `main` so the fix isn't lost.

The release workflow will build and publish `v0.1.1` the same
way it does for any other tag.

## Post-release

- Announce in the GitHub Discussions "Announcements" category.
- Update the `CHANGELOG` header on `main` to point at the
  published release.
- Close the milestone.

## What goes in a release body

The CI-generated changelog is grouped by commit type. Edit the
draft release to add:

- **Headline** — one-sentence summary of the release.
- **Breaking changes** — explicit call-out, with a migration
  note in the body.
- **Security fixes** — reference the CVE or GHSA id.
- **Operator notes** — anything the host operator must do
  (e.g. "set `CITEVYN_REDIS_URL` to enable the new rate limiter").
- **Acknowledgements** — external contributors and reporters.

## When to skip the release workflow

- A trivial doc-only or refactor change that has no user-facing
  impact. Land it on `main`, skip the tag, and the next
  functional change will roll it up.
- A change to the docs/ or .github/ directories. Same rule.

## Reference

- [`docs/RELEASE_PLAN.md`](../docs/RELEASE_PLAN.md) — historical
  release plan (slice 0).
- [`docs/RUNBOOK.md`](../docs/RUNBOOK.md) — on-call runbook
  covering deploy/rollback in detail.
- [`.github/workflows/release.yml`](workflows/release.yml) — the
  release workflow definition.