"""
publish_to_repos.py
Publishes MycoDiscovery outputs to TWO repositories with different visibility:

  PUBLIC  repo (e.g. "MycoDiscovery")        — the citable, open-access copy.
          Gets: the published JSON database, environment_snapshot.txt,
          prisma_summary.json, protocol.py (methodology), README.md.
          Does NOT get: raw candidate CSVs before curation (may contain
          curator scratch notes you haven't cleaned up for public view —
          edit PUBLIC_FILES below if you want these public too).

  PRIVATE repo (biostat-biodiscovery)         — the full working copy, used
          to actually serve the live website. Gets everything: the JSON,
          the JSX pages, the full search pipeline, all curation CSVs,
          full history.

Why two repos instead of one with folders:
  GitHub repo-level visibility (public/private) is all-or-nothing per repo.
  Keeping them separate means you can point people to a citable, permanent,
  public URL (https://github.com/YOUR_ORG/MycoDiscovery) for a methods
  section or a Zenodo archive, without exposing your website's private
  source code, work-in-progress pages, or anything else in
  biostat-biodiscovery.

Setup (once):
  1. Create the public repo on GitHub: name it "MycoDiscovery"
     (web UI: github.com/new, or `gh repo create MycoDiscovery --public`)
  2. Make biostat-biodiscovery private:
     Settings -> General -> Danger Zone -> Change visibility -> Private
  3. Set environment variables (or Colab Secrets):
       GITHUB_TOKEN        - PAT with 'repo' scope (works for both repos
                              if both belong to the same account/org)
       PUBLIC_REPO_URL      - e.g. https://github.com/Zdereje/MycoDiscovery.git
       PRIVATE_REPO_URL     - e.g. https://github.com/Zdereje/biostat-biodiscovery.git

Usage:
    python3 publish_to_repos.py --json mycodiscovery_targets_v2.json \\
        --data-dir data --work-dir /tmp/mycodiscovery_publish
"""
import argparse
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone

# Files that go to the PUBLIC repo — the citable, methodology-transparent subset.
PUBLIC_FILES = [
    "environment_snapshot.txt",
    "prisma_summary.json",
    "search_log.jsonl",
]
PUBLIC_CODE_FILES = ["protocol.py", "README.md", "requirements.txt"]


def run(cmd, cwd=None, check=True):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def clone_or_pull(repo_url: str, dest: Path, token: str):
    authed_url = repo_url.replace("https://", f"https://{token}@")
    if dest.exists():
        run(["git", "pull"], cwd=dest)
    else:
        run(["git", "clone", authed_url, str(dest)])
    # Always refresh the push URL with the current token (tokens can rotate)
    run(["git", "remote", "set-url", "origin", authed_url], cwd=dest)


def publish_public(repo_url: str, token: str, work_dir: Path, json_path: Path,
                    data_dir: Path, search_pipeline_dir: Path):
    dest = work_dir / "MycoDiscovery"
    clone_or_pull(repo_url, dest, token)

    (dest / "data").mkdir(exist_ok=True)
    shutil.copy(json_path, dest / "data" / json_path.name)

    for fname in PUBLIC_FILES:
        src = data_dir / fname
        if src.exists():
            shutil.copy(src, dest / "data" / fname)
        else:
            print(f"NOTE: {fname} not found in {data_dir}, skipping (not fatal).")

    (dest / "methodology").mkdir(exist_ok=True)
    for fname in PUBLIC_CODE_FILES:
        src = search_pipeline_dir / fname
        if src.exists():
            shutil.copy(src, dest / "methodology" / fname)

    _write_public_readme(dest, json_path)

    run(["git", "add", "-A"], cwd=dest)
    commit_msg = f"Publish MycoDiscovery data update: {datetime.now(timezone.utc).isoformat()}"
    result = run(["git", "commit", "-m", commit_msg], cwd=dest, check=False)
    if "nothing to commit" in (result.stdout + result.stderr):
        print("Public repo: no changes to publish.")
        return
    run(["git", "push"], cwd=dest)
    print(f"Published to public repo: {repo_url}")


