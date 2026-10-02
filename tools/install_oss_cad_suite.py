#!/usr/bin/env python3
"""Download a pinned OSS CAD Suite Linux-x64 release with checksum verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

API = "https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases/tags/{tag}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "mind3-oss-cad-installer"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="Pinned OSS CAD Suite release tag, e.g. 2026-09-29")
    ap.add_argument("--destination", type=Path, required=True)
    ap.add_argument("--expected-sha256", default=os.getenv("OSS_CAD_SUITE_SHA256"))
    ap.add_argument("--keep-archive", action="store_true")
    args = ap.parse_args()

    destination = args.destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    release = fetch_json(API.format(tag=args.tag))
    assets = release.get("assets", [])
    matches = [a for a in assets if str(a.get("name", "")).startswith("oss-cad-suite-linux-x64-") and str(a.get("name", "")).endswith(".tgz")]
    if len(matches) != 1:
        names = [a.get("name") for a in matches]
        raise SystemExit(f"Expected exactly one Linux-x64 OSS CAD Suite archive for tag {args.tag}; found {names}")

    asset = matches[0]
    name = str(asset["name"])
    url = str(asset["browser_download_url"])
    declared_digest = str(asset.get("digest") or "")
    if declared_digest.startswith("sha256:"):
        declared_digest = declared_digest.split(":", 1)[1]

    temp_dir = Path(tempfile.mkdtemp(prefix="mind3_oss_cad_"))
    archive = temp_dir / name
    try:
        print(f"Downloading {name} from pinned release {args.tag}...", flush=True)
        urllib.request.urlretrieve(url, archive)
        actual = sha256(archive)
        expected = args.expected_sha256 or declared_digest
        if expected and actual.lower() != expected.lower():
            raise SystemExit(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")
        print(f"SHA-256: {actual}", flush=True)

        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, mode="r:gz") as tf:
            root = destination.resolve()
            members = []
            for member in tf.getmembers():
                target = (root / member.name).resolve()
                if target != root and root not in target.parents:
                    raise SystemExit(f"Unsafe archive member rejected: {member.name}")
                if member.issym() or member.islnk():
                    link_target = (target.parent / member.linkname).resolve()
                    if root not in link_target.parents and link_target != root:
                        raise SystemExit(f"Unsafe archive link rejected: {member.name} -> {member.linkname}")
                members.append(member)
            tf.extractall(root, members=members)

        children = [p for p in destination.iterdir()]
        if len(children) == 1 and children[0].is_dir():
            inner = children[0]
            for item in inner.iterdir():
                shutil.move(str(item), destination / item.name)
            inner.rmdir()

        metadata = {
            "tag": args.tag,
            "asset": name,
            "asset_url": url,
            "sha256": actual,
            "declared_digest": declared_digest or None,
            "release_html_url": release.get("html_url"),
        }
        (destination / "mind3-oss-cad-suite.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(metadata, indent=2), flush=True)
        return 0
    finally:
        if args.keep_archive:
            print(f"Archive retained at {archive}", flush=True)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
