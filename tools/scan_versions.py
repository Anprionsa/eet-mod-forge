#!/usr/bin/env python3
"""
Scan GitHub repos for latest releases, stars, and activity.
Run via GitHub Actions on a schedule.
Usage: python scan_versions.py data/github_mods.json data/version_cache.json
"""

import json, sys, time, os
from urllib.request import urlopen, Request
from urllib.error import HTTPError

def fetch_repo_info(owner, repo, token=None):
    """Fetch latest release + repo metadata from GitHub API."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    result = {}
    
    # Get repo metadata (stars, last push)
    try:
        req = Request(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result["stars"] = data.get("stargazers_count", 0)
            result["pushed"] = (data.get("pushed_at") or "")[:10]
            result["archived"] = data.get("archived", False)
            result["description"] = (data.get("description") or "")[:200]
    except HTTPError as e:
        if e.code == 403:
            return "RATE_LIMITED"
        return None
    except Exception:
        pass
    
    # Get latest release
    try:
        req = Request(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", headers=headers)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result["tag"] = data.get("tag_name", "")
            result["release_name"] = data.get("name", "")
            result["release_date"] = (data.get("published_at") or "")[:10]
            result["body"] = (data.get("body") or "")[:500]
            result["release_url"] = data.get("html_url", "")
    except HTTPError as e:
        if e.code == 404:
            result["tag"] = ""  # No releases, that's fine
        elif e.code == 403:
            return "RATE_LIMITED"
    except Exception:
        pass
    
    return result


def main():
    if len(sys.argv) < 3:
        print("Usage: python scan_versions.py data/github_mods.json data/version_cache.json")
        sys.exit(1)
    
    input_path, output_path = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN")
    
    with open(input_path) as f:
        mods = json.load(f)
    
    cache = {}
    try:
        with open(output_path) as f:
            cache = json.load(f)
    except FileNotFoundError:
        pass
    
    print(f"Scanning {len(mods)} repos (token: {'yes' if token else 'no'})...")
    updated = 0
    rate_limited = False
    
    for i, mod in enumerate(mods):
        if rate_limited:
            break
        
        owner, repo = mod["o"], mod["r"]
        key = f"{owner}/{repo}"
        
        result = fetch_repo_info(owner, repo, token)
        
        if result == "RATE_LIMITED":
            rate_limited = True
            print(f"  Rate limited after {i} requests.")
            break
        
        if result:
            cache[key] = {
                **result,
                "mod_id": mod["i"],
                "installed": mod.get("v", ""),
                "checked": time.strftime("%Y-%m-%d"),
            }
            updated += 1
        
        if i % 10 == 9:
            time.sleep(0.5 if token else 2)
        
        if (i + 1) % 50 == 0:
            print(f"  Checked {i + 1}/{len(mods)}...")
    
    with open(output_path, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    print(f"Done. Updated {updated}. Cache total: {len(cache)}.")


if __name__ == "__main__":
    main()
