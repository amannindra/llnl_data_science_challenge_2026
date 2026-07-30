"""Verify a collaborator handoff packet without trusting any of its claims.

The packet under ``collaboration/`` is read-only evidence: documents, tables,
review panels, agent configs, and a viewer.  This tool re-derives everything it
can and reports each independent check as PASS, FAIL, or SKIP:

* integrity      - manifest completeness, streamed SHA-256, sizes, orphans
* arithmetic     - every headline number reconciled against its own components
* row_counts     - every claimed row count re-counted from the CSV itself
* linkage        - panels <-> index tables, and derived tables <-> label table
* cross_check    - the 18,468-strut claim recomputed from this repo's own data
                   through ``Components.lattice_graph``
* viewer         - referenced asset paths, self-containment, embedded payload

Only an integrity failure sets a nonzero exit status.  Arithmetic, linkage, and
viewer problems are the collaborator's to fix, so they are reported as findings
and still exit 0.  Nothing outside ``--output-dir`` is ever written.

Run:
    conda run -n DSC python Aman_Scripts/collaboration/verify_handoff.py
"""

from __future__ import annotations

import argparse
import csv
import html as html_module
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from Components.asset_io import AssetNotMaterializedError  # noqa: E402
from Components.lattice_graph import (  # noqa: E402
    LatticeGraphError,
    load_lattice_graph,
    weld_coincident_nodes,
)
from Components.paths import find_repository_root, output_path  # noqa: E402
from Components.reporting import (  # noqa: E402
    atomic_write_bytes,
    build_manifest,
    file_sha256,
    json_safe,
    write_csv,
    write_json,
)

DEFAULT_PACKET = Path("collaboration") / "part2_verification_handoff_20260727"
DEFAULT_OUTPUT = Path("collaboration")
REGISTERED_JSON = (
    Path("data") / "missing_struts" / "registered_jsons"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)

PANEL_NAME_PATTERN = re.compile(
    r"^rank_(?P<rank>\d{3})_(?P<edge>E_(?P<node_u>N\d+)_(?P<node_v>N\d+))_ct_panel\.png$"
)
NODE_ID_PATTERN = re.compile(r"^N(\d+)$")
EDGE_ID_PATTERN = re.compile(r"^E_(N\d+)_(N\d+)$")
FILENAME_COUNT_PATTERN = re.compile(r"_(\d{2,})_")