def _write_public_readme(dest: Path, json_path: Path):
    readme = dest / "README.md"
    content = f"""# MycoDiscovery

A target-first, literature-curated database of published mycobacterial drug
discovery compounds and their reported resistance mutations, organized by
biological target rather than by species or marketed drug.

## Contents

- `data/{json_path.name}` — the published database (target -> compound ->
  resistance mutation, each mutation individually cited to a PMID/DOI)
- `data/prisma_summary.json` — systematic-review identification/deduplication
  counts
- `data/environment_snapshot.txt` — exact software versions and git commit
  used to generate this data release
- `methodology/protocol.py` — the pre-specified search protocol (query
  templates, inclusion/exclusion criteria) used to find candidate literature
- `methodology/README.md` — full pipeline documentation

## Status

Each target in the database is tagged `"status": "verified"` (compounds and
mutations pulled from real, individually-cited literature) or `"status":
"scaffold"` (target defined, awaiting the same literature curation pass).
Check `data/{json_path.name}` -> `metadata.verified_targets` for current
coverage.

## Citing this database

If you use this data, please cite the specific git commit/release you used
(tag releases via GitHub Releases for permanent, versioned citation), plus
the underlying primary literature cited in each mutation record.

## Maintained by

Biostat & BioDiscovery LLC. Updated periodically as literature curation
continues — see commit history for the update cadence.
"""
    readme.write_text(content)


def publish_private(repo_url: str, token: str, work_dir: Path, json_path: Path,
                     data_dir: Path):
    dest = work_dir / "biostat-biodiscovery"
    clone_or_pull(repo_url, dest, token)

    target_json_dir = dest / "public" / "data"
    target_json_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(json_path, target_json_dir / json_path.name)

    pipeline_data_dest = dest / "tools" / "mycodiscovery_search" / "data"
    pipeline_data_dest.mkdir(parents=True, exist_ok=True)
    if data_dir.exists():
        for item in data_dir.iterdir():
            if item.name == "cache":
                continue  # skip the raw PubMed response cache — regenerable, bulky
            if item.is_file():
                shutil.copy(item, pipeline_data_dest / item.name)

    run(["git", "add", "-A"], cwd=dest)
    commit_msg = f"MycoDiscovery data sync: {datetime.now(timezone.utc).isoformat()}"
    result = run(["git", "commit", "-m", commit_msg], cwd=dest, check=False)
    if "nothing to commit" in (result.stdout + result.stderr):
        print("Private repo: no changes to publish.")
        return
    run(["git", "push"], cwd=dest)
    print(f"Synced to private repo: {repo_url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="Path to the merged mycodiscovery_targets_*.json")
    ap.add_argument("--data-dir", required=True, help="Path to the search pipeline's data/ folder")
    ap.add_argument("--search-pipeline-dir", default=".", help="Path to mycodiscovery_search/ (for methodology files)")
    ap.add_argument("--work-dir", required=True, help="Scratch directory for repo clones")
    ap.add_argument("--public-only", action="store_true")
    ap.add_argument("--private-only", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    public_url = os.environ.get("PUBLIC_REPO_URL")
    private_url = os.environ.get("PRIVATE_REPO_URL")

    if not token:
        raise SystemExit("Set GITHUB_TOKEN (a PAT with 'repo' scope).")

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.json)
    data_dir = Path(args.data_dir)
    search_pipeline_dir = Path(args.search_pipeline_dir)

    if not args.private_only:
        if not public_url:
            raise SystemExit("Set PUBLIC_REPO_URL (e.g. https://github.com/YOU/MycoDiscovery.git)")
        publish_public(public_url, token, work_dir, json_path, data_dir, search_pipeline_dir)

    if not args.public_only:
        if not private_url:
            raise SystemExit("Set PRIVATE_REPO_URL (e.g. https://github.com/YOU/biostat-biodiscovery.git)")
        publish_private(private_url, token, work_dir, json_path, data_dir)


if __name__ == "__main__":
    main()
