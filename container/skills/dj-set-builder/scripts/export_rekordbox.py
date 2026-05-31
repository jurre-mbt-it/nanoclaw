#!/usr/bin/env python3
"""Export an ordered DJ set to formats rekordbox can import.

Given the source rekordbox collection XML and an ordered list of TrackIDs,
writes TWO files so the user can load the set straight into rekordbox with the
order preserved:

  <out>.xml   — a rekordbox-native DJ_PLAYLISTS file. Each selected TRACK element
                is copied VERBATIM from the source (including Location and the
                TEMPO/POSITION_MARK beatgrid + cue children), and a single
                Type="1" playlist node lists the tracks in the chosen order by
                TrackID (KeyType="0"). This is the reliable path: rekordbox
                matches tracks to the user's existing collection by Location,
                so beatgrids and cues survive.
  <out>.m3u8  — a plain UTF-8 playlist of absolute file paths in order. Simpler
                to import (drag onto rekordbox) but carries no cue/beatgrid data
                and only works if the audio files sit at the same paths.

Why copy TRACK elements verbatim instead of rebuilding them: rekordbox stores
the analysed beatgrid (TEMPO) and hot cues/memory cues (POSITION_MARK) as child
elements. Rebuilding from scratch would drop them; a deep copy keeps the track
exactly as rekordbox analysed it.

Usage:
    python3 export_rekordbox.py --source collection.xml \
        --ids 177709775,51977700,... --name "Peak Set" --out /path/to/peak_set
    # or read ordered ids from a file (one per line, or a JSON array):
    python3 export_rekordbox.py --source collection.xml \
        --ids-file order.txt --name "Peak Set" --out /path/to/peak_set

The --out value is a basename WITHOUT extension; .xml and .m3u8 are appended.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
import sqlite3
import sys
import urllib.parse
import xml.etree.ElementTree as ET


def load_ids(args) -> list[str]:
    if args.ids:
        return [s.strip() for s in args.ids.split(",") if s.strip()]
    if args.ids_file:
        raw = open(args.ids_file, encoding="utf-8").read().strip()
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    sys.exit("Provide --ids or --ids-file")


def location_to_path(loc: str | None) -> str | None:
    if not loc:
        return None
    dec = urllib.parse.unquote(loc)
    for pre in ("file://localhost", "file://"):
        if dec.startswith(pre):
            dec = dec[len(pre):]
            break
    return dec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="source rekordbox collection XML")
    ap.add_argument("--db", help="library.py index DB to read tracks from (instead of --source)")
    ap.add_argument("--ids", help="comma-separated TrackIDs in play order")
    ap.add_argument("--ids-file", help="file with ordered TrackIDs (lines or JSON array)")
    ap.add_argument("--name", required=True, help="playlist name to create")
    ap.add_argument("--out", required=True, help="output basename (no extension)")
    args = ap.parse_args()
    if not args.source and not args.db:
        sys.exit("Provide --source (XML) or --db (library index)")

    ids = load_ids(args)
    # by_id maps TrackID -> verbatim <TRACK> element (with beatgrid + cues).
    if args.db:
        con = sqlite3.connect(args.db)
        by_id = {tid: ET.fromstring(blob)
                 for tid, blob in con.execute("SELECT track_id, xml_blob FROM tracks")}
        con.close()
        product = None
    else:
        src_root = ET.parse(args.source).getroot()
        by_id = {t.get("TrackID"): t for t in src_root.find("COLLECTION").iter("TRACK")}
        product = src_root.find("PRODUCT")

    missing = [i for i in ids if i not in by_id]
    if missing:
        print(f"WARNING: {len(missing)} TrackIDs not found in source and skipped: "
              f"{missing[:8]}{'...' if len(missing) > 8 else ''}", file=sys.stderr)
    ordered = [i for i in ids if i in by_id]
    if not ordered:
        sys.exit("No valid TrackIDs to export.")

    # --- build rekordbox XML ---
    dj = ET.Element("DJ_PLAYLISTS", {"Version": "1.0.0"})
    dj.append(copy.deepcopy(product) if product is not None else
              ET.Element("PRODUCT", {"Name": "rekordbox", "Company": "AlphaTheta"}))

    # COLLECTION: one entry per UNIQUE track, copied verbatim (keeps beatgrid + cues)
    out_col = ET.SubElement(dj, "COLLECTION")
    seen: set[str] = set()
    for tid in ordered:
        if tid in seen:
            continue
        seen.add(tid)
        out_col.append(copy.deepcopy(by_id[tid]))
    out_col.set("Entries", str(len(seen)))

    # PLAYLISTS: ROOT folder -> our ordered playlist (references by TrackID)
    pls = ET.SubElement(dj, "PLAYLISTS")
    root_node = ET.SubElement(pls, "NODE", {"Type": "0", "Name": "ROOT", "Count": "1"})
    pl = ET.SubElement(root_node, "NODE",
                       {"Name": args.name, "Type": "1", "KeyType": "0",
                        "Entries": str(len(ordered))})
    for tid in ordered:  # play order, duplicates allowed in a playlist
        ET.SubElement(pl, "TRACK", {"Key": tid})

    xml_path = args.out + ".xml"
    ET.ElementTree(dj).write(xml_path, encoding="UTF-8", xml_declaration=True)

    # --- build M3U8 ---
    m3u_path = args.out + ".m3u8"
    lines = ["#EXTM3U"]
    no_path = 0
    for tid in ordered:
        tr = by_id[tid]
        path = location_to_path(tr.get("Location"))
        secs = 0
        try:
            secs = int(float(tr.get("TotalTime") or 0))
        except ValueError:
            secs = 0
        artist = tr.get("Artist") or ""
        name = tr.get("Name") or ""
        title = f"{artist} - {name}".strip(" -")
        if path:
            lines.append(f"#EXTINF:{secs},{title}")
            lines.append(path)
        else:
            no_path += 1
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {xml_path} ({len(seen)} tracks in collection, "
          f"{len(ordered)} in playlist '{args.name}')")
    print(f"Wrote {m3u_path}" + (f" ({no_path} tracks had no Location, omitted)" if no_path else ""))


if __name__ == "__main__":
    main()
