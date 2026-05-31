#!/usr/bin/env python3
"""Pre-categorized track index for the DJ set builder.

Why this exists: parsing the full rekordbox XML (megabytes, thousands of
tracks) on every request is slow and burns tokens when track data lands in
context. This builds a compact SQLite index ONCE, with the fields the skill
needs plus derived categories (Camelot, BPM band, set-material flag). After
that, building a set is small SQL queries that return only the candidate rows
— not the whole library.

It also makes adding a new export cheap: `index` UPSERTS by TrackID, so a new
XML APPENDS new tracks and refreshes known ones instead of re-importing
everything. It reports how many were new vs already known, and flags likely
duplicates that carry a different TrackID (same artist+title).

Subcommands:
    index   build/update the index from one or more XML exports
    stats   summary: counts per BPM band, # artists, deep-cut-eligible, etc.
    query   list candidate tracks matching filters (the token-cheap path)

Examples:
    python3 library.py index --db library.db --source collection.xml
    python3 library.py index --db library.db --source new_export.xml   # appends/dedupes
    python3 library.py stats --db library.db
    python3 library.py query --db library.db --bpm-min 144 --bpm-max 158 --deep-cuts --limit 40
    python3 library.py query --db library.db --band hardtrance --format ids   # feeds export --ids

The `query` rows are pre-filtered for set-material (hygiene) by default and
carry a deep_cut flag (artist has <=2 tracks in the library, no rating, low
play count) computed live, so it stays correct as the library grows.
"""
from __future__ import annotations
import argparse
import os
import re
import sqlite3
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

CAMELOT = {
    "Abm": "1A", "G#m": "1A", "Ebm": "2A", "D#m": "2A", "Bbm": "3A", "A#m": "3A",
    "Fm": "4A", "Cm": "5A", "Gm": "6A", "Dm": "7A", "Am": "8A", "Em": "9A", "Bm": "10A",
    "F#m": "11A", "Gbm": "11A", "Dbm": "12A", "C#m": "12A",
    "B": "1B", "F#": "2B", "Gb": "2B", "Db": "3B", "C#": "3B", "Ab": "4B", "G#": "4B",
    "Eb": "5B", "D#": "5B", "Bb": "6B", "A#": "6B", "F": "7B", "C": "8B", "G": "9B",
    "D": "10B", "A": "11B", "E": "12B",
}


def to_camelot(t):
    if not t:
        return None
    t = t.strip()
    if re.fullmatch(r"\d{1,2}[AB]", t):
        return t
    return CAMELOT.get(t)


def bpm_band(b):
    if not b:
        return None
    if b < 128: return "house"
    if b < 140: return "trance/groove"
    if b < 150: return "hardhouse/trance"
    return "hardtrance"


