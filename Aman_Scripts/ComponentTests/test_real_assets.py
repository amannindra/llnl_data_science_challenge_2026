#!/usr/bin/env python3
"""Memory-conscious smoke checks against the restored project assets."""

from __future__ import annotations

import os

import numpy as np
import psutil

from _harness import Checker
from Components.asset_io import inspect_stl, inspect_tiff, read_tiff_slice
from Components.lattice_graph import load_lattice_graph, summarize_components, weld_coincident_nodes
from Components.paths import data_path, find_repository_root


def main() -> int:
    check = Checker("real_assets", minimum_checks=10)
    root = find_repository_root(__file__)
    raw = data_path(
        "missing_struts", "tif_stacks",
        "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif", root=root,
    )
    duplicate_raw = data_path("9x9x9_octet_lattice", "9x9x9_octet_lattice.tif", root=root)
    segmented = data_path(
        "missing_struts", "tif_stacks", "Tilted_Brian_Tran_segmented.tiff", root=root,
    )
    registered_path = data_path(
        "missing_struts", "registered_jsons",
        "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json", root=root,
    )
    stl_path = data_path("missing_struts", "stls", "0.stl", root=root)

    process = psutil.Process(os.getpid())
    starting_rss = process.memory_info().rss
    raw_metadata = inspect_tiff(raw)
    segmented_metadata = inspect_tiff(segmented)
    check.check("raw TIFF payload is restored", raw.stat().st_size > 1_000_000_000)
    check.check("segmented TIFF payload is restored", segmented.stat().st_size > 500_000_000)
    check.equal("raw TIFF has expected ZYX shape", raw_metadata.shape, (761, 815, 837))
    check.equal("segmented TIFF has expected ZYX shape", segmented_metadata.shape, (761, 815, 837))
    check.equal("raw TIFF axes are explicit", raw_metadata.axes, "ZYX")
    check.equal("segmented TIFF axes are explicit", segmented_metadata.axes, "ZYX")
    check.equal("raw TIFF dtype is uint16", raw_metadata.dtype, np.dtype(np.uint16))
    check.equal("segmented TIFF dtype is uint8", segmented_metadata.dtype, np.dtype(np.uint8))
    check.equal("raw TIFF page count is correct", raw_metadata.page_count, 761)
    check.equal("segmented TIFF page count is correct", segmented_metadata.page_count, 761)
    check.check("raw TIFF is memory-mappable", raw_metadata.memory_mappable)
    check.check("segmented TIFF is memory-mappable", segmented_metadata.memory_mappable)

    raw_middle = read_tiff_slice(raw, 380)
    duplicate_middle = read_tiff_slice(duplicate_raw, 380)
    segmented_slices = np.stack([
        read_tiff_slice(segmented, 0),
        read_tiff_slice(segmented, 380),
        read_tiff_slice(segmented, 760),
    ])
    check.equal("raw single-page read has YX shape", raw_middle.shape, (815, 837))
    check.check("duplicate raw asset has identical middle page", np.array_equal(raw_middle, duplicate_middle))
    check.check("raw middle page has nonzero dynamic range", int(raw_middle.max()) > int(raw_middle.min()))
    check.equal("segmented sampled slices use only 0/255", set(np.unique(segmented_slices).tolist()), {0, 255})
    check.check("segmented sampled slices contain foreground and background",
                bool(np.any(segmented_slices == 255) and np.any(segmented_slices == 0)))

    registered = load_lattice_graph(registered_path)
    check.equal("registered graph junction-record count", len(registered.junctions), 10_206)
    check.equal("registered graph expected-strut count", len(registered.struts), 18_468)
    welded = weld_coincident_nodes(registered)
    check.equal("registered graph welds to physical-node count", len(welded.nodes), 3_430)
    check.equal("registered welded graph is one component",
                summarize_components(welded).component_count, 1)

    stl = inspect_stl(stl_path)
    check.equal("restored STL is binary", stl.encoding, "binary")
    check.check("restored STL contains a substantial triangle mesh", stl.triangles > 1_000_000)
    check.check("restored STL has finite XYZ bounds",
                stl.bounding_box_min is not None and stl.bounding_box_max is not None
                and np.isfinite(stl.bounding_box_min).all() and np.isfinite(stl.bounding_box_max).all())
    rss_growth = process.memory_info().rss - starting_rss
    check.check("real-asset smoke stays below 512 MiB RSS growth",
                rss_growth < 512 * 1024**2, f"growth={rss_growth / 1024**2:.1f} MiB")
    return check.done()


if __name__ == "__main__":
    raise SystemExit(main())
