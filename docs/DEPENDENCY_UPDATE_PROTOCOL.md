# Dependency Update Protocol

How POSSE dependencies are kept current and audited against vulnerabilities
and supply-chain attacks.

## Automated controls

| Control | Where | What it does |
|---|---|---|
| Dependabot | `.github/dependabot.yml` | Weekly update PRs for pip, Docker base image, and GitHub Actions |
| 7-day cooldown | `.github/dependabot.yml` | Never proposes a release younger than 7 days |
| OSV audit | `.github/workflows/audit.yml` | Scans `poetry.lock` (Python deps) on every dependency PR and weekly on a schedule |
| Image audit | `.github/workflows/audit.yml` | Trivy scans the built image for OS/base-image and library CVEs (zlib, BusyBox, etc.) |
| Hash-pinned installs | `poetry.lock` | Poetry verifies package hashes at install time |

The 7-day cooldown is the key supply-chain control: nearly every compromised
PyPI release in recent campaigns was detected and yanked within days of
publication. Never installing same-day releases sidesteps the dominant attack
pattern (maintainer-account phishing followed by a short-lived malicious
release).

The cooldown also delays Dependabot's *security* update PRs by up to 7 days,
so do not rely on Dependabot for urgent fixes. A known advisory against a
version we run is handled immediately through the manual Emergency path below,
which bypasses the cooldown.

## Weekly

Review and merge Dependabot PRs once CI and the Dependency Audit workflow
pass. Patch and minor pip updates arrive grouped in a single PR.

Before merging, be suspicious of any update where the package's maintainer,
repository URL, or release pattern recently changed — version bumps are
routine, provenance changes are not.

## Monthly

Full refresh of the dependency tree:

```bash
docker compose --profile test run --rm test poetry update --lock
git diff poetry.lock
docker compose --profile test run --rm test poetry sync
docker compose --profile test run --rm test
```

When reviewing the lock diff, a **new transitive package appearing in the
tree is a bigger red flag than any version bump** — investigate it before
merging. Land the result through a normal PR.

Major version bumps of direct dependencies are done individually, after
reading the upstream changelog.

Note: each local compose service keeps its Poetry virtualenv in a cache
volume (`poetry_cache` for the app, `poetry_cache_test` for the test
service), which shadows whatever the image installed at build time. The two
are kept separate because the app image installs only main deps while the
test image adds dev deps — a shared volume would let whichever service ran
first seed the venv for both. After changing `poetry.lock`, run `poetry sync`
inside the container (as above) — rebuilding the image alone does not update
the runtime environment.

## Emergency (advisory against a version we run)

The weekly OSV scan or an external advisory flags a vulnerable locked
version:

1. Bump only the affected package(s):
   `docker compose --profile test run --rm test poetry update <package> --lock`
2. Sync and run the test suite (commands above).
3. Land via PR and deploy. Do not bundle with routine updates.

If the advisory is an active supply-chain compromise (malicious release, not
a bug), also check whether the malicious version was ever installed locally
or in CI before the fix, and rotate any credentials the build could have
read.