def is_set_material(bpm, dur, loc):
    loc = (loc or "").lower().replace("%20", " ")
    if not bpm or bpm <= 0 or (dur or 0) < 90:
        return 0
    if any(s in loc for s in ("/sampler/", "loopmasters", "/demo tracks/")):
        return 0
    return 1


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def ident_of(artist, name, location, track_id):
    # Dedup identity = normalized artist+title. rekordbox re-exports churn both
    # TrackIDs AND file paths (volume renames, folder reorgs), but artist+title
    # is stable and still distinguishes versions (mix names live in the title).
    # Fall back to filename, then TrackID, when artist/title are missing.
    a, t = norm(artist), norm(name)
    if a or t:
        return f"at:{a}|{t}"
    base = os.path.basename(urllib.parse.unquote(location or "").rstrip("/")).lower()
    return f"f:{base}" if base else f"id:{track_id}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
  ident TEXT PRIMARY KEY,          -- normalized file location (stable id)
  track_id TEXT,
  name TEXT, artist TEXT, artist_norm TEXT, title_norm TEXT,
  bpm REAL, camelot TEXT, genre TEXT,
  rating INTEGER, play_count INTEGER, total_time INTEGER, year INTEGER,
  location TEXT, bpm_band TEXT, is_set_material INTEGER,
  source_xml TEXT, xml_blob TEXT, first_seen TEXT
);
CREATE INDEX IF NOT EXISTS idx_bpm ON tracks(bpm);
CREATE INDEX IF NOT EXISTS idx_band ON tracks(bpm_band);
CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist_norm);
CREATE INDEX IF NOT EXISTS idx_camelot ON tracks(camelot);
CREATE INDEX IF NOT EXISTS idx_trackid ON tracks(track_id);
CREATE INDEX IF NOT EXISTS idx_titlenorm ON tracks(artist_norm, title_norm);
"""


def cmd_index(args):
    con = sqlite3.connect(args.db)
    con.executescript(SCHEMA)
    if args.replace:
        con.execute("DELETE FROM tracks")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = known = moved = 0
    for src in args.source:
        root = ET.parse(src).getroot()
        col = root.find("COLLECTION")
        if col is None:
            print(f"WARN: no COLLECTION in {src}", file=sys.stderr)
            continue
        for tr in col.iter("TRACK"):
            tid = tr.get("TrackID")
            if not tid or tr.get("Name") is None:
                continue
            ident = ident_of(tr.get("Artist"), tr.get("Name"), tr.get("Location"), tid)
            bpm = float(tr.get("AverageBpm") or 0) or None
            dur = int(float(tr.get("TotalTime") or 0))
            row = (
                ident, tid, tr.get("Name"), tr.get("Artist"), norm(tr.get("Artist")), norm(tr.get("Name")),
                bpm, to_camelot(tr.get("Tonality")), tr.get("Genre"),
                int(tr.get("Rating") or 0) // 51, int(tr.get("PlayCount") or 0),
                dur, int(tr.get("Year") or 0) or None,
                tr.get("Location"), bpm_band(bpm), is_set_material(bpm, dur, tr.get("Location")),
                src, ET.tostring(tr, encoding="unicode"), now,
            )
            prev = con.execute("SELECT location FROM tracks WHERE ident=?", (ident,)).fetchone()
            if prev is not None and prev[0] != tr.get("Location"):
                moved += 1
            con.execute(
                """INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(ident) DO UPDATE SET
                     track_id=excluded.track_id, name=excluded.name, artist=excluded.artist,
                     artist_norm=excluded.artist_norm, title_norm=excluded.title_norm,
                     bpm=excluded.bpm, camelot=excluded.camelot, genre=excluded.genre,
                     rating=excluded.rating, play_count=excluded.play_count,
                     total_time=excluded.total_time, year=excluded.year, location=excluded.location,
                     bpm_band=excluded.bpm_band, is_set_material=excluded.is_set_material,
                     source_xml=excluded.source_xml, xml_blob=excluded.xml_blob""",
                row)
            if prev is not None: known += 1
            else: new += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    con.close()
    print(f"indexed {args.source}" + (" (replace)" if args.replace else ""))
    print(f"  new: {new} | already known (refreshed): {known} | library total: {total}")
    if moved:
        print(f"  note: {moved} known tracks had a changed file location (moved/re-exported) "
              f"— refreshed to the new path")


def cmd_stats(args):
    con = sqlite3.connect(args.db)
    total = con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    setm = con.execute("SELECT COUNT(*) FROM tracks WHERE is_set_material=1").fetchone()[0]
    artists = con.execute("SELECT COUNT(DISTINCT artist_norm) FROM tracks").fetchone()[0]
    print(f"library total: {total} | set-material: {setm} | distinct artists: {artists}")
    print("by BPM band (set-material only):")
    for band, c in con.execute(
            "SELECT bpm_band, COUNT(*) FROM tracks WHERE is_set_material=1 "
            "GROUP BY bpm_band ORDER BY 2 DESC"):
        print(f"  {band or '(geen bpm)':18} {c}")
    dc = con.execute(
        "SELECT COUNT(*) FROM tracks t JOIN (SELECT artist_norm, COUNT(*) c FROM tracks "
        "GROUP BY artist_norm) a ON t.artist_norm=a.artist_norm "
        "WHERE t.is_set_material=1 AND a.c<=2 AND IFNULL(t.rating,0)=0 AND IFNULL(t.play_count,0)<=1"
    ).fetchone()[0]
    print(f"deep-cut-eligible (proxy): {dc}")
    con.close()


def cmd_query(args):
    con = sqlite3.connect(args.db)
    where = ["t.is_set_material=1"] if not args.include_fx else []
    params = []
    if args.bpm_min is not None: where.append("t.bpm >= ?"); params.append(args.bpm_min)
    if args.bpm_max is not None: where.append("t.bpm <= ?"); params.append(args.bpm_max)
    if args.band: where.append("t.bpm_band = ?"); params.append(args.band)
    if args.key: where.append("t.camelot = ?"); params.append(args.key)
    if args.with_key: where.append("t.camelot IS NOT NULL")
    if args.deep_cuts:
        where.append("a.c <= 2 AND IFNULL(t.rating,0)=0 AND IFNULL(t.play_count,0)<=1")
    sql = ("SELECT t.track_id, t.artist, t.name, t.bpm, t.camelot, t.genre, "
           "t.rating, t.play_count, a.c AS artist_count "
           "FROM tracks t JOIN (SELECT artist_norm, COUNT(*) c FROM tracks GROUP BY artist_norm) a "
           "ON t.artist_norm=a.artist_norm")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.bpm"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = con.execute(sql, params).fetchall()
    con.close()
    if args.format == "ids":
        print(",".join(r[0] for r in rows))
        return
    print(f"{len(rows)} tracks:")
    for tid, artist, name, bpm, cam, genre, rating, pc, ac in rows:
        dc = " [deep cut]" if (ac <= 2 and (rating or 0) == 0 and (pc or 0) <= 1) else ""
        print(f"  {tid:>11}  {bpm or 0:5.0f} {cam or '--':>3}  {(artist or '?')[:24]:24} - {(name or '')[:34]:34}{dc}")


def main():
    ap = argparse.ArgumentParser(description="Pre-categorized track index for the DJ set builder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="build/update the index from XML export(s)")
    p.add_argument("--db", required=True)
    p.add_argument("--source", required=True, action="append", help="rekordbox XML (repeatable)")
    p.add_argument("--replace", action="store_true",
                   help="clear the index first — use when the XML is your full current library "
                        "(refreshes everything, drops tracks no longer present)")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("stats", help="summary of the library")
    p.add_argument("--db", required=True)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("query", help="list candidate tracks matching filters")
    p.add_argument("--db", required=True)
    p.add_argument("--bpm-min", type=float)
    p.add_argument("--bpm-max", type=float)
    p.add_argument("--band", help="house | trance/groove | hardhouse/trance | hardtrance")
    p.add_argument("--key", help="Camelot code, e.g. 8A")
    p.add_argument("--with-key", action="store_true", help="only tracks that have a key")
    p.add_argument("--deep-cuts", action="store_true", help="only deep-cut-eligible tracks")
    p.add_argument("--include-fx", action="store_true", help="don't filter out sample-FX")
    p.add_argument("--limit", type=int)
    p.add_argument("--format", choices=["table", "ids"], default="table")
    p.set_defaults(func=cmd_query)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
