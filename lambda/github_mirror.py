"""
GitHub-backed mirror for Lambda /recall + Compare.

The Lambda needs read-only access to two things in the repo:
  - tech-radar.md         (for /radar grep fallback)
  - memory/chroma/        (for Mem0 semantic queries)

Option A: GitHub Actions can push these files to an S3 mirror; Lambda reads
from S3. This is the legacy compatibility path and requires AWS credentials
in both GitHub Actions and Lambda.

Option B (default): Lambda fetches the repo tarball directly from GitHub using
GH_TOKEN when configured, or anonymous access for a public repo. No S3 mirror
is required; the GitHub repo remains the single source of truth.

Trade-off: one HTTP call + tarball extract on cold start (~3-5s extra). All
warm invocations within the cache TTL are zero-cost.

Endpoint used:
  https://api.github.com/repos/<owner>/<repo>/tarball/<branch>
"""

from __future__ import annotations

import os
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Paths Lambda reads (kept in sync with radar_query.py)
LOCAL_MIRROR = Path("/tmp/frontier-scout-mirror")
FRESHNESS_MARKER = LOCAL_MIRROR / ".github-synced-at"

# How long a downloaded mirror is considered fresh before we re-fetch.
# Warm Lambda invocations within this window skip the download entirely.
CACHE_TTL_SECONDS = int(os.environ.get("MIRROR_TTL_SECONDS", "600"))   # 10 min default

# Bound the download so a misconfigured repo can't fill /tmp.
MAX_TARBALL_BYTES = 50 * 1024 * 1024   # 50 MB — repo is ~5 MB today
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024


# Only paths under these roots survive the extract — everything else is
# discarded. Defense-in-depth against an attacker who somehow lands a file
# at e.g. `../etc/passwd` inside the tarball.
ALLOWED_PATH_PREFIXES = (
    "tech-radar.md",
    "skills-log.md",
    "memory/",
    "briefings/",
    "costs.jsonl",
    "quality-log.jsonl",
)


def ensure_mirror_from_github() -> bool:
    """Populate /tmp/frontier-scout-mirror/ from a GitHub tarball.

    Returns True iff the mirror is usable after this call (either freshly
    downloaded or still-warm cached). Returns False on any failure — the
    caller (radar_query._ensure_mirror) treats False as "mirror unavailable"
    and falls back to the graceful "configure mirror" message.
    """
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GH_BRANCH") or os.environ.get("GITHUB_REF_NAME", "main")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not repo:
        print("  GitHub mirror: GH_REPO/GITHUB_REPOSITORY missing — skipping")
        return False

    # Warm cache hit
    if _cache_is_fresh():
        return True

    url = f"https://api.github.com/repos/{repo}/tarball/{branch}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "frontier-scout-lambda",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)

    LOCAL_MIRROR.mkdir(parents=True, exist_ok=True)
    tarball_path = Path("/tmp") / "frontier-scout-mirror.tar.gz"

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read(MAX_TARBALL_BYTES + 1)
        if len(content) > MAX_TARBALL_BYTES:
            print(f"  GitHub mirror: tarball > {MAX_TARBALL_BYTES} bytes — aborting")
            return False
        tarball_path.write_bytes(content)
    except urllib.error.HTTPError as e:
        body = (e.read() or b"")[:200].decode("utf-8", errors="ignore")
        print(f"  GitHub mirror: HTTP {e.code} from {url} · {body}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"  GitHub mirror: fetch failed: {e}")
        return False

    if not _safe_extract(tarball_path):
        return False

    FRESHNESS_MARKER.write_text(str(int(time.time())))
    print(f"  GitHub mirror: synced from {repo}@{branch} ({len(content)} bytes)")
    return True


def _cache_is_fresh() -> bool:
    if not FRESHNESS_MARKER.exists():
        return False
    try:
        ts = int(FRESHNESS_MARKER.read_text().strip())
    except (ValueError, OSError):
        return False
    age = time.time() - ts
    return 0 <= age < CACHE_TTL_SECONDS


def _safe_extract(tarball_path: Path) -> bool:
    """Extract the tarball into LOCAL_MIRROR with traversal + size guards.

    GitHub tarballs have an outer directory like `<owner>-<repo>-<sha>/`
    which we strip — the destination tree mirrors the repo root.
    """
    mirror_root = LOCAL_MIRROR.resolve()
    total_bytes = 0
    extracted_count = 0

    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            for member in tar:
                # Strip the outer directory: "ws-repo-abc123/tech-radar.md" → "tech-radar.md"
                parts = Path(member.name).parts
                if len(parts) < 2:
                    continue  # the outer dir itself; skip
                rel_path = Path(*parts[1:])
                rel_str = str(rel_path).replace("\\", "/")

                # Whitelist: only files we actually need land in /tmp
                if not any(rel_str == p.rstrip("/") or rel_str.startswith(p) for p in ALLOWED_PATH_PREFIXES):
                    continue

                # Path-traversal guard: resolved destination must stay under mirror_root
                dest = (LOCAL_MIRROR / rel_path).resolve()
                try:
                    dest.relative_to(mirror_root)
                except ValueError:
                    print(f"  GitHub mirror: rejected traversal member {member.name!r}")
                    continue

                # Symlinks/links discarded — tarfile defaults already protect
                # against most cases on Python 3.12+, but be explicit.
                if member.issym() or member.islnk():
                    continue

                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue

                total_bytes += member.size or 0
                if total_bytes > MAX_EXTRACTED_BYTES:
                    print(f"  GitHub mirror: extract byte cap hit ({MAX_EXTRACTED_BYTES})")
                    return False

                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src:
                    if src is None:
                        continue
                    dest.write_bytes(src.read())
                extracted_count += 1
    except tarfile.TarError as e:
        print(f"  GitHub mirror: tar extract failed: {e}")
        return False

    print(f"  GitHub mirror: extracted {extracted_count} files ({total_bytes} bytes)")
    return True
