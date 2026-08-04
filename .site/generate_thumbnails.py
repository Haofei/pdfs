#!/usr/bin/env python3
"""Render first-page thumbnails for every PDF in the manifest.

Thumbnails are keyed by the 12-hex blob-SHA prefix from the manifest (`h`),
so they are content-addressed: a re-uploaded/renamed PDF reuses its thumb and
only genuinely new blobs get rendered.  Requires pdftoppm (poppler-utils) and
Pillow with WebP support.

Local mode (bootstrap, every PDF already on disk):
    generate_thumbnails.py --manifest manifest.json --repo /path/to/pdfs --out thumbs/

CI mode (incremental, fetch only missing blobs over HTTP):
    generate_thumbnails.py --manifest manifest.json --out thumbs-store/ \
        --fetch-base https://raw.githubusercontent.com/tpn/pdfs/<sha>
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from PIL import Image

RENDER_TIMEOUT = 120  # seconds per PDF; big scanned PDFs can be slow


def encode_path(path):
    return "/".join(urllib.parse.quote(seg) for seg in path.split("/"))


def render_one(pdf_path, out_path):
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "page")
        subprocess.run(
            ["pdftoppm", "-f", "1", "-l", "1", "-scale-to", "400",
             "-png", "-singlefile", pdf_path, base],
            check=True, capture_output=True, timeout=RENDER_TIMEOUT)
        im = Image.open(base + ".png").convert("RGB")
        # Unique temp name + atomic rename: several manifest entries can share
        # one blob SHA (identical PDFs under two names).
        tf = tempfile.NamedTemporaryFile(
            dir=os.path.dirname(out_path) or ".", suffix=".tmp", delete=False)
        tf.close()
        im.save(tf.name, "WEBP", quality=72, method=4)
    os.replace(tf.name, out_path)


def process(rec, args):
    out_path = os.path.join(args.out, rec["h"] + ".webp")
    if os.path.exists(out_path):
        return "cached"
    try:
        if args.fetch_base:
            url = args.fetch_base.rstrip("/") + "/" + encode_path(rec["p"])
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                with urllib.request.urlopen(url, timeout=300) as resp:
                    while chunk := resp.read(1 << 20):
                        tf.write(chunk)
                tmp_pdf = tf.name
            try:
                render_one(tmp_pdf, out_path)
            finally:
                os.unlink(tmp_pdf)
        else:
            render_one(os.path.join(args.repo, rec["p"]), out_path)
        return "ok"
    except Exception as e:
        print(f"FAIL {rec['p']}: {type(e).__name__}: {e}", file=sys.stderr)
        return "fail"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", help="local repo working copy (local mode)")
    ap.add_argument("--fetch-base", help="base URL for raw blobs (CI mode)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    args = ap.parse_args()
    if bool(args.repo) == bool(args.fetch_base):
        sys.exit("exactly one of --repo / --fetch-base is required")

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)
    seen = set()
    pdfs = [r for r in manifest["files"]
            if r["e"] == "pdf" and not (r["h"] in seen or seen.add(r["h"]))]
    os.makedirs(args.out, exist_ok=True)

    counts = {"ok": 0, "cached": 0, "fail": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for i, result in enumerate(ex.map(lambda r: process(r, args), pdfs), 1):
            counts[result] += 1
            if i % 100 == 0 or i == len(pdfs):
                print(f"{i}/{len(pdfs)} rendered={counts['ok']} "
                      f"cached={counts['cached']} failed={counts['fail']}",
                      flush=True)

    print(f"done: {counts}", flush=True)
    # A few failures (corrupt/encrypted PDFs) are tolerable; a wholesale
    # failure means the toolchain is broken -- fail loudly in that case.
    if counts["ok"] + counts["cached"] < len(pdfs) * 0.95:
        sys.exit(1)


if __name__ == "__main__":
    main()
