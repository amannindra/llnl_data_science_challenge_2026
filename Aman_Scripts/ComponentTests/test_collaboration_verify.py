#!/usr/bin/env python3
"""Adversarial checks for the collaborator handoff verification helpers.

Every fixture here is synthetic and lives in a temporary directory.  The real
packet under ``collaboration/`` is never read, so these checks stay fast and
keep failing for code reasons rather than for evidence reasons.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from _harness import Checker, finish

from Components.testing import load_module_from_path

SCRIPTS = Path(__file__).resolve().parents[1]
verify = load_module_from_path(
    SCRIPTS / "collaboration" / "verify_handoff.py", "collaboration_verify_handoff"
)


def build_packet(root: Path) -> dict:
    """Write a tiny synthetic packet and return its (correct) manifest."""

    (root / "tables").mkdir(parents=True, exist_ok=True)
    (root / "panels").mkdir(parents=True, exist_ok=True)
    payload = {
        "good.txt": b"good\n",
        "tables/rows.csv": b"a,b\n1,2\n3,4\n",
        "panels/rank_001_E_N000001_N000002_ct_panel.png": b"\x89PNG-fake",
    }
    for relative, data in payload.items():
        (root / relative).write_bytes(data)
    files = [
        {
            "path": relative,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for relative, data in sorted(payload.items())
    ]
    return {"file_count": len(files), "files": files}


def main() -> int:
    check = Checker("collaboration/verify_handoff helpers", minimum_checks=12)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        # ---------------------------------------------------------------- #
        # Streamed hashing
        # ---------------------------------------------------------------- #
        hello = root / "hello.bin"
        hello.write_bytes(b"hello")
        check.equal(
            "hash_file matches the known SHA-256 vector for b'hello'",
            verify.hash_file(hello),
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        )
        chunky = root / "chunky.bin"
        chunky.write_bytes(bytes(range(256)) * 4096)
        check.equal(
            "hash_file is block-size independent across many chunks",
            verify.hash_file(chunky, block_size=7),
            hashlib.sha256(chunky.read_bytes()).hexdigest(),
        )
        check.raises(
            "hash_file refuses a missing file",
            FileNotFoundError, verify.hash_file, root / "absent.bin",
        )

        # ---------------------------------------------------------------- #
        # Panel filename parsing
        # ---------------------------------------------------------------- #
        parsed = verify.parse_panel_filename("rank_007_E_N001012_N002152_ct_panel.png")
        check.equal(
            "a well-formed panel filename parses into rank/edge/nodes",
            None if parsed is None else (parsed.rank, parsed.edge_id, parsed.node_u, parsed.node_v),
            (7, "E_N001012_N002152", "N001012", "N002152"),
        )
        malformed = [
            "rank_7_E_N001012_N002152_ct_panel.png",        # rank not zero-padded to 3
            "rank_007_E_N001012_ct_panel.png",              # only one node
            "rank_007_N001012_N002152_ct_panel.png",        # missing the E_ prefix
            "rank_007_E_N001012_N002152_ct_panel.jpg",      # wrong extension
            "rank_007_E_NOTANODE_N002152_ct_panel.png",     # non-numeric node
            "prefix_rank_007_E_N001012_N002152_ct_panel.png",  # unanchored prefix
            "rank_007_E_N001012_N002152_ct_panel.png.bak",  # trailing junk
            "",
        ]
        check.check(
            "every malformed panel filename is rejected",
            all(verify.parse_panel_filename(name) is None for name in malformed),
            f"accepted: {[n for n in malformed if verify.parse_panel_filename(n) is not None]}",
        )
        check.equal(
            "panel_filename round-trips through parse_panel_filename",
            verify.parse_panel_filename(verify.panel_filename(3, "E_N000042_N000043")),
            verify.PanelName(3, "E_N000042_N000043", "N000042", "N000043"),
        )
        check.raises(
            "panel_filename rejects a negative rank",
            ValueError, verify.panel_filename, -1, "E_N000001_N000002",
        )
        check.equal("parse_edge_id splits a valid edge ID",
                    verify.parse_edge_id("E_N000001_N012345"), ("N000001", "N012345"))
        check.check(
            "parse_edge_id rejects malformed edge IDs",
            all(verify.parse_edge_id(bad) is None
                for bad in ("N000001_N000002", "E_N000001", "E_1_2", "", "E_N1_N2_N3")),
        )
        check.equal("node_number extracts the padded integer",
                    verify.node_number("N009069"), 9069)
        check.check("node_number rejects malformed node IDs",
                    all(verify.node_number(bad) is None for bad in ("9069", "NN1", "N", "N12a", "")))

        # ---------------------------------------------------------------- #
        # Rank contiguity
        # ---------------------------------------------------------------- #
        check.equal(
            "a contiguous 1..5 rank column reports no problems",
            verify.rank_sequence_problems([1, 2, 3, 4, 5], 5),
            {"duplicates": [], "missing": [], "unexpected": []},
        )
        check.equal(
            "a gap in the rank column is reported as missing",
            verify.rank_sequence_problems([1, 2, 4, 5, 6], 5),
            {"duplicates": [], "missing": [3], "unexpected": [6]},
        )
        check.equal(
            "a duplicated rank is reported",
            verify.rank_sequence_problems([1, 2, 2, 4], 4),
            {"duplicates": [2], "missing": [3], "unexpected": []},
        )
        check.equal(
            "zero-based ranks are caught as an off-by-one",
            verify.rank_sequence_problems([0, 1, 2], 3),
            {"duplicates": [], "missing": [3], "unexpected": [0]},
        )

        # ---------------------------------------------------------------- #
        # Orphan detection and unsafe manifest paths
        # ---------------------------------------------------------------- #
        packet = root / "packet"
        manifest = build_packet(packet)
        listed = [entry["path"] for entry in manifest["files"]]
        check.equal("an exact packet has no orphans", verify.orphan_files(packet, listed), [])
        (packet / "tables" / "sneaky.csv").write_bytes(b"x\n1\n")
        (packet / "ünicode – fïle.md").write_bytes("café\n".encode("utf-8"))
        check.equal(
            "unlisted files (including unicode names) are reported as orphans",
            verify.orphan_files(packet, listed),
            ["tables/sneaky.csv", "ünicode – fïle.md"],
        )
        check.equal(
            "relative_files walks nested directories with POSIX separators",
            sorted(verify.relative_files(packet)),
            sorted(listed + ["tables/sneaky.csv", "ünicode – fïle.md"]),
        )
        check.equal(
            "a manifest entry with no file on disk is not mistaken for an orphan",
            verify.orphan_files(packet, listed + ["never/written.txt"]),
            ["tables/sneaky.csv", "ünicode – fïle.md"],
        )
        check.equal(
            "absolute and parent-escaping manifest paths are rejected",
            verify.unsafe_manifest_paths(
                ["ok/file.csv", "/etc/passwd", "../outside.md", "a/../../b.md", "nested/ok.txt"]
            ),
            ["../outside.md", "/etc/passwd", "a/../../b.md"],
        )

        # ---------------------------------------------------------------- #
        # CSV row counting
        # ---------------------------------------------------------------- #
        plain = root / "plain.csv"
        plain.write_bytes(b"a,b\n1,2\n3,4\n5,6\n")
        check.equal("plain CSV data rows are counted", verify.count_csv_data_rows(plain), 3)
        empty = root / "empty.csv"
        empty.write_bytes(b"")
        check.equal("an empty CSV counts zero rows", verify.count_csv_data_rows(empty), 0)
        check.equal("an empty CSV has an empty header", verify.csv_header(empty), [])
        header_only = root / "header_only.csv"
        header_only.write_bytes(b"a,b\n")
        check.equal("a header-only CSV counts zero rows",
                    verify.count_csv_data_rows(header_only), 0)
        crlf = root / "crlf.csv"
        crlf.write_bytes(b"a,b\r\n1,2\r\n3,4\r\n")
        check.equal("CRLF line endings do not inflate the row count",
                    verify.count_csv_data_rows(crlf), 2)
        check.equal("CRLF headers are not polluted by the carriage return",
                    verify.csv_header(crlf), ["a", "b"])
        embedded = root / "embedded.csv"
        embedded.write_bytes(b'a,b\n1,"line one\nline two"\n2,plain\n')
        check.equal(
            "a quoted embedded newline counts as one row, not two",
            verify.count_csv_data_rows(embedded), 2,
        )
        bom = root / "bom.csv"
        bom.write_bytes("﻿a,b\n1,2\n".encode("utf-8"))
        check.equal("a UTF-8 BOM does not corrupt the first header field",
                    verify.csv_header(bom), ["a", "b"])
        check.equal("a UTF-8 BOM does not change the row count",
                    verify.count_csv_data_rows(bom), 1)

        # ---------------------------------------------------------------- #
        # Claim discovery and arithmetic reconciliation
        # ---------------------------------------------------------------- #
        check.equal("a row count embedded in a filename is recovered",
                    verify.claimed_count_in_filename("remaining_review_required_677_to_verify.csv"),
                    677)
        check.equal("the first embedded count wins for multi-number filenames",
                    verify.claimed_count_in_filename("low_priority_uncertain_2654_audit_table.csv"),
                    2654)
        check.check("a filename with no embedded count returns None",
                    verify.claimed_count_in_filename("headline_numbers.csv") is None)
        check.check("reconcile accepts an exact match", verify.reconcile(214, 202 + 12))
        check.check("reconcile rejects an off-by-one", not verify.reconcile(214, 202 + 13))
        check.check("reconcile honours an absolute tolerance",
                    verify.reconcile(1.158761, 100 * 214 / 18468, tolerance=5e-7))
        check.check("reconcile rejects a value outside its tolerance",
                    not verify.reconcile(1.158, 100 * 214 / 18468, tolerance=5e-7))
        check.raises("reconcile rejects a negative tolerance",
                     ValueError, verify.reconcile, 1.0, 1.0, tolerance=-1e-9)

        # ---------------------------------------------------------------- #
        # Viewer reference extraction
        # ---------------------------------------------------------------- #
        networked = """
        <html><head><link rel="stylesheet" href="style.css">
        <script src="https://cdn.example.com/three.min.js"></script></head>
        <body><img src="./figures/panel.png"><a href="#legend">legend</a>
        <img src="data:image/png;base64,AAAA">
        <div style="background: url('assets/bg.png')"></div>
        <script>fetch("viewer_data.json").then(r => r.json());</script>
        </body></html>
        """
        references = verify.extract_viewer_references(networked)
        check.equal(
            "relative src/href/url() paths are all extracted",
            sorted(references.local_paths),
            ["assets/bg.png", "figures/panel.png", "style.css", "viewer_data.json"],
        )
        check.equal("absolute-scheme URLs are classified as external, not local",
                    list(references.external_urls), ["https://cdn.example.com/three.min.js"])
        check.equal("fetch() is detected as a network API",
                    list(references.network_apis), ["fetch"])
        check.check("a fetching page is not self-contained", not references.self_contained)
        check.check("data: URIs and #anchors are never treated as files",
                    not any(item.startswith(("data:", "#")) for item in references.local_paths))

        inline = (
            '<html><body><script id="viewer-data" type="application/json">'
            '{"metadata": {"edge_count": 2}, "edges": [1, 2]}</script>'
            '<script>const d = JSON.parse(document.getElementById("viewer-data").textContent);'
            "</script></body></html>"
        )
        inline_references = verify.extract_viewer_references(inline)
        check.check("a page whose data is inline is reported self-contained",
                    inline_references.self_contained,
                    f"local={inline_references.local_paths}, apis={inline_references.network_apis}")
        check.equal("the inline JSON script id is captured",
                    list(inline_references.inline_data_scripts), ["viewer-data"])
        check.equal("the inline JSON payload parses back to its object",
                    verify.inline_json_payload(inline, "viewer-data")["metadata"]["edge_count"], 2)
        check.raises("an unknown inline script id raises KeyError",
                     KeyError, verify.inline_json_payload, inline, "missing-id")
        escaped = verify.extract_viewer_references('<img src="a&amp;b/panel.png">')
        check.equal("HTML entities inside a path are unescaped",
                    list(escaped.local_paths), ["a&b/panel.png"])
        check.raises("a malformed inline JSON body raises a decode error",
                     json.JSONDecodeError, verify.inline_json_payload,
                     '<script id="bad" type="application/json">{oops</script>', "bad")

        # ---------------------------------------------------------------- #
        # check_integrity end-to-end on a deliberately corrupted packet
        # ---------------------------------------------------------------- #
        broken_root = root / "broken"
        broken_manifest = build_packet(broken_root)
        (broken_root / "good.txt").write_bytes(b"tampered\n")          # wrong hash and size
        (broken_root / "tables" / "rows.csv").unlink()                 # missing file
        (broken_root / "extra_orphan.md").write_bytes(b"# orphan\n")   # unlisted file
        broken_manifest["file_count"] = 99                             # wrong count
        log = verify.ResultLog()
        verify.check_integrity(log, broken_root, broken_manifest)
        status = {result.check_id: result.status for result in log.results}
        for check_id, label in (
            ("INT-04", "a wrong file_count vs len(files)"),
            ("INT-05", "a wrong file_count vs the on-disk count"),
            ("INT-06", "a manifest entry with no file on disk"),
            ("INT-07", "a size that disagrees with the manifest"),
            ("INT-08", "a SHA-256 that disagrees with the manifest"),
            ("INT-10", "an unlisted file on disk"),
        ):
            check.equal(f"check_integrity flags {label}", status.get(check_id), verify.FAIL)
        check.check("check_integrity records a blocking finding for each integrity failure",
                    all(finding["severity"] == "blocking"
                        for finding in log.findings if finding["severity"] != "info"),
                    json.dumps(log.findings, sort_keys=True)[:200])

        clean_root = root / "clean"
        clean_manifest = build_packet(clean_root)
        clean_log = verify.ResultLog()
        verify.check_integrity(clean_log, clean_root, clean_manifest)
        check.check("check_integrity passes an untouched packet",
                    not clean_log.integrity_failed(),
                    json.dumps([r.check_id for r in clean_log.results if r.status == verify.FAIL]))
        check.equal("an untouched packet produces no non-informational findings",
                    [f for f in clean_log.findings if f["severity"] != "info"], [])

        # ---------------------------------------------------------------- #
        # Result-model guards
        # ---------------------------------------------------------------- #
        check.raises("CheckResult rejects an unknown status", ValueError,
                     verify.CheckResult, "X-01", verify.INTEGRITY, "name", "MAYBE")
        check.raises("CheckResult rejects an unknown category", ValueError,
                     verify.CheckResult, "X-01", "invented", "name", verify.PASS)
        gate = verify.ResultLog()
        gate.verdict("A-01", verify.LINKAGE, "a non-integrity failure", False, "broken link")
        check.check("a linkage failure does not trip the integrity gate",
                    not gate.integrity_failed())
        gate.verdict("A-02", verify.INTEGRITY, "an integrity failure", False, "bad hash")
        check.check("an integrity failure trips the integrity gate", gate.integrity_failed())
        check.equal("ResultLog counts pass/fail/skip separately",
                    gate.counts(), {"total": 2, "passed": 0, "failed": 2, "skipped": 0})

    return check.done()


if __name__ == "__main__":
    finish(main())