_ATTRIBUTE_REFERENCE = re.compile(
    r"""\b(?:src|href|data-src|data-url|poster)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.IGNORECASE | re.DOTALL,
)
_CSS_URL_REFERENCE = re.compile(r"""url\(\s*(?P<quote>["']?)(?P<value>[^)"']+)(?P=quote)\s*\)""")
_NETWORK_CALL = re.compile(
    r"""(?P<api>fetch|XMLHttpRequest|WebSocket|EventSource|importScripts|navigator\.sendBeacon)"""
)
_DATA_STRING = re.compile(
    r"""["'](?P<value>[^"'\s<>]+\.(?:json|csv|png|jpg|jpeg|svg|js|mjs|css|html|tif|tiff|stl|ply|npy))["']"""
)
_INLINE_SCRIPT = re.compile(
    r"""<script(?P<attributes>[^>]*)>(?P<body>.*?)</script\s*>""", re.IGNORECASE | re.DOTALL
)
_SCRIPT_ID = re.compile(r"""\bid\s*=\s*(["'])(?P<value>.*?)\1""", re.IGNORECASE)
_SCRIPT_TYPE = re.compile(r"""\btype\s*=\s*(["'])(?P<value>.*?)\1""", re.IGNORECASE)

_NON_LOCAL_PREFIXES = ("#", "data:", "javascript:", "mailto:", "tel:", "blob:", "about:")
_ABSOLUTE_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://|^//")

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

INTEGRITY = "integrity"
ARITHMETIC = "arithmetic"
ROW_COUNTS = "row_counts"
LINKAGE = "linkage"
CROSS_CHECK = "cross_check"
VIEWER = "viewer"


# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CheckResult:
    """One independent verification outcome."""

    check_id: str
    category: str
    name: str
    status: str
    detail: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {PASS, FAIL, SKIP}:
            raise ValueError(f"unknown check status: {self.status!r}")
        if self.category not in {
            INTEGRITY, ARITHMETIC, ROW_COUNTS, LINKAGE, CROSS_CHECK, VIEWER
        }:
            raise ValueError(f"unknown check category: {self.category!r}")


class ResultLog:
    """Ordered check results plus free-standing findings."""

    def __init__(self) -> None:
        self.results: list[CheckResult] = []
        self.findings: list[dict[str, str]] = []

    def add(
        self, check_id: str, category: str, name: str, status: str,
        detail: str = "", evidence: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        result = CheckResult(check_id, category, name, status, detail, dict(evidence or {}))
        self.results.append(result)
        if status == FAIL:
            self.finding(check_id, "blocking" if category == INTEGRITY else "warning", detail or name)
        return result

    def verdict(
        self, check_id: str, category: str, name: str, passed: bool,
        detail: str = "", evidence: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        return self.add(check_id, category, name, PASS if passed else FAIL, detail, evidence)

    def skip(
        self, check_id: str, category: str, name: str, reason: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        result = self.add(check_id, category, name, SKIP, reason, evidence)
        self.finding(check_id, "skipped", reason)
        return result

    def finding(self, check_id: str, severity: str, message: str) -> None:
        self.findings.append({"check_id": check_id, "severity": severity, "message": message})

    def note(self, check_id: str, message: str) -> None:
        self.finding(check_id, "info", message)

    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.results),
            "passed": sum(r.status == PASS for r in self.results),
            "failed": sum(r.status == FAIL for r in self.results),
            "skipped": sum(r.status == SKIP for r in self.results),
        }

    def integrity_failed(self) -> bool:
        return any(r.category == INTEGRITY and r.status == FAIL for r in self.results)


# --------------------------------------------------------------------------- #
# Pure helpers (unit tested against synthetic fixtures)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PanelName:
    """The four fields encoded in a review-panel filename."""

    rank: int
    edge_id: str
    node_u: str
    node_v: str


def hash_file(path: str | Path, *, block_size: int = 1 << 20) -> str:
    """Stream a file into SHA-256 without materializing it in memory."""

    return file_sha256(path, block_size=block_size)


def parse_panel_filename(name: str) -> PanelName | None:
    """Parse ``rank_NNN_E_<nodeA>_<nodeB>_ct_panel.png`` or return ``None``."""

    match = PANEL_NAME_PATTERN.match(str(name))
    if match is None:
        return None
    return PanelName(
        int(match.group("rank")), match.group("edge"),
        match.group("node_u"), match.group("node_v"),
    )


def panel_filename(rank: int, edge_id: str) -> str:
    """Rebuild the canonical panel filename for a rank/edge pair."""

    rank = int(rank)
    if rank < 0:
        raise ValueError("panel rank must be nonnegative")
    return f"rank_{rank:03d}_{edge_id}_ct_panel.png"


def parse_edge_id(edge_id: str) -> tuple[str, str] | None:
    """Split ``E_<nodeA>_<nodeB>`` into its two node IDs, or return ``None``."""

    match = EDGE_ID_PATTERN.match(str(edge_id))
    return (match.group(1), match.group(2)) if match else None


def node_number(node_id: str) -> int | None:
    """Return the integer inside ``N000123``, or ``None`` if it is malformed."""

    match = NODE_ID_PATTERN.match(str(node_id))
    return int(match.group(1)) if match else None


def rank_sequence_problems(ranks: Iterable[int], expected_count: int) -> dict[str, list[int]]:
    """Describe how a rank column deviates from a contiguous ``1..N``."""

    observed = [int(rank) for rank in ranks]
    seen: dict[int, int] = {}
    for rank in observed:
        seen[rank] = seen.get(rank, 0) + 1
    expected = set(range(1, int(expected_count) + 1))
    return {
        "duplicates": sorted(rank for rank, count in seen.items() if count > 1),
        "missing": sorted(expected - set(seen)),
        "unexpected": sorted(set(seen) - expected),
    }


def relative_files(root: str | Path) -> set[str]:
    """Return every regular file under ``root`` as a POSIX relative path."""

    base = Path(root)
    return {
        item.relative_to(base).as_posix()
        for item in base.rglob("*")
        if item.is_file() and not item.is_symlink()
    }


def orphan_files(root: str | Path, listed: Iterable[str]) -> list[str]:
    """Return files present on disk but absent from a manifest listing."""

    declared = {Path(entry).as_posix() for entry in listed}
    return sorted(relative_files(root) - declared)


def unsafe_manifest_paths(listed: Iterable[str]) -> list[str]:
    """Return manifest paths that are absolute or escape the packet root."""

    bad: list[str] = []
    for entry in listed:
        text = str(entry)
        candidate = Path(text)
        if candidate.is_absolute() or text.startswith("/") or text.startswith("\\"):
            bad.append(text)
        elif ".." in candidate.parts:
            bad.append(text)
    return sorted(set(bad))


def _reader(handle: Any) -> csv.DictReader:
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    return csv.DictReader(handle)


def iter_csv_rows(path: str | Path) -> Iterator[dict[str, str]]:
    """Stream a CSV as dictionaries, tolerating CRLF and a UTF-8 BOM."""

    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in _reader(handle):
            yield row


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Read a small CSV fully into memory."""

    return list(iter_csv_rows(path))


def count_csv_data_rows(path: str | Path) -> int:
    """Count CSV data rows without loading the file, honouring quoted newlines."""

    total = 0
    for _ in iter_csv_rows(path):
        total += 1
    return total


def csv_header(path: str | Path) -> list[str]:
    """Return a CSV header, or an empty list for an empty file."""

    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(_reader(handle).fieldnames or [])


def claimed_count_in_filename(name: str) -> int | None:
    """Recover a row count embedded in a filename such as ``..._677_...csv``."""

    matches = FILENAME_COUNT_PATTERN.findall(Path(str(name)).stem + "_")
    return int(matches[0]) if matches else None


def reconcile(actual: float, expected: float, *, tolerance: float = 0.0) -> bool:
    """Compare two numbers within an absolute tolerance."""

    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    return abs(float(actual) - float(expected)) <= float(tolerance)


@dataclass(frozen=True)
class ViewerReferences:
    """Everything a viewer page pulls in, and how it pulls it in."""

    local_paths: tuple[str, ...]
    external_urls: tuple[str, ...]
    network_apis: tuple[str, ...]
    inline_data_scripts: tuple[str, ...]

    @property
    def self_contained(self) -> bool:
        return not self.local_paths and not self.external_urls and not self.network_apis


def extract_viewer_references(markup: str) -> ViewerReferences:
    """Extract every asset reference and network call from a viewer page."""

    text = str(markup)
    local: set[str] = set()
    external: set[str] = set()

    def classify(raw: str) -> None:
        value = html_module.unescape(raw).strip()
        if not value or value.startswith(_NON_LOCAL_PREFIXES):
            return
        if _ABSOLUTE_SCHEME.match(value):
            external.add(value)
            return
        cleaned = value.split("#", 1)[0].split("?", 1)[0]
        while cleaned.startswith("./"):
            cleaned = cleaned[2:]
        if cleaned:
            local.add(cleaned)

    for match in _ATTRIBUTE_REFERENCE.finditer(text):
        classify(match.group("value"))
    for match in _CSS_URL_REFERENCE.finditer(text):
        classify(match.group("value"))
    for match in _DATA_STRING.finditer(text):
        classify(match.group("value"))

    apis = sorted({match.group("api") for match in _NETWORK_CALL.finditer(text)})

    inline: list[str] = []
    for match in _INLINE_SCRIPT.finditer(text):
        attributes = match.group("attributes")
        type_match = _SCRIPT_TYPE.search(attributes)
        if type_match is None or "json" not in type_match.group("value").lower():
            continue
        id_match = _SCRIPT_ID.search(attributes)
        inline.append(id_match.group("value") if id_match else "<anonymous>")

    return ViewerReferences(
        tuple(sorted(local)), tuple(sorted(external)), tuple(apis), tuple(sorted(inline))
    )


def inline_json_payload(markup: str, script_id: str) -> Any:
    """Return the parsed JSON body of an inline ``<script type=...json>`` block."""

    for match in _INLINE_SCRIPT.finditer(str(markup)):
        id_match = _SCRIPT_ID.search(match.group("attributes"))
        if id_match is not None and id_match.group("value") == script_id:
            return json.loads(match.group("body"))
    raise KeyError(f"no inline JSON script with id {script_id!r}")


# --------------------------------------------------------------------------- #
# Integrity
# --------------------------------------------------------------------------- #


def check_integrity(log: ResultLog, packet: Path, manifest: Mapping[str, Any]) -> None:
    entries = manifest.get("files")
    if not isinstance(entries, list):
        log.verdict("INT-01", INTEGRITY, "MANIFEST.json exposes a files[] array", False,
                    "MANIFEST.json has no list-valued 'files' key")
        return
    log.verdict("INT-01", INTEGRITY, "MANIFEST.json exposes a files[] array", True,
                f"{len(entries)} entries")

    paths = [str(entry.get("path", "")) for entry in entries]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    log.verdict("INT-02", INTEGRITY, "manifest paths are unique", not duplicates,
                f"duplicate paths: {duplicates[:5]}" if duplicates else f"{len(paths)} unique paths")

    unsafe = unsafe_manifest_paths(paths)
    log.verdict("INT-03", INTEGRITY, "manifest paths stay inside the packet", not unsafe,
                f"unsafe paths: {unsafe[:5]}" if unsafe else "no absolute or '..' paths")

    declared_count = manifest.get("file_count")
    log.verdict("INT-04", INTEGRITY, "file_count equals len(files)",
                declared_count == len(entries),
                f"file_count={declared_count!r}, len(files)={len(entries)}")

    on_disk = relative_files(packet)
    log.verdict("INT-05", INTEGRITY, "file_count equals the recursive on-disk file count",
                declared_count == len(on_disk),
                f"file_count={declared_count!r}, on disk={len(on_disk)}")
    log.note("INT-05", "MANIFEST.json counts itself: it is one of the files[] entries, "
                       "so file_count includes the manifest file")

    missing = [path for path in paths if not (packet / path).is_file()]
    log.verdict("INT-06", INTEGRITY, "every manifest file exists on disk", not missing,
                f"missing: {missing[:5]}" if missing else f"{len(paths)}/{len(paths)} present")

    size_mismatches: list[dict[str, Any]] = []
    hash_mismatches: list[dict[str, Any]] = []
    for entry in entries:
        path = str(entry.get("path", ""))
        target = packet / path
        if not target.is_file():
            continue
        actual_size = target.stat().st_size
        if actual_size != entry.get("size_bytes"):
            size_mismatches.append(
                {"path": path, "actual": actual_size, "declared": entry.get("size_bytes")}
            )
        actual_hash = hash_file(target)
        if actual_hash != entry.get("sha256"):
            hash_mismatches.append(
                {"path": path, "actual": actual_hash, "declared": entry.get("sha256")}
            )

    log.verdict("INT-07", INTEGRITY, "every file's size matches the manifest", not size_mismatches,
                f"{len(size_mismatches)} mismatch(es): "
                f"{[m['path'] for m in size_mismatches][:5]}"
                if size_mismatches else f"{len(paths)} sizes verified",
                {"mismatches": size_mismatches})
    log.verdict("INT-08", INTEGRITY, "every file's SHA-256 matches the manifest", not hash_mismatches,
                f"{len(hash_mismatches)} mismatch(es): "
                f"{[m['path'] for m in hash_mismatches][:5]}"
                if hash_mismatches else f"{len(paths)} hashes verified",
                {"mismatches": hash_mismatches})

    self_name = "MANIFEST.json"
    self_only_hash = [m for m in hash_mismatches if m["path"] != self_name]
    self_only_size = [m for m in size_mismatches if m["path"] != self_name]
    log.verdict("INT-09", INTEGRITY,
                "every payload file (excluding the manifest's self-entry) verifies",
                not self_only_hash and not self_only_size,
                f"{len(paths) - 1} payload files verified"
                if not self_only_hash and not self_only_size
                else f"payload mismatches: {[m['path'] for m in self_only_hash + self_only_size][:5]}")
    if any(m["path"] == self_name for m in hash_mismatches + size_mismatches):
        log.finding(
            "INT-08", "warning",
            "MANIFEST.json contains a self-entry whose size/SHA-256 describe an earlier "
            "revision of itself. A manifest cannot contain its own final hash, so this "
            "entry is unsatisfiable by construction and should be omitted or recorded "
            "in a detached sidecar.",
        )

    orphans = orphan_files(packet, paths)
    log.verdict("INT-10", INTEGRITY, "no unlisted files exist on disk", not orphans,
                f"orphans: {orphans[:5]}" if orphans else "no orphan files",
                {"orphans": orphans})


# --------------------------------------------------------------------------- #
# Arithmetic
# --------------------------------------------------------------------------- #


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def check_arithmetic(
    log: ResultLog, packet: Path, manifest: Mapping[str, Any],
    headline: Mapping[str, str], phase2c: Mapping[str, Any],
    baseline: Mapping[str, Any], viewer_manifest: Mapping[str, Any],
    label_counters: Mapping[str, Mapping[str, int]] | None,
) -> None:
    counts = manifest.get("important_counts", {})
    head = {key: _number(value) for key, value in headline.items()}
    total = head.get("total_expected_struts")
    missing = head.get("auto_supported_possible_unintended_missing")
    disconnected = head.get("auto_supported_possible_unintended_disconnected")
    combined = head.get("auto_supported_possible_unintended_combined")
    percent = head.get("draft_percent")
    reviewed = head.get("reviewed_panels")
    # A claim that is simply absent cannot be reconciled; that is a SKIP, not a FAIL.
    no_headline = "headline_numbers.csv is absent or has no data row" if not headline else None

    if no_headline:
        log.skip("ARI-01", ARITHMETIC, "headline combined == missing + disconnected", no_headline)
    else:
        log.verdict("ARI-01", ARITHMETIC, "headline combined == missing + disconnected",
                    None not in (missing, disconnected, combined)
                    and reconcile(combined, missing + disconnected),
                    f"{combined} vs {missing} + {disconnected} = "
                    f"{None if None in (missing, disconnected) else missing + disconnected}")

    baseline_claim = counts.get("conservative_spotcheck_supported_baseline_candidates")
    if no_headline:
        log.skip("ARI-02", ARITHMETIC, "important_counts baseline == headline combined", no_headline)
    else:
        log.verdict("ARI-02", ARITHMETIC,
                    "important_counts baseline == headline combined",
                    baseline_claim == combined,
                    f"important_counts={baseline_claim}, headline={combined}")

    phase2c_claim = counts.get("phase2c_auto_supported_possible_unintended_candidates")
    promoted = counts.get("newly_promoted_phase2c_rows_to_verify_first")
    if None in (phase2c_claim, baseline_claim, promoted):
        log.skip("ARI-03", ARITHMETIC,
                 "phase2c candidates == baseline candidates + newly promoted rows",
                 "MANIFEST.important_counts is missing one of the three candidate counts")
    else:
        log.verdict("ARI-03", ARITHMETIC,
                    "phase2c candidates == baseline candidates + newly promoted rows",
                    phase2c_claim == baseline_claim + promoted,
                    f"{phase2c_claim} vs {baseline_claim} + {promoted}")

    expected_percent = None if not total or combined is None else 100.0 * combined / total
    if no_headline:
        log.skip("ARI-04", ARITHMETIC, "draft_percent == 100 * combined / total", no_headline)
    else:
        log.verdict("ARI-04", ARITHMETIC, "draft_percent == 100 * combined / total",
                    percent is not None and expected_percent is not None
                    and reconcile(percent, expected_percent, tolerance=5e-7),
                    f"csv={percent}, recomputed={expected_percent}")

    spot_sum = sum(
        value for value in (
            head.get("human_defect_like"), head.get("human_ambiguous"),
            head.get("human_present_like_contradictions"),
        ) if value is not None
    )
    if no_headline:
        log.skip("ARI-05", ARITHMETIC,
                 "human defect_like + ambiguous + contradictions == reviewed_panels", no_headline)
    else:
        log.verdict("ARI-05", ARITHMETIC,
                    "human defect_like + ambiguous + contradictions == reviewed_panels",
                    reviewed is not None and reconcile(spot_sum, reviewed),
                    f"{spot_sum} vs reviewed_panels={reviewed}")

    label_counts_path = packet / "final_report_baseline" / "tables" / "human_spotcheck_label_counts.csv"
    if label_counts_path.is_file():
        rows = read_csv_rows(label_counts_path)
        tally = {row["human_label"]: int(row["count"]) for row in rows}
        defect_like = tally.get("material_absent", 0) + tally.get("material_disconnected", 0)
        log.verdict("ARI-06", ARITHMETIC,
                    "human_spotcheck_label_counts.csv reproduces the headline spot-check",
                    sum(tally.values()) == reviewed
                    and defect_like == head.get("human_defect_like")
                    and tally.get("ambiguous", 0) == head.get("human_ambiguous"),
                    f"tally={tally}, sum={sum(tally.values())}, defect_like={defect_like}")
    else:
        log.skip("ARI-06", ARITHMETIC,
                 "human_spotcheck_label_counts.csv reproduces the headline spot-check",
                 f"missing file: {label_counts_path.name}")

    summary = phase2c.get("summary", {}) if phase2c else {}
    edge_total = summary.get("total_edge_count")
    for check_id, key, label in (
        ("ARI-07", "by_phase2c_label", "label"),
        ("ARI-08", "by_phase2c_status", "status"),
        ("ARI-09", "by_phase2c_triage_bucket", "triage bucket"),
    ):
        breakdown = summary.get(key)
        if not isinstance(breakdown, Mapping):
            log.skip(check_id, ARITHMETIC, f"phase2c {label} breakdown sums to total_edge_count",
                     f"phase2c_summary.json has no {key}")
            continue
        log.verdict(check_id, ARITHMETIC, f"phase2c {label} breakdown sums to total_edge_count",
                    sum(breakdown.values()) == edge_total,
                    f"sum={sum(breakdown.values())}, total_edge_count={edge_total}")

    p2c_missing = summary.get("phase2c_auto_supported_possible_unintended_missing_count")
    p2c_disc = summary.get("phase2c_auto_supported_possible_unintended_disconnected_count")
    p2c_comb = summary.get("phase2c_auto_supported_possible_unintended_combined_count")
    no_summary = "phase2c_summary.json is absent or has no summary block" if not summary else None
    if no_summary or None in (p2c_missing, p2c_disc, p2c_comb):
        log.skip("ARI-10", ARITHMETIC, "phase2c combined == phase2c missing + disconnected",
                 no_summary or "phase2c_summary.json omits a candidate count")
        log.skip("ARI-11", ARITHMETIC, "phase2c combined == important_counts phase2c candidates",
                 no_summary or "phase2c_summary.json omits its combined count")
    else:
        log.verdict("ARI-10", ARITHMETIC, "phase2c combined == phase2c missing + disconnected",
                    p2c_comb == p2c_missing + p2c_disc,
                    f"{p2c_comb} vs {p2c_missing} + {p2c_disc}")
        log.verdict("ARI-11", ARITHMETIC,
                    "phase2c combined == important_counts phase2c candidates",
                    p2c_comb == phase2c_claim,
                    f"summary={p2c_comb}, manifest={phase2c_claim}")

    fraction = summary.get("phase2c_auto_supported_possible_unintended_combined_fraction")
    recomputed_fraction = None if not edge_total or p2c_comb is None else p2c_comb / edge_total
    if fraction is None or recomputed_fraction is None:
        log.skip("ARI-12", ARITHMETIC, "phase2c combined fraction == combined / total_edge_count",
                 no_summary or "phase2c_summary.json omits its combined fraction")
    else:
        log.verdict("ARI-12", ARITHMETIC,
                    "phase2c combined fraction == combined / total_edge_count",
                    reconcile(fraction, recomputed_fraction, tolerance=1e-12),
                    f"json={fraction}, recomputed={recomputed_fraction}")

    template_rows = counts.get("human_verification_template_rows")
    parts = (
        counts.get("newly_promoted_phase2c_rows_to_verify_first"),
        counts.get("remaining_review_required_rows"),
        counts.get("low_priority_uncertain_audit_rows"),
    )
    parts_total = None if None in parts else sum(parts)
    if parts_total is None or template_rows is None:
        log.skip("ARI-13", ARITHMETIC,
                 "human_verification_template_rows == sum of its three sub-queue counts",
                 "MANIFEST.important_counts omits a sub-queue or template row count")
    else:
        log.verdict("ARI-13", ARITHMETIC,
                    "human_verification_template_rows == sum of its three sub-queue counts",
                    template_rows == parts_total,
                    f"{template_rows} vs {' + '.join(str(part) for part in parts)} = {parts_total}")

    auto = baseline.get("automated_review", {}) if baseline else {}
    baseline_parts = {
        "combined": auto.get("auto_supported_possible_unintended_combined"),
        "designed_removed": auto.get("auto_supported_designed_removed_absent_or_disconnected"),
        "present_like": auto.get("auto_supported_present_like"),
        "blocked": auto.get("blocked_manual_review"),
        "low_priority": auto.get("low_priority_uncertain_not_reported_as_defect"),
    }
    if all(value is not None for value in baseline_parts.values()):
        log.verdict("ARI-14", ARITHMETIC,
                    "baseline label partition sums to total_expected_struts",
                    sum(baseline_parts.values()) == auto.get("total_expected_struts"),
                    f"{' + '.join(str(v) for v in baseline_parts.values())} = "
                    f"{sum(baseline_parts.values())} vs {auto.get('total_expected_struts')}")
        blocked = baseline_parts["blocked"]
        low_delta = (summary.get("phase2c_low_priority_not_reported_as_defect_count", 0)
                     - baseline_parts["low_priority"])
        reallocated = (counts.get("newly_promoted_phase2c_rows_to_verify_first", 0)
                       + counts.get("remaining_review_required_rows", 0) + low_delta)
        log.verdict("ARI-15", ARITHMETIC,
                    "phase2c re-triages exactly the baseline's blocked rows",
                    blocked == reallocated,
                    f"blocked={blocked} vs promoted+review_required+low_priority_delta="
                    f"{counts.get('newly_promoted_phase2c_rows_to_verify_first')}+"
                    f"{counts.get('remaining_review_required_rows')}+{low_delta}={reallocated}")
    else:
        log.skip("ARI-14", ARITHMETIC, "baseline label partition sums to total_expected_struts",
                 "final_ct_defect_summary.json is missing automated_review fields")
        log.skip("ARI-15", ARITHMETIC, "phase2c re-triages exactly the baseline's blocked rows",
                 "final_ct_defect_summary.json is missing automated_review fields")

    baseline_percent = auto.get("draft_auto_supported_possible_unintended_percent")
    if baseline_percent is None or percent is None:
        log.skip("ARI-16", ARITHMETIC,
                 "final_ct_defect_summary percent agrees with headline_numbers.csv",
                 no_headline or "final_ct_defect_summary.json omits its draft percent")
    else:
        log.verdict("ARI-16", ARITHMETIC,
                    "final_ct_defect_summary percent agrees with headline_numbers.csv",
                    reconcile(baseline_percent, percent, tolerance=5e-7),
                    f"json={baseline_percent}, csv={percent}")

    class_counts = viewer_manifest.get("class_counts", {}) if viewer_manifest else {}
    if class_counts:
        log.verdict("ARI-17", ARITHMETIC, "viewer class_counts sum to the viewer edge_count",
                    sum(class_counts.values()) == viewer_manifest.get("edge_count"),
                    f"sum={sum(class_counts.values())}, edge_count={viewer_manifest.get('edge_count')}")
    else:
        log.skip("ARI-17", ARITHMETIC, "viewer class_counts sum to the viewer edge_count",
                 "viewer/run_manifest.json has no class_counts")

    if label_counters is not None:
        for check_id, key, name in (
            ("ARI-18", "by_phase2c_label", "phase2c_label"),
            ("ARI-19", "by_phase2c_status", "phase2c_status"),
            ("ARI-20", "by_phase2c_triage_bucket", "phase2c_triage_bucket"),
        ):
            declared = summary.get(key)
            actual = label_counters.get(key)
            log.verdict(check_id, ARITHMETIC,
                        f"phase2c_labels.csv {name} tally reproduces phase2c_summary.json",
                        isinstance(declared, Mapping) and dict(actual or {}) == dict(declared),
                        "recounted tally matches" if dict(actual or {}) == dict(declared or {})
                        else f"recounted={dict(actual or {})}, declared={dict(declared or {})}")
    else:
        for check_id, name in (("ARI-18", "phase2c_label"), ("ARI-19", "phase2c_status"),
                               ("ARI-20", "phase2c_triage_bucket")):
            log.skip(check_id, ARITHMETIC,
                     f"phase2c_labels.csv {name} tally reproduces phase2c_summary.json",
                     "phase2c_labels.csv unavailable")


# --------------------------------------------------------------------------- #
# Row counts
# --------------------------------------------------------------------------- #


def discover_row_claims(
    packet: Path, manifest: Mapping[str, Any], phase2c: Mapping[str, Any],
    headline: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Collect every row count the packet claims, and where it claims it."""

    counts = manifest.get("important_counts", {})
    summary = phase2c.get("summary", {}) if phase2c else {}
    claims: list[dict[str, Any]] = []

    def add(relative: str, claimed: Any, source: str) -> None:
        if claimed is None:
            return
        claims.append({"path": relative, "claimed": int(claimed), "claim_source": source})

    add("review_tables/newly_promoted_14_to_verify.csv",
        counts.get("newly_promoted_phase2c_rows_to_verify_first"),
        "MANIFEST.important_counts.newly_promoted_phase2c_rows_to_verify_first")
    add("review_tables/remaining_review_required_677_to_verify.csv",
        counts.get("remaining_review_required_rows"),
        "MANIFEST.important_counts.remaining_review_required_rows")
    add("review_tables/low_priority_uncertain_2654_audit_table.csv",
        counts.get("low_priority_uncertain_audit_rows"),
        "MANIFEST.important_counts.low_priority_uncertain_audit_rows")
    add("review_tables/human_verification_template.csv",
        counts.get("human_verification_template_rows"),
        "MANIFEST.important_counts.human_verification_template_rows")
    add("review_tables/phase2c_auto_supported_unintended_candidates.csv",
        counts.get("phase2c_auto_supported_possible_unintended_candidates"),
        "MANIFEST.important_counts.phase2c_auto_supported_possible_unintended_candidates")
    add("review_tables/phase2c_labels.csv", summary.get("total_edge_count"),
        "phase2c_summary.json.summary.total_edge_count")
    add("review_tables/phase2c_remaining_review_queue.csv",
        summary.get("phase2c_remaining_review_required_count"),
        "phase2c_summary.json.summary.phase2c_remaining_review_required_count")
    add("final_report_baseline/tables/auto_supported_unintended_candidates.csv",
        _number(headline.get("auto_supported_possible_unintended_combined")),
        "headline_numbers.csv.auto_supported_possible_unintended_combined")
    add("final_report_baseline/tables/manual_review_queue.csv",
        _number(headline.get("blocked_manual_review_rows")),
        "headline_numbers.csv.blocked_manual_review_rows")
    add("final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv",
        _number(headline.get("reviewed_panels")), "headline_numbers.csv.reviewed_panels")

    panel_json = packet / "review_panels_phase2c_top120" / "ct_edge_panel_summary.json"
    if panel_json.is_file():
        try:
            payload = json.loads(panel_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        add("review_panels_phase2c_top120/ct_edge_panel_summary.csv", payload.get("edge_count"),
            "ct_edge_panel_summary.json.edge_count")
        add("review_tables/review_panel_index.csv", payload.get("edge_count"),
            "ct_edge_panel_summary.json.edge_count (same 120-panel review packet)")

    # Names that encode their own row count are self-claiming.
    for relative in ("review_tables/newly_promoted_14_to_verify.csv",
                     "review_tables/remaining_review_required_677_to_verify.csv",
                     "review_tables/low_priority_uncertain_2654_audit_table.csv"):
        embedded = claimed_count_in_filename(Path(relative).name)
        add(relative, embedded, "filename")
    return claims


def check_row_counts(log: ResultLog, packet: Path, claims: Sequence[Mapping[str, Any]]) -> None:
    cache: dict[str, int] = {}
    for index, claim in enumerate(claims, start=1):
        check_id = f"ROW-{index:02d}"
        relative = str(claim["path"])
        name = f"{relative} has {claim['claimed']} data rows"
        target = packet / relative
        if not target.is_file():
            log.skip(check_id, ROW_COUNTS, name, f"missing file: {relative}")
            continue
        if relative not in cache:
            cache[relative] = count_csv_data_rows(target)
        actual = cache[relative]
        log.verdict(check_id, ROW_COUNTS, name, actual == claim["claimed"],
                    f"actual={actual}, claimed={claim['claimed']} "
                    f"(source: {claim['claim_source']})")


# --------------------------------------------------------------------------- #
# Linkage
# --------------------------------------------------------------------------- #


def check_panel_linkage(log: ResultLog, packet: Path) -> None:
    panel_dir = packet / "review_panels_phase2c_top120"
    summary_csv = panel_dir / "ct_edge_panel_summary.csv"
    if not panel_dir.is_dir() or not summary_csv.is_file():
        log.skip("LNK-01", LINKAGE, "panel summary references every panel PNG",
                 "review_panels_phase2c_top120/ct_edge_panel_summary.csv is missing")
        return

    on_disk = sorted(item.name for item in panel_dir.glob("*.png"))
    rows = read_csv_rows(summary_csv)
    referenced = [Path(row.get("output_path", "")).name for row in rows]
    log.note("LNK-01", "ct_edge_panel_summary.csv output_path values point at the collaborator's "
                       "own run directory (outputs/part2/phase2c/...); linkage is matched on the "
                       "filename component only")

    absent = sorted(set(referenced) - set(on_disk))
    orphaned = sorted(set(on_disk) - set(referenced))
    log.verdict("LNK-01", LINKAGE, "every panel referenced by the summary exists on disk",
                not absent, f"missing: {absent[:5]}" if absent else f"{len(referenced)} referenced")
    log.verdict("LNK-02", LINKAGE, "every panel PNG on disk appears in the summary",
                not orphaned, f"orphaned: {orphaned[:5]}" if orphaned else f"{len(on_disk)} on disk")

    unparsable = [name for name in on_disk if parse_panel_filename(name) is None]
    log.verdict("LNK-03", LINKAGE, "every panel filename follows rank_NNN_E_<u>_<v>_ct_panel.png",
                not unparsable, f"unparsable: {unparsable[:5]}" if unparsable
                else f"{len(on_disk)} filenames parsed")

    parsed = [parse_panel_filename(name) for name in on_disk]
    ranks = [item.rank for item in parsed if item is not None]
    problems = rank_sequence_problems(ranks, len(on_disk))
    log.verdict("LNK-04", LINKAGE, f"panel ranks are contiguous 1..{len(on_disk)}",
                not any(problems.values()), json.dumps(problems, sort_keys=True))

    filename_mismatch: list[str] = []
    node_mismatch: list[str] = []
    for row in rows:
        name = Path(row.get("output_path", "")).name
        parsed_row = parse_panel_filename(name)
        if parsed_row is None:
            filename_mismatch.append(name or "<empty>")
            continue
        if parsed_row.edge_id != row.get("edge_id") or parsed_row.rank != int(row.get("rank", -1)):
            filename_mismatch.append(name)
        nodes = parse_edge_id(str(row.get("edge_id", "")))
        if nodes is None or (parsed_row.node_u, parsed_row.node_v) != nodes:
            node_mismatch.append(name)
    log.verdict("LNK-05", LINKAGE, "panel filename rank/edge match the summary row",
                not filename_mismatch,
                f"mismatches: {filename_mismatch[:5]}" if filename_mismatch
                else f"{len(rows)} rows agree")
    log.verdict("LNK-06", LINKAGE, "panel filename node pair matches the row's edge_id",
                not node_mismatch,
                f"mismatches: {node_mismatch[:5]}" if node_mismatch else f"{len(rows)} rows agree")

    for check_id, relative, label in (
        ("LNK-07", "review_tables/review_panel_index.csv", "review_panel_index.csv"),
        ("LNK-08", "final_report_baseline/tables/spotcheck_panel_index.csv",
         "spotcheck_panel_index.csv"),
    ):
        index_path = packet / relative
        if not index_path.is_file():
            log.skip(check_id, LINKAGE, f"{label} panels resolve to files in this packet",
                     f"missing file: {relative}")
            continue
        index_rows = read_csv_rows(index_path)
        expected = [panel_filename(int(row["rank"]), row["edge_id"]) for row in index_rows]
        present = [name for name in expected if (panel_dir / name).is_file()]
        index_problems = rank_sequence_problems(
            (int(row["rank"]) for row in index_rows), len(index_rows)
        )
        log.verdict(f"{check_id}a", LINKAGE, f"{label} ranks are contiguous 1..{len(index_rows)}",
                    not any(index_problems.values()), json.dumps(index_problems, sort_keys=True))
        bad_edges = [row["edge_id"] for row in index_rows
                     if parse_edge_id(row["edge_id"]) is None]
        log.verdict(f"{check_id}b", LINKAGE, f"{label} edge_id values parse to a node pair",
                    not bad_edges, f"unparsable: {bad_edges[:5]}" if bad_edges
                    else f"{len(index_rows)} edge IDs parsed")
        log.verdict(check_id, LINKAGE, f"{label} panels resolve to files in this packet",
                    len(present) == len(expected),
                    f"{len(present)}/{len(expected)} derived panel filenames present",
                    {"absent_examples": sorted(set(expected) - set(present))[:5]})
        if len(present) != len(expected):
            log.finding(
                check_id, "info",
                f"{label} indexes {len(expected)} panels from a run whose PNGs are not shipped "
                f"in this packet ({len(expected) - len(present)} absent). Only the 120 Phase 2C "
                f"panels under review_panels_phase2c_top120/ are included.",
            )


def check_table_linkage(
    log: ResultLog, packet: Path, edge_records: Mapping[str, tuple[str, str, str]] | None,
) -> None:
    derived = [
        ("LNK-10", "review_tables/newly_promoted_14_to_verify.csv"),
        ("LNK-11", "review_tables/remaining_review_required_677_to_verify.csv"),
        ("LNK-12", "review_tables/low_priority_uncertain_2654_audit_table.csv"),
        ("LNK-13", "review_tables/human_verification_template.csv"),
        ("LNK-14", "review_tables/phase2c_auto_supported_unintended_candidates.csv"),
        ("LNK-15", "review_tables/phase2c_remaining_review_queue.csv"),
        ("LNK-16", "review_tables/review_panel_index.csv"),
        ("LNK-17", "review_panels_phase2c_top120/ct_edge_panel_summary.csv"),
        ("LNK-18", "final_report_baseline/tables/spotcheck_panel_index.csv"),
        ("LNK-19", "final_report_baseline/tables/auto_supported_unintended_candidates.csv"),
        ("LNK-20", "final_report_baseline/tables/manual_review_queue.csv"),
        ("LNK-21", "final_report_baseline/tables/human_spotcheck_labels_rank001_040.csv"),
    ]
    for check_id, relative in derived:
        name = f"{Path(relative).name} edge IDs are all present in phase2c_labels.csv"
        target = packet / relative
        if edge_records is None:
            log.skip(check_id, LINKAGE, name, "phase2c_labels.csv unavailable")
            continue
        if not target.is_file():
            log.skip(check_id, LINKAGE, name, f"missing file: {relative}")
            continue
        rows = read_csv_rows(target)
        if not rows or "edge_id" not in rows[0]:
            log.skip(check_id, LINKAGE, name, f"{relative} has no edge_id column")
            continue
        ids = [row["edge_id"] for row in rows]
        unknown = sorted({eid for eid in ids if eid not in edge_records})
        duplicated = len(ids) != len(set(ids))
        node_disagreement = [
            row["edge_id"] for row in rows
            if {"node_u", "node_v"} <= set(row)
            and parse_edge_id(row["edge_id"]) != (row["node_u"], row["node_v"])
        ]
        problems = []
        if unknown:
            problems.append(f"{len(unknown)} unknown edge IDs e.g. {unknown[:3]}")
        if duplicated:
            problems.append("duplicate edge IDs")
        if node_disagreement:
            problems.append(f"{len(node_disagreement)} edge_id/node column disagreements")
        log.verdict(check_id, LINKAGE, name, not problems,
                    "; ".join(problems) if problems
                    else f"{len(ids)} unique edge IDs resolve against the label table")

    template = packet / "review_tables" / "human_verification_template.csv"
    if template.is_file():
        rows = read_csv_rows(template)
        queues: dict[str, int] = {}
        for row in rows:
            queues[row.get("verification_queue", "")] = queues.get(row.get("verification_queue", ""), 0) + 1
        expected_queues = {}
        for relative, queue_key in (
            ("review_tables/newly_promoted_14_to_verify.csv", "newly_promoted_14_first_priority"),
            ("review_tables/remaining_review_required_677_to_verify.csv",
             "remaining_review_required_677_second_priority"),
            ("review_tables/low_priority_uncertain_2654_audit_table.csv",
             "low_priority_uncertain_2654_audit_only"),
        ):
            source = packet / relative
            if source.is_file():
                expected_queues[queue_key] = count_csv_data_rows(source)
        log.verdict("LNK-22", LINKAGE,
                    "human_verification_template.csv queue composition matches its three sources",
                    queues == expected_queues,
                    f"template={queues}, sources={expected_queues}")
    else:
        log.skip("LNK-22", LINKAGE,
                 "human_verification_template.csv queue composition matches its three sources",
                 "missing file: review_tables/human_verification_template.csv")

    spot_labels = packet / "final_report_baseline" / "tables" / "human_spotcheck_labels_rank001_040.csv"
    spot_index = packet / "final_report_baseline" / "tables" / "spotcheck_panel_index.csv"
    if spot_labels.is_file() and spot_index.is_file():
        labels = read_csv_rows(spot_labels)
        index = read_csv_rows(spot_index)
        prefix = [(int(row["rank"]), row["edge_id"]) for row in index[: len(labels)]]
        observed = [(int(row["rank"]), row["edge_id"]) for row in labels]
        log.verdict("LNK-23", LINKAGE,
                    "human spot-check labels cover the top-ranked spotcheck panel rows",
                    prefix == observed,
                    f"{len(labels)} labelled rows align with spotcheck_panel_index ranks "
                    f"1..{len(labels)}" if prefix == observed else "rank/edge order disagrees")
    else:
        log.skip("LNK-23", LINKAGE,
                 "human spot-check labels cover the top-ranked spotcheck panel rows",
                 "spot-check label or index table is missing")


# --------------------------------------------------------------------------- #
# Cross-validation against this repository's own data
# --------------------------------------------------------------------------- #


def check_cross_validation(
    log: ResultLog, repository: Path, manifest: Mapping[str, Any],
    edge_records: Mapping[str, tuple[str, str, str]] | None,
    panel_nodes: Iterable[str],
) -> None:
    counts = manifest.get("important_counts", {})
    claimed_total = counts.get("total_expected_struts")
    registered = repository / REGISTERED_JSON
    reason: str | None = None
    if not registered.is_file():
        reason = f"registered lattice JSON not present: {REGISTERED_JSON.as_posix()}"

    graph = None
    welded = None
    if reason is None:
        try:
            graph = load_lattice_graph(registered)
            welded = weld_coincident_nodes(graph, tolerance=1e-6)
        except (AssetNotMaterializedError, LatticeGraphError, MemoryError, OSError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
            graph = welded = None
        except Exception as exc:  # noqa: BLE001 - never fail the run on cross-validation.
            reason = f"{type(exc).__name__}: {exc}"
            graph = welded = None

    if graph is None or welded is None:
        for check_id, name in (
            ("XVL-01", "registered lattice JSON parses to 10,206 junction records"),
            ("XVL-02", "coincident-node welding yields 3,430 physical nodes"),
            ("XVL-03", "welded strut count reproduces the packet's total_expected_struts"),
            ("XVL-04", "packet node IDs fall inside the source junction ID range"),
            ("XVL-05", "packet edge set equals this repo's welded strut set"),
            ("XVL-06", "packet source_strut_id values are real source strut IDs"),
        ):
            log.skip(check_id, CROSS_CHECK, name, reason or "cross-validation unavailable")
        return

    log.verdict("XVL-01", CROSS_CHECK, "registered lattice JSON parses to 10,206 junction records",
                len(graph.junctions) == 10206,
                f"junctions={len(graph.junctions)}, source struts={len(graph.struts)}, "
                f"unit cells={len(graph.unit_cells)}")
    log.verdict("XVL-02", CROSS_CHECK, "coincident-node welding yields 3,430 physical nodes",
                len(welded.nodes) == 3430, f"welded nodes={len(welded.nodes)}")
    log.verdict("XVL-03", CROSS_CHECK,
                "welded strut count reproduces the packet's total_expected_struts",
                len(welded.struts) == claimed_total,
                f"recomputed={len(welded.struts)} from "
                f"{REGISTERED_JSON.as_posix()}, packet claims {claimed_total}")

    junction_ids = {junction.id for junction in graph.junctions}
    junction_to_node = dict(welded.junction_to_node)
    node_numbers = {node_number(node) for node in panel_nodes}
    invalid = sorted(number for number in node_numbers
                     if number is None or number not in junction_ids)
    log.verdict("XVL-04", CROSS_CHECK, "packet node IDs fall inside the source junction ID range",
                not invalid,
                f"{len(node_numbers)} distinct node IDs in "
                f"[{min(junction_ids)}, {max(junction_ids)}]" if not invalid
                else f"{len(invalid)} out-of-range IDs e.g. {invalid[:5]}")

    if edge_records is None:
        log.skip("XVL-05", CROSS_CHECK, "packet edge set equals this repo's welded strut set",
                 "phase2c_labels.csv unavailable")
        log.skip("XVL-06", CROSS_CHECK, "packet source_strut_id values are real source strut IDs",
                 "phase2c_labels.csv unavailable")
        return

    repository_pairs = {tuple(sorted((strut.node0, strut.node1))) for strut in welded.struts}
    packet_pairs: set[tuple[int, int]] = set()
    unmapped = 0
    for edge_id in edge_records:
        nodes = parse_edge_id(edge_id)
        if nodes is None:
            unmapped += 1
            continue
        left, right = (node_number(nodes[0]), node_number(nodes[1]))
        if left not in junction_to_node or right not in junction_to_node:
            unmapped += 1
            continue
        packet_pairs.add(tuple(sorted((junction_to_node[left], junction_to_node[right]))))
    only_packet = len(packet_pairs - repository_pairs)
    only_repository = len(repository_pairs - packet_pairs)
    log.verdict("XVL-05", CROSS_CHECK, "packet edge set equals this repo's welded strut set",
                not unmapped and not only_packet and not only_repository,
                f"packet={len(packet_pairs)}, repo={len(repository_pairs)}, "
                f"packet-only={only_packet}, repo-only={only_repository}, unmapped={unmapped}")

    strut_ids = {strut.id for strut in graph.struts}
    packet_strut_ids: set[int] = set()
    bad_strut_ids = 0
    for _, _, source_strut_id in edge_records.values():
        try:
            packet_strut_ids.add(int(source_strut_id))
        except (TypeError, ValueError):
            bad_strut_ids += 1
    outside = sorted(packet_strut_ids - strut_ids)
    log.verdict("XVL-06", CROSS_CHECK, "packet source_strut_id values are real source strut IDs",
                not outside and not bad_strut_ids,
                f"{len(packet_strut_ids)} distinct IDs inside [{min(strut_ids)}, {max(strut_ids)}]"
                if not outside and not bad_strut_ids
                else f"{len(outside)} outside e.g. {outside[:5]}, {bad_strut_ids} unparsable")


# --------------------------------------------------------------------------- #
# Viewer
# --------------------------------------------------------------------------- #


def check_viewer(log: ResultLog, packet: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    entrypoint = str(manifest.get("viewer_entrypoint", "viewer/index.html"))
    target = packet / entrypoint
    if not target.is_file():
        for check_id, name in (
            ("VWR-01", "the manifest's viewer_entrypoint exists"),
            ("VWR-02", "every path the viewer references exists"),
            ("VWR-03", "the viewer is self-contained (no fetch/XHR/external hosts)"),
            ("VWR-04", "the viewer's embedded payload parses and matches its edge_count"),
        ):
            log.skip(check_id, VIEWER, name, f"missing viewer entrypoint: {entrypoint}")
        return {}
    log.verdict("VWR-01", VIEWER, "the manifest's viewer_entrypoint exists", True, entrypoint)

    markup = target.read_text(encoding="utf-8", errors="replace")
    references = extract_viewer_references(markup)
    broken = [item for item in references.local_paths
              if not (target.parent / item).exists() and not (packet / item).exists()]
    log.verdict("VWR-02", VIEWER, "every path the viewer references exists", not broken,
                f"broken: {broken[:5]}" if broken
                else f"{len(references.local_paths)} referenced local path(s)",
                {"local_paths": list(references.local_paths)})
    log.verdict("VWR-03", VIEWER, "the viewer is self-contained (no fetch/XHR/external hosts)",
                references.self_contained,
                f"network APIs={list(references.network_apis)}, "
                f"external={list(references.external_urls)[:3]}, "
                f"local refs={list(references.local_paths)[:3]}"
                if not references.self_contained
                else f"no network calls; data arrives via inline "
                     f"<script type=application/json> block(s) {list(references.inline_data_scripts)}")

    payload_summary: dict[str, Any] = {}
    if references.inline_data_scripts:
        script_id = references.inline_data_scripts[0]
        try:
            payload = inline_json_payload(markup, script_id)
        except (KeyError, json.JSONDecodeError) as exc:
            log.verdict("VWR-04", VIEWER,
                        "the viewer's embedded payload parses and matches its edge_count", False,
                        f"{type(exc).__name__}: {exc}")
            return payload_summary
        edges = payload.get("edges", []) if isinstance(payload, Mapping) else []
        metadata = payload.get("metadata", {}) if isinstance(payload, Mapping) else {}
        declared = metadata.get("edge_count")
        class_counts: dict[str, int] = {}
        for edge in edges:
            key = str(edge.get("class_name"))
            class_counts[key] = class_counts.get(key, 0) + 1
        run_manifest_path = target.parent / "run_manifest.json"
        run_counts: Mapping[str, Any] = {}
        if run_manifest_path.is_file():
            run_counts = json.loads(run_manifest_path.read_text(encoding="utf-8")).get(
                "class_counts", {}
            )
        agrees = len(edges) == declared and (not run_counts or class_counts == dict(run_counts))
        log.verdict("VWR-04", VIEWER,
                    "the viewer's embedded payload parses and matches its edge_count", agrees,
                    f"inline edges={len(edges)}, metadata.edge_count={declared}, "
                    f"class tally {'matches' if class_counts == dict(run_counts) else 'differs from'} "
                    f"run_manifest.json")
        payload_summary = {
            "script_id": script_id, "edges": len(edges), "declared_edge_count": declared,
            "class_counts": class_counts,
        }
        sidecar = target.parent / "viewer_data.json"
        if sidecar.is_file():
            try:
                duplicate = json.loads(sidecar.read_text(encoding="utf-8")) == payload
            except json.JSONDecodeError:
                duplicate = False
            if duplicate:
                log.note("VWR-04",
                         "viewer/viewer_data.json duplicates the payload already embedded in "
                         "index.html; index.html never references it, so the sidecar "
                         "(10.5 MiB) is redundant inside the packet")
    else:
        log.verdict("VWR-04", VIEWER,
                    "the viewer's embedded payload parses and matches its edge_count", False,
                    "no inline <script type=application/json> data block found")

    unreferenced = sorted(
        item.name for item in target.parent.iterdir()
        if item.is_file() and item.name != target.name and item.name not in references.local_paths
    )
    if unreferenced:
        log.note("VWR-02", f"viewer sidecar files never referenced by {entrypoint}: {unreferenced}")
    log.note("VWR-03", "the viewer opens directly from the filesystem (file://) because it makes "
                       "no fetch/XHR calls; no local web server is required")
    return payload_summary


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_label_table(
    path: Path,
) -> tuple[dict[str, tuple[str, str, str]], dict[str, dict[str, int]], set[str]] | None:
    """Stream phase2c_labels.csv into edge records, tallies, and its node ID set."""

    if not path.is_file():
        return None
    records: dict[str, tuple[str, str, str]] = {}
    tallies = {
        "by_phase2c_label": {}, "by_phase2c_status": {}, "by_phase2c_triage_bucket": {},
    }
    nodes: set[str] = set()
    columns = {
        "by_phase2c_label": "phase2c_label",
        "by_phase2c_status": "phase2c_status",
        "by_phase2c_triage_bucket": "phase2c_triage_bucket",
    }
    for row in iter_csv_rows(path):
        edge_id = row.get("edge_id", "")
        records[edge_id] = (
            row.get("phase2c_label", ""), row.get("phase2c_status", ""),
            row.get("source_strut_id", ""),
        )
        nodes.add(row.get("node_u", ""))
        nodes.add(row.get("node_v", ""))
        for key, column in columns.items():
            value = row.get(column, "")
            tallies[key][value] = tallies[key].get(value, 0) + 1
    return records, tallies, nodes


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def build_report(
    log: ResultLog, packet_relative: str, manifest: Mapping[str, Any],
    viewer_summary: Mapping[str, Any],
) -> dict[str, Any]:
    counts = log.counts()
    by_category: dict[str, dict[str, int]] = {}
    for result in log.results:
        bucket = by_category.setdefault(
            result.category, {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        )
        bucket["total"] += 1
        bucket[{PASS: "passed", FAIL: "failed", SKIP: "skipped"}[result.status]] += 1
    return {
        "tool": "verify_handoff",
        "packet": packet_relative,
        "packet_created_utc": manifest.get("created_utc"),
        "packet_name": manifest.get("packet_name"),
        "integrity_gate": "FAIL" if log.integrity_failed() else "PASS",
        "totals": counts,
        "by_category": by_category,
        "checks": [
            {
                "check_id": result.check_id, "category": result.category, "name": result.name,
                "status": result.status, "detail": result.detail,
                "evidence": json_safe(dict(result.evidence)),
            }
            for result in log.results
        ],
        "findings": log.findings,
        "viewer": json_safe(dict(viewer_summary)),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    totals = report["totals"]
    lines = [
        "# Collaborator handoff verification",
        "",
        f"Packet: `{report['packet']}` (created {report['packet_created_utc']})",
        "",
        f"- Checks: {totals['total']} total, {totals['passed']} PASS, "
        f"{totals['failed']} FAIL, {totals['skipped']} SKIP",
        f"- Integrity gate: **{report['integrity_gate']}**",
        "",
        "## Results by category",
        "",
        "| Category | Total | Pass | Fail | Skip |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for category in sorted(report["by_category"]):
        bucket = report["by_category"][category]
        lines.append(
            f"| {category} | {bucket['total']} | {bucket['passed']} | "
            f"{bucket['failed']} | {bucket['skipped']} |"
        )
    lines += ["", "## Checks", "", "| ID | Category | Status | Check | Detail |",
              "| --- | --- | --- | --- | --- |"]
    for check in report["checks"]:
        detail = str(check["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {check['check_id']} | {check['category']} | {check['status']} | "
            f"{check['name']} | {detail} |"
        )
    lines += ["", "## Findings", ""]
    if not report["findings"]:
        lines.append("No findings.")
    for finding in report["findings"]:
        lines.append(f"- **{finding['severity']}** ({finding['check_id']}): {finding['message']}")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    repository = find_repository_root()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--handoff-dir", default=str(repository / DEFAULT_PACKET),
                        help="collaborator packet to verify")
    parser.add_argument("--output-dir", default=None,
                        help="default: Aman_Scripts/outputs/collaboration")
    parser.add_argument("--skip-cross-check", action="store_true",
                        help="skip the lattice-graph recomputation from data/")
    parser.add_argument("--quiet", action="store_true", help="print only the summary lines")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    repository = find_repository_root()
    packet = Path(arguments.handoff_dir).expanduser().resolve(strict=False)
    if not packet.is_dir():
        print(f"handoff directory not found: {packet}", file=sys.stderr)
        return 2
    output_directory = (
        Path(arguments.output_dir).expanduser().resolve(strict=False)
        if arguments.output_dir else output_path(DEFAULT_OUTPUT)
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    try:
        packet_relative = packet.relative_to(repository).as_posix()
    except ValueError:
        packet_relative = packet.as_posix()

    log = ResultLog()
    manifest = _load_json(packet / "MANIFEST.json")
    if not manifest:
        print(f"MANIFEST.json missing or unparsable under {packet}", file=sys.stderr)
        return 2

    check_integrity(log, packet, manifest)

    headline_path = packet / "final_report_baseline" / "tables" / "headline_numbers.csv"
    headline_rows = read_csv_rows(headline_path) if headline_path.is_file() else []
    headline = headline_rows[0] if headline_rows else {}
    phase2c = _load_json(packet / "review_tables" / "phase2c_summary.json")
    baseline = _load_json(packet / "final_report_baseline" / "final_ct_defect_summary.json")
    viewer_manifest = _load_json(packet / "viewer" / "run_manifest.json")

    loaded = load_label_table(packet / "review_tables" / "phase2c_labels.csv")
    edge_records, tallies, label_nodes = loaded if loaded else (None, None, set())

    check_arithmetic(log, packet, manifest, headline, phase2c, baseline, viewer_manifest, tallies)
    check_row_counts(log, packet, discover_row_claims(packet, manifest, phase2c, headline))
    check_panel_linkage(log, packet)
    check_table_linkage(log, packet, edge_records)

    panel_nodes: set[str] = set(label_nodes)
    for item in (packet / "review_panels_phase2c_top120").glob("*.png"):
        parsed = parse_panel_filename(item.name)
        if parsed is not None:
            panel_nodes.update((parsed.node_u, parsed.node_v))
    if arguments.skip_cross_check:
        for check_id, name in (
            ("XVL-01", "registered lattice JSON parses to 10,206 junction records"),
            ("XVL-02", "coincident-node welding yields 3,430 physical nodes"),
            ("XVL-03", "welded strut count reproduces the packet's total_expected_struts"),
            ("XVL-04", "packet node IDs fall inside the source junction ID range"),
            ("XVL-05", "packet edge set equals this repo's welded strut set"),
            ("XVL-06", "packet source_strut_id values are real source strut IDs"),
        ):
            log.skip(check_id, CROSS_CHECK, name, "--skip-cross-check requested")
    else:
        check_cross_validation(log, repository, manifest, edge_records, panel_nodes)

    viewer_summary = check_viewer(log, packet, manifest)

    report = build_report(log, packet_relative, manifest, viewer_summary)
    report_json = write_json(output_directory / "verify_handoff_report.json", report)
    report_md = atomic_write_bytes(
        output_directory / "verify_handoff_report.md",
        render_markdown(report).encode("utf-8"),
    )
    checks_csv = write_csv(
        output_directory / "verify_handoff_checks.csv",
        [
            {
                "check_id": check["check_id"], "category": check["category"],
                "status": check["status"], "name": check["name"], "detail": check["detail"],
            }
            for check in report["checks"]
        ],
        ("check_id", "category", "status", "name", "detail"),
    )
    write_json(
        output_directory / "manifest.json",
        build_manifest([report_json, report_md, checks_csv], root=output_directory),
    )

    if not arguments.quiet:
        for result in log.results:
            print(f"  [{result.status:4}] {result.check_id:8} {result.name}"
                  + (f"  ->  {result.detail}" if result.detail else ""))
        print("-" * 72)
    totals = report["totals"]
    print(f"{totals['passed']}/{totals['total']} checks passed "
          f"({totals['failed']} FAIL, {totals['skipped']} SKIP) | findings: {len(log.findings)}")
    for category in sorted(report["by_category"]):
        bucket = report["by_category"][category]
        print(f"  {category:12} {bucket['passed']}/{bucket['total']} pass, "
              f"{bucket['failed']} fail, {bucket['skipped']} skip")
    print(f"artifacts -> {output_directory}")
    print("INTEGRITY " + report["integrity_gate"])
    return 1 if log.integrity_failed() else 0


if __name__ == "__main__":
    raise SystemExit(main())
