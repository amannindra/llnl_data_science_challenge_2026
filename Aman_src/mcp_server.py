import contextlib
import io
import json
import os
import operator
import stat
import sys
import tempfile

import numpy as np
import tifffile
from fastmcp import FastMCP

# Task 3 is an API wrapper: expose the *existing* skeletonize_mask() from
# skeletonization.py rather than reimplementing it. Make sure this file's own
# directory is importable so the import works both when the server is run as a
# script (python Aman_src/mcp_server.py) and when it is loaded by absolute path.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
from skeletonization import skeletonize_mask

_REPOSITORY_DIR = os.path.dirname(_SRC_DIR)
if _REPOSITORY_DIR not in sys.path:
    sys.path.insert(0, _REPOSITORY_DIR)
from Aman_Scripts.Components.asset_io import (
    inspect_npy,
    inspect_tiff,
    load_json,
    load_npy,
)
from Aman_Scripts.Components.coordinates import zyx_to_xyz
from Aman_Scripts.Components.lattice_graph import load_lattice_graph, weld_coincident_nodes
from Aman_Scripts.Components.reporting import file_sha256, write_json

# Initialize the MCP server
mcp = FastMCP("CT Segmentation")


def _json_pointer_value(document, pointer: str):
    """Resolve a small RFC 6901 JSON Pointer without mutating the document."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("'json_pointer' must be empty or start with '/'")

    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(f"object key {token!r} does not exist")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit():
                raise ValueError(f"list token {token!r} is not a nonnegative index")
            index = int(token)
            if index >= len(current):
                raise IndexError(f"list index {index} outside [0, {len(current)})")
            current = current[index]
        else:
            raise TypeError(
                f"cannot descend through {type(current).__name__} with token {token!r}"
            )
    return current


@mcp.tool()
def read_json(
    input_filepath: str,
    json_pointer: str = "",
    max_characters: int = 20_000,
) -> str:
    """Read a JSON file or one value selected with an RFC 6901 JSON Pointer.

    Large values are returned as a bounded preview so an MCP response cannot
    accidentally flood the client's context. Use ``json_pointer`` (for example,
    ``/records/0``) to retrieve a smaller nested value.

    Args:
        input_filepath: Path to an input ``.json`` file.
        json_pointer: Optional RFC 6901 pointer to a nested value. Empty selects
            the entire document.
        max_characters: Maximum serialized characters to return, from 1 to
            1,000,000. Defaults to 20,000.

    Returns:
        The selected value as formatted JSON plus source metadata, or an error string.
    """
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not isinstance(json_pointer, str):
        return f"Error: 'json_pointer' must be a string, got {json_pointer!r}."
    if isinstance(max_characters, bool):
        return f"Error: 'max_characters' must be an integer, got {max_characters!r}."
    try:
        max_characters = operator.index(max_characters)
    except TypeError:
        return f"Error: 'max_characters' must be an integer, got {max_characters!r}."
    if not 1 <= max_characters <= 1_000_000:
        return ("Error: 'max_characters' must be between 1 and 1000000, "
                f"got {max_characters}.")
    if os.path.splitext(input_filepath)[1].lower() != ".json":
        return f"Error: 'input_filepath' must end with .json, got {input_filepath!r}."

    try:
        document = load_json(input_filepath)
        selected = _json_pointer_value(document, json_pointer)
        rendered = json.dumps(
            selected,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
    except Exception as e:  # noqa: BLE001 - surface filesystem/JSON/pointer errors to MCP
        return f"Error: Failed to read JSON '{input_filepath}': {e}"

    truncated = len(rendered) > max_characters
    returned = rendered[:max_characters] if truncated else rendered
    pointer_label = json_pointer or "<root>"
    header = (
        f"Read JSON from {os.path.abspath(os.path.expanduser(input_filepath))} "
        f"(pointer={pointer_label!r}, type={type(selected).__name__}, "
        f"characters={len(rendered)}, truncated={str(truncated).lower()})."
    )
    if truncated:
        header += " Select a narrower json_pointer or increase max_characters for more."
    return f"{header}\n{returned}"


@mcp.tool()
def read_npy(input_filepath: str) -> str:
    """Inspect a NumPy ``.npy`` array with bounded-memory summary statistics.

    The array is opened read-only with memory mapping. Numeric values are scanned
    in chunks, so large CT volumes are never copied into memory as one array.

    Args:
        input_filepath: Path to an input ``.npy`` file.

    Returns:
        Shape, dtype, size, value statistics, a short preview, and SHA-256, or an
        error string. Three-dimensional project volumes use ZYX array order.
    """
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if os.path.splitext(input_filepath)[1].lower() != ".npy":
        return f"Error: 'input_filepath' must end with .npy, got {input_filepath!r}."

    try:
        metadata = inspect_npy(input_filepath)
        array = load_npy(input_filepath, mmap_mode="r", allow_pickle=False)
    except Exception as e:  # noqa: BLE001 - surface filesystem/LFS/NumPy errors to MCP
        return f"Error: Failed to read NumPy array '{input_filepath}': {e}"

    is_bool = np.issubdtype(metadata.dtype, np.bool_)
    if not is_bool and not np.issubdtype(metadata.dtype, np.number):
        return (f"Error: Expected a numeric or boolean NumPy array, but "
                f"'{input_filepath}' has dtype {metadata.dtype}.")

    flattened = np.ravel(array, order="K")
    finite_count = 0
    nonzero_count = 0
    statistic_sum = 0.0
    statistic_min = np.inf
    statistic_max = -np.inf
    use_magnitude = np.issubdtype(metadata.dtype, np.complexfloating)
    chunk_elements = 1_000_000
    try:
        for begin in range(0, int(flattened.size), chunk_elements):
            chunk = np.asarray(flattened[begin:begin + chunk_elements])
            nonzero_count += int(np.count_nonzero(chunk))
            finite_mask = np.isfinite(chunk)
            if not np.any(finite_mask):
                continue
            values = chunk[finite_mask]
            if use_magnitude:
                values = np.abs(values)
            finite_count += int(values.size)
            statistic_sum += float(np.sum(values, dtype=np.float64))
            statistic_min = min(statistic_min, float(np.min(values)))
            statistic_max = max(statistic_max, float(np.max(values)))
        preview_values = np.asarray(flattened[:16]).tolist()
        digest = file_sha256(metadata.path)
    except Exception as e:  # noqa: BLE001 - make scan/hash failures visible to MCP clients
        return f"Error: Failed to summarize NumPy array '{input_filepath}': {e}"

    if finite_count:
        statistic_mean = statistic_sum / finite_count
        statistic_text = (
            f"min={statistic_min:.12g}, max={statistic_max:.12g}, "
            f"mean={statistic_mean:.12g}"
        )
    else:
        statistic_text = "min=n/a, max=n/a, mean=n/a"
    statistic_prefix = "magnitude_" if use_magnitude else ""
    axis_text = ", axis_order=ZYX" if len(metadata.shape) == 3 else ""
    return (
        f"Read NumPy array {metadata.path} "
        f"(shape={metadata.shape}, dtype={metadata.dtype}, elements={array.size}, "
        f"logical_bytes={metadata.nbytes}{axis_text}, finite={finite_count}/{array.size}, "
        f"nonzero={nonzero_count}, {statistic_prefix}{statistic_text}, "
        f"preview={preview_values!r}, sha256={digest})."
    )


def _otsu_from_histogram(counts: np.ndarray, levels: np.ndarray) -> float:
    """Return the lowest maximizing Otsu level for a histogram."""
    counts = np.asarray(counts, dtype=np.float64)
    levels = np.asarray(levels, dtype=np.float64)
    if counts.ndim != 1 or levels.ndim != 1 or counts.size != levels.size:
        raise ValueError("Otsu histogram counts and levels must be matching 1D arrays")
    if counts.size < 2 or not np.isfinite(counts).all() or np.any(counts < 0):
        raise ValueError("Otsu histogram counts must be finite and nonnegative")
    populated = np.flatnonzero(counts > 0)
    if populated.size < 2:
        raise ValueError("Otsu threshold requires at least two populated intensity bins")
    total = float(counts.sum())
    cumulative = np.cumsum(counts)
    weighted = np.cumsum(counts * levels)
    high_weight = total - cumulative
    valid = (cumulative > 0) & (high_weight > 0)
    between = np.full(counts.size, -np.inf, dtype=np.float64)
    low_mean = np.zeros(counts.size, dtype=np.float64)
    high_mean = np.zeros(counts.size, dtype=np.float64)
    low_mean[valid] = weighted[valid] / cumulative[valid]
    high_mean[valid] = (weighted[-1] - weighted[valid]) / high_weight[valid]
    between[valid] = cumulative[valid] * high_weight[valid] * (
        low_mean[valid] - high_mean[valid]
    ) ** 2
    return float(levels[int(np.argmax(between))])


def _tiff_otsu_threshold(path: str, series_index: int, metadata) -> float:
    """Build a bounded-memory global histogram and return its Otsu threshold."""
    minimum = np.inf
    maximum = -np.inf
    with tifffile.TiffFile(metadata.path) as tif:
        series = tif.series[series_index]
        for page in series.pages:
            image = np.asarray(page.asarray())
            finite = image[np.isfinite(image)]
            if finite.size:
                minimum = min(minimum, float(np.min(finite)))
                maximum = max(maximum, float(np.max(finite)))
    if not np.isfinite(minimum) or not np.isfinite(maximum) or minimum == maximum:
        raise ValueError("Otsu threshold requires at least two finite intensity values")

    is_integer = metadata.dtype.kind in "iu"
    exact_integer = is_integer and (maximum - minimum + 1 <= 1_000_000)
    if exact_integer:
        lower = int(minimum)
        upper = int(maximum)
        levels = np.arange(lower, upper + 1, dtype=np.float64)
        counts = np.zeros(levels.size, dtype=np.uint64)
        with tifffile.TiffFile(metadata.path) as tif:
            for page in tif.series[series_index].pages:
                image = np.asarray(page.asarray())
                finite = image[np.isfinite(image)]
                if finite.size:
                    shifted = finite.astype(np.int64, copy=False) - lower
                    counts += np.bincount(shifted, minlength=counts.size).astype(np.uint64)
        return _otsu_from_histogram(counts, levels)

    bins = 4096
    levels = np.linspace(minimum, maximum, bins, dtype=np.float64)
    counts = np.zeros(bins, dtype=np.uint64)
    with tifffile.TiffFile(metadata.path) as tif:
        for page in tif.series[series_index].pages:
            image = np.asarray(page.asarray())
            finite = image[np.isfinite(image)]
            if finite.size:
                histogram, _ = np.histogram(finite, bins=bins, range=(minimum, maximum))
                counts += histogram.astype(np.uint64, copy=False)
    return _otsu_from_histogram(counts, levels)


@mcp.tool()
def segment_tiff_otsu(
    input_filepath: str,
    output_filepath: str,
    series_index: int = 0,
) -> str:
    """Segment a 3D ZYX TIFF using a global Otsu threshold.

    The threshold is computed from all finite voxel intensities. Foreground is
    defined as ``intensity > threshold`` (the standard Otsu mask convention) and written as a streamed `uint8` TIFF
    mask with values `{0, 255}`. The destination is atomically replaced only
    after the complete mask has been written.

    Args:
        input_filepath: Input `.tif` or `.tiff` CT volume.
        output_filepath: Output `.tif` or `.tiff` mask path. `.tif` is appended
            when no extension is supplied.
        series_index: Zero-based TIFF series index, defaulting to 0.

    Returns:
        A status string containing the Otsu threshold and mask statistics, or an
        `Error:` string for invalid or unreadable inputs.
    """
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."
    if isinstance(series_index, bool):
        return f"Error: 'series_index' must be an integer, got {series_index!r}."
    try:
        series_index = operator.index(series_index)
    except TypeError:
        return f"Error: 'series_index' must be an integer, got {series_index!r}."
    if series_index < 0:
        return f"Error: 'series_index' must be nonnegative, got {series_index}."
    if os.path.splitext(input_filepath)[1].lower() not in {".tif", ".tiff"}:
        return f"Error: 'input_filepath' must end with .tif or .tiff, got {input_filepath!r}."

    try:
        metadata = inspect_tiff(input_filepath, series_index=series_index)
        if metadata.axes != "ZYX" or len(metadata.shape) != 3:
            return ("Error: segment_tiff_otsu requires a 3D ZYX TIFF series, "
                    f"received axes={metadata.axes!r}, shape={metadata.shape}.")
        if metadata.dtype.kind not in "uibf":
            return f"Error: TIFF dtype must be real numeric, received {metadata.dtype}."
        threshold = _tiff_otsu_threshold(input_filepath, series_index, metadata)
    except Exception as e:  # noqa: BLE001 - return failures through MCP
        return f"Error: Failed to compute Otsu threshold for '{input_filepath}': {e}"

    saved_path = output_filepath
    if os.path.splitext(saved_path)[1].lower() not in {".tif", ".tiff"}:
        saved_path += ".tif"
    saved_path = os.path.abspath(os.path.expanduser(saved_path))
    out_dir = os.path.dirname(saved_path)
    temporary_path = None
    mask = None
    foreground = 0
    total = int(np.prod(metadata.shape, dtype=np.int64))
    try:
        os.makedirs(out_dir, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            dir=out_dir,
            prefix=f".{os.path.basename(saved_path)}.",
            suffix=".tmp.tif",
        )
        os.close(descriptor)
        # tifffile.memmap creates a contiguous TIFF destination, allowing page
        # writes without allocating the complete mask in process memory.
        mask = tifffile.memmap(
            temporary_path,
            shape=metadata.shape,
            dtype=np.uint8,
            mode="w+",
            imagej=True,
            metadata={"axes": "ZYX"},
        )
        with tifffile.TiffFile(metadata.path) as tif:
            for z_index, page in enumerate(tif.series[series_index].pages):
                image = np.asarray(page.asarray())
                page_mask = np.asarray(image > threshold, dtype=np.uint8) * 255
                mask[z_index] = page_mask
                foreground += int(np.count_nonzero(page_mask))
        mask.flush()
        del mask
        mask = None
        os.replace(temporary_path, saved_path)
        temporary_path = None
    except Exception as e:  # noqa: BLE001 - clean up incomplete masks and return text
        return f"Error: Failed to write Otsu mask '{saved_path}': {e}"
    finally:
        if mask is not None:
            del mask
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)

    try:
        digest = file_sha256(saved_path)
    except Exception as e:  # noqa: BLE001
        return f"Error: Otsu mask was saved but verification failed: {e}"
    fraction = foreground / total if total else 0.0
    return (
        f"Saved Otsu TIFF mask to {saved_path} "
        f"(threshold={threshold:.12g}, shape={metadata.shape}, dtype=uint8, "
        f"foreground={foreground}/{total} voxels, {fraction:.2%}, sha256={digest})."
    )


@mcp.tool()
def skeleton_to_json(
    input_filepath: str,
    output_filepath: str,
    max_voxels: int = 2_000_000,
) -> str:
    """Convert a 3D skeleton NumPy array into a traceable JSON voxel list.

    The input array uses NumPy's ZYX order. Every finite, nonzero skeleton voxel
    is emitted as an XYZ coordinate, matching this project's JSON and mesh
    convention. The JSON is atomically written with source and output checksums.

    Args:
        input_filepath: Path to a 3D skeleton ``.npy`` file.
        output_filepath: Destination JSON path. ``.json`` is appended if absent.
        max_voxels: Safety limit for exported skeleton voxels, default 2,000,000.

    Returns:
        A status string with output details, or an ``Error:`` string.
    """
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."
    if os.path.splitext(input_filepath)[1].lower() != ".npy":
        return f"Error: 'input_filepath' must end with .npy, got {input_filepath!r}."
    if isinstance(max_voxels, bool):
        return f"Error: 'max_voxels' must be a positive integer, got {max_voxels!r}."
    try:
        max_voxels = operator.index(max_voxels)
    except TypeError:
        return f"Error: 'max_voxels' must be a positive integer, got {max_voxels!r}."
    if max_voxels < 1:
        return f"Error: 'max_voxels' must be positive, got {max_voxels}."

    try:
        source = load_npy(input_filepath, mmap_mode="r", allow_pickle=False)
        if source.ndim != 3:
            return ("Error: skeleton_to_json requires a 3D skeleton array, "
                    f"received shape {tuple(int(size) for size in source.shape)}.")
        if not (np.issubdtype(source.dtype, np.number) or np.issubdtype(source.dtype, np.bool_)):
            return f"Error: skeleton array must be numeric or boolean, received {source.dtype}."
        if np.issubdtype(source.dtype, np.complexfloating):
            return f"Error: skeleton array must be real-valued, received {source.dtype}."
        foreground = np.asarray(source != 0)
        if np.issubdtype(source.dtype, np.inexact):
            foreground &= np.isfinite(source)
        voxel_count = int(np.count_nonzero(foreground))
        if voxel_count > max_voxels:
            return (f"Error: skeleton has {voxel_count} foreground voxels, exceeding "
                    f"max_voxels={max_voxels}. Increase max_voxels explicitly if intended.")
        coordinates_xyz = zyx_to_xyz(np.argwhere(foreground)).astype(np.int64, copy=False)
        source_sha256 = file_sha256(input_filepath)
    except Exception as e:  # noqa: BLE001 - surface NumPy/LFS/input errors to MCP clients
        return f"Error: Failed to read skeleton '{input_filepath}': {e}"

    saved_path = output_filepath
    if not saved_path.endswith(".json"):
        saved_path += ".json"
    try:
        written = write_json(
            saved_path,
            {
                "schema_version": "skeleton-voxels.v1",
                "source": {
                    "path": os.path.abspath(os.path.expanduser(input_filepath)),
                    "sha256": source_sha256,
                    "array_order": "zyx",
                    "shape_zyx": [int(size) for size in source.shape],
                    "dtype": str(source.dtype),
                },
                "coordinate_order": "xyz",
                "skeleton_voxel_count": voxel_count,
                "voxel_coordinates_xyz": coordinates_xyz.tolist(),
            },
            create_parents=True,
        )
        output_sha256 = file_sha256(written)
    except Exception as e:  # noqa: BLE001 - surface atomic write failures to MCP clients
        return f"Error: Failed to write skeleton JSON '{saved_path}': {e}"
    return (
        f"Saved skeleton JSON to {written} "
        f"(shape_zyx={tuple(int(size) for size in source.shape)}, "
        f"coordinate_order=xyz, skeleton_voxels={voxel_count}, sha256={output_sha256})."
    )


def _nonnegative_finite(value, name: str) -> float:
    """Validate one tolerance value without exposing exceptions through MCP."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite nonnegative number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite nonnegative number") from exc
    if not np.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return result


def _limited(values: list, maximum: int) -> dict:
    """Return deterministic details together with their total count."""
    return {"count": len(values), "truncated": len(values) > maximum, "values": values[:maximum]}


@mcp.tool()
def compare_octet_json(
    left_filepath: str,
    right_filepath: str,
    output_filepath: str,
    coordinate_tolerance: float = 1e-6,
    thickness_tolerance: float = 1e-9,
    weld_tolerance: float = 1e-6,
    max_details: int = 1_000,
) -> str:
    """Compare nodes and struts in two supported octet-lattice JSON files.

    Junction IDs and strut IDs are compared directly. Shared junction positions
    use the supplied XYZ tolerance; strut endpoints are compared as undirected
    pairs of source junction IDs. Each input is also position-welded to report
    its physical node and strut counts. No coordinate-frame registration is
    inferred, so use a registered pair when direct XYZ positions should match.

    Args:
        left_filepath: First octet-lattice JSON file.
        right_filepath: Second octet-lattice JSON file.
        output_filepath: JSON report destination; ``.json`` is appended if absent.
        coordinate_tolerance: Direct XYZ position-match tolerance.
        thickness_tolerance: Absolute thickness-match tolerance.
        weld_tolerance: XYZ tolerance used to weld duplicate physical junctions.
        max_details: Maximum detailed IDs/records retained for each difference type.

    Returns:
        A status string with comparison counts and report path, or an ``Error:`` string.
    """
    for name, value in (("left_filepath", left_filepath), ("right_filepath", right_filepath),
                        ("output_filepath", output_filepath)):
        if not isinstance(value, str) or not value:
            return f"Error: '{name}' must be a non-empty string."
    if (os.path.splitext(left_filepath)[1].lower() != ".json"
            or os.path.splitext(right_filepath)[1].lower() != ".json"):
        return "Error: both input files must end with .json."
    try:
        coordinate_tolerance = _nonnegative_finite(coordinate_tolerance, "coordinate_tolerance")
        thickness_tolerance = _nonnegative_finite(thickness_tolerance, "thickness_tolerance")
        weld_tolerance = _nonnegative_finite(weld_tolerance, "weld_tolerance")
        if isinstance(max_details, bool):
            raise ValueError("max_details must be a positive integer")
        max_details = operator.index(max_details)
        if max_details < 1:
            raise ValueError("max_details must be a positive integer")
    except (TypeError, ValueError) as e:
        return f"Error: Invalid comparison option: {e}"

    try:
        left = load_lattice_graph(left_filepath)
        right = load_lattice_graph(right_filepath)
        left_welded = weld_coincident_nodes(left, tolerance=weld_tolerance)
        right_welded = weld_coincident_nodes(right, tolerance=weld_tolerance)
    except Exception as e:  # noqa: BLE001 - include LFS, schema, and parse failures
        return f"Error: Failed to load octet-lattice JSON input: {e}"

    left_nodes, right_nodes = left.junction_by_id(), right.junction_by_id()
    left_node_ids, right_node_ids = set(left_nodes), set(right_nodes)
    shared_node_ids = sorted(left_node_ids & right_node_ids)
    node_position_mismatches = []
    for junction_id in shared_node_ids:
        left_position = np.asarray(left_nodes[junction_id].position, dtype=float)
        right_position = np.asarray(right_nodes[junction_id].position, dtype=float)
        distance = float(np.linalg.norm(left_position - right_position))
        if distance > coordinate_tolerance:
            node_position_mismatches.append({
                "junction_id": junction_id,
                "left_xyz": left_position.tolist(),
                "right_xyz": right_position.tolist(),
                "distance": distance,
            })

    left_struts, right_struts = left.strut_by_id(), right.strut_by_id()
    left_strut_ids, right_strut_ids = set(left_struts), set(right_struts)
    shared_strut_ids = sorted(left_strut_ids & right_strut_ids)
    endpoint_mismatches, thickness_mismatches, edge_index_mismatches = [], [], []
    for strut_id in shared_strut_ids:
        first, second = left_struts[strut_id], right_struts[strut_id]
        if first.endpoints != second.endpoints:
            endpoint_mismatches.append({
                "strut_id": strut_id,
                "left_junction_ids": list(first.endpoints),
                "right_junction_ids": list(second.endpoints),
            })
        if ((first.thickness is None) != (second.thickness is None)
                or (first.thickness is not None and second.thickness is not None
                    and abs(first.thickness - second.thickness) > thickness_tolerance)):
            thickness_mismatches.append({
                "strut_id": strut_id,
                "left_thickness": first.thickness,
                "right_thickness": second.thickness,
            })
        if first.unit_cell_edge_idx != second.unit_cell_edge_idx:
            edge_index_mismatches.append({
                "strut_id": strut_id,
                "left_unit_cell_edge_idx": first.unit_cell_edge_idx,
                "right_unit_cell_edge_idx": second.unit_cell_edge_idx,
            })

    left_only_nodes, right_only_nodes = sorted(left_node_ids - right_node_ids), sorted(right_node_ids - left_node_ids)
    left_only_struts, right_only_struts = sorted(left_strut_ids - right_strut_ids), sorted(right_strut_ids - left_strut_ids)
    direct_equal = not any((left_only_nodes, right_only_nodes, left_only_struts, right_only_struts,
                            node_position_mismatches, endpoint_mismatches,
                            thickness_mismatches, edge_index_mismatches))
    report = {
        "schema_version": "octet-lattice-json-comparison.v1",
        "comparison_basis": {
            "junction_identity": "source junction ID",
            "junction_position_order": "xyz",
            "strut_identity": "source strut ID",
            "strut_endpoints": "undirected source junction-ID pair",
            "registration_inferred": False,
        },
        "tolerances": {
            "coordinate_xyz": coordinate_tolerance,
            "thickness": thickness_tolerance,
            "weld_xyz": weld_tolerance,
        },
        "inputs": {
            "left": {"path": os.path.abspath(os.path.expanduser(left_filepath)), "sha256": file_sha256(left_filepath)},
            "right": {"path": os.path.abspath(os.path.expanduser(right_filepath)), "sha256": file_sha256(right_filepath)},
        },
        "direct_comparison_equal": direct_equal,
        "raw_records": {
            "left": {"junctions": len(left.junctions), "struts": len(left.struts), "unit_cells": len(left.unit_cells)},
            "right": {"junctions": len(right.junctions), "struts": len(right.struts), "unit_cells": len(right.unit_cells)},
        },
        "junctions": {
            "shared_id_count": len(shared_node_ids),
            "left_only_ids": _limited(left_only_nodes, max_details),
            "right_only_ids": _limited(right_only_nodes, max_details),
            "position_mismatches": _limited(node_position_mismatches, max_details),
        },
        "struts": {
            "shared_id_count": len(shared_strut_ids),
            "left_only_ids": _limited(left_only_struts, max_details),
            "right_only_ids": _limited(right_only_struts, max_details),
            "endpoint_mismatches": _limited(endpoint_mismatches, max_details),
            "thickness_mismatches": _limited(thickness_mismatches, max_details),
            "unit_cell_edge_idx_mismatches": _limited(edge_index_mismatches, max_details),
        },
        "welded_physical_topology": {
            "left": {
                "nodes": len(left_welded.nodes), "struts": len(left_welded.struts),
                "dangling_source_strut_ids": list(left_welded.dangling_strut_ids),
                "self_loop_source_strut_ids": list(left_welded.self_loop_strut_ids),
            },
            "right": {
                "nodes": len(right_welded.nodes), "struts": len(right_welded.struts),
                "dangling_source_strut_ids": list(right_welded.dangling_strut_ids),
                "self_loop_source_strut_ids": list(right_welded.self_loop_strut_ids),
            },
        },
    }
    saved_path = output_filepath if output_filepath.endswith(".json") else f"{output_filepath}.json"
    try:
        written = write_json(saved_path, report, create_parents=True)
        digest = file_sha256(written)
    except Exception as e:  # noqa: BLE001
        return f"Error: Failed to write comparison report '{saved_path}': {e}"
    return (
        f"Saved octet JSON comparison to {written} "
        f"(direct_equal={str(direct_equal).lower()}, shared_junctions={len(shared_node_ids)}, "
        f"shared_struts={len(shared_strut_ids)}, left_welded_nodes={len(left_welded.nodes)}, "
        f"right_welded_nodes={len(right_welded.nodes)}, sha256={digest})."
    )


@mcp.tool()
def read_tiff(input_filepath: str, output_filepath: str, series_index: int = 0) -> str:
    """Read one TIFF series and save it as a NumPy array for downstream tools.

    The TIFF is decoded directly into a temporary disk-backed ``.npy`` array and
    atomically moved into place when complete. This avoids materializing a second
    copy of a large CT volume in memory. NumPy/TIFF array order is preserved
    exactly (the project's CT volumes are normally ZYX).

    Args:
        input_filepath: Path to an input ``.tif`` or ``.tiff`` file.
        output_filepath: Path for the output NumPy array. ``.npy`` is appended
            when it is missing.
        series_index: Zero-based TIFF series to read. Defaults to the first series.

    Returns:
        A status string with the saved path and TIFF metadata, or an error string.
    """
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."

    if isinstance(series_index, bool):
        return f"Error: 'series_index' must be an integer, got {series_index!r}."
    try:
        series_index = operator.index(series_index)
    except TypeError:
        return f"Error: 'series_index' must be an integer, got {series_index!r}."
    if series_index < 0:
        return f"Error: 'series_index' must be nonnegative, got {series_index}."

    extension = os.path.splitext(input_filepath)[1].lower()
    if extension not in {".tif", ".tiff"}:
        return ("Error: 'input_filepath' must end with .tif or .tiff, "
                f"got {input_filepath!r}.")

    try:
        metadata = inspect_tiff(input_filepath, series_index=series_index)
    except Exception as e:  # noqa: BLE001 - surface file/LFS/TIFF errors to MCP clients
        return f"Error: Failed to inspect TIFF '{input_filepath}': {e}"

    saved_path = output_filepath
    if not saved_path.endswith(".npy"):
        saved_path = saved_path + ".npy"
    saved_path = os.path.abspath(os.path.expanduser(saved_path))
    out_dir = os.path.dirname(saved_path)

    temporary_path = None
    destination = None
    decoded = None
    try:
        os.makedirs(out_dir, exist_ok=True)
        destination_mode = (
            stat.S_IMODE(os.stat(saved_path).st_mode)
            if os.path.isfile(saved_path)
            else 0o644
        )
        descriptor, temporary_path = tempfile.mkstemp(
            dir=out_dir,
            prefix=f".{os.path.basename(saved_path)}.",
            suffix=".tmp.npy",
        )
        os.close(descriptor)

        destination = np.lib.format.open_memmap(
            temporary_path,
            mode="w+",
            dtype=metadata.dtype,
            shape=metadata.shape,
        )
        with tifffile.TiffFile(metadata.path) as tif:
            decoded = tif.asarray(series=series_index, out=destination)
        if decoded.shape != metadata.shape or decoded.dtype != metadata.dtype:
            raise ValueError(
                "decoded TIFF metadata changed while reading: "
                f"expected shape={metadata.shape}, dtype={metadata.dtype}; "
                f"got shape={decoded.shape}, dtype={decoded.dtype}"
            )

        destination.flush()
        del decoded
        decoded = None
        del destination
        destination = None
        with open(temporary_path, "rb") as handle:
            os.fsync(handle.fileno())
        os.chmod(temporary_path, destination_mode)
        os.replace(temporary_path, saved_path)
        temporary_path = None
    except Exception as e:  # noqa: BLE001 - return a useful MCP error without partial output
        return f"Error: Failed to read TIFF '{input_filepath}': {e}"
    finally:
        if decoded is not None:
            del decoded
        if destination is not None:
            del destination
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)

    try:
        digest = file_sha256(saved_path)
        saved_bytes = os.path.getsize(saved_path)
    except Exception as e:  # noqa: BLE001 - the conversion succeeded but provenance did not
        return f"Error: Saved '{saved_path}' but failed to verify it: {e}"

    return (
        f"Saved TIFF series to {saved_path} "
        f"(series_index={series_index}, shape={metadata.shape}, axes={metadata.axes}, "
        f"dtype={metadata.dtype}, pages={metadata.page_count}, bytes={saved_bytes}, "
        f"sha256={digest})."
    )

@mcp.tool()
def segment_ct_dataset(input_filepath: str, output_filepath: str, threshold: float) -> str:
    """
    Segments a 3D CT dataset based on a given density threshold value.

    Args:
        input_filepath: Path to the input .npy file containing the 3D CT scan data.
        output_filepath: Path indicating where the segmented .npy file should be saved.
        threshold: The density value to use as a threshold. Voxels >= threshold will be set to 1, others to 0.

    Returns:
        A status message indicating success and the save location, or an error message.
    """
    # --- Validate the input path ---
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not os.path.exists(input_filepath):
        return f"Error: Input file not found at '{input_filepath}'."

    # --- Validate the threshold ---
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return f"Error: 'threshold' must be a number, got {threshold!r}."
    if not np.isfinite(threshold):
        return f"Error: 'threshold' must be finite, got {threshold!r}."

    # --- Load the volume ---
    try:
        data = np.load(input_filepath, allow_pickle=False)
    except Exception as e:  # noqa: BLE001 - report any load failure to the agent
        return f"Error: Failed to load '{input_filepath}': {e}"

    if not np.issubdtype(data.dtype, np.number):
        return (f"Error: Expected a numeric array, but '{input_filepath}' has "
                f"dtype {data.dtype}.")

    # --- Segment: voxels >= threshold -> 1, everything else (incl. NaN) -> 0 ---
    # `>=` matches the documented convention exactly; the result is a fresh
    # array, so the input `data` is never mutated. uint8 stores literal 0/1.
    mask = (data >= threshold).astype(np.uint8)

    # --- Resolve the actual save path (np.save appends .npy if missing) ---
    saved_path = output_filepath
    if not saved_path.endswith(".npy"):
        saved_path = saved_path + ".npy"

    # --- Make sure the destination directory exists, then save ---
    out_dir = os.path.dirname(os.path.abspath(saved_path))
    try:
        os.makedirs(out_dir, exist_ok=True)
        np.save(saved_path, mask)
    except Exception as e:  # noqa: BLE001 - report any save failure to the agent
        return f"Error: Failed to save segmentation to '{saved_path}': {e}"

    fg = int(mask.sum())
    total = int(mask.size)
    pct = (100.0 * fg / total) if total else 0.0
    return (f"Saved segmentation to {saved_path} "
            f"(shape={tuple(int(s) for s in mask.shape)}, dtype=uint8, "
            f"threshold={threshold}, foreground={fg}/{total} voxels, {pct:.2f}%).")

@mcp.tool()
def visualize_slice(input_filepath: str, output_filepath: str, slice_index: int, axis: int = 0) -> str:
    """
    Loads a 3D CT dataset from a .npy file and saves a visualization of a specific slice to an image file.
    
    Args:
        input_filepath: Path to the input .npy file containing the 3D CT data.
        output_filepath: Path indicating where the output image should be saved (e.g., .png).
        slice_index: The index of the slice to visualize.
        axis: The axis along which to take the slice (0, 1, or 2). Default is 0.

    Returns:
        A status message indicating success and the save location, or an error message.
    """
    # --- Validate the input path ---
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not os.path.exists(input_filepath):
        return f"Error: Input file not found at '{input_filepath}'."

    # --- Validate the output path ---
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."

    # --- Validate axis (must be 0, 1, or 2 per the documented convention) ---
    try:
        axis = int(axis)
    except (TypeError, ValueError):
        return f"Error: 'axis' must be an integer (0, 1, or 2), got {axis!r}."
    if axis not in (0, 1, 2):
        return f"Error: 'axis' must be 0, 1, or 2, got {axis}."

    # --- Validate slice_index (accept ints and int-valued strings/floats) ---
    try:
        slice_index = int(slice_index)
    except (TypeError, ValueError):
        return f"Error: 'slice_index' must be an integer, got {slice_index!r}."

    # --- Load the volume ---
    try:
        data = np.load(input_filepath, allow_pickle=False)
    except Exception as e:  # noqa: BLE001 - report any load failure to the agent
        return f"Error: Failed to load '{input_filepath}': {e}"

    if not np.issubdtype(data.dtype, np.number):
        return (f"Error: Expected a numeric array, but '{input_filepath}' has "
                f"dtype {data.dtype}.")
    if data.ndim != 3:
        return (f"Error: Expected a 3D CT volume, but '{input_filepath}' has "
                f"{data.ndim} dimension(s) with shape {tuple(int(s) for s in data.shape)}.")

    # --- Bounds-check the slice index (numpy-style negative indexing allowed) ---
    n = data.shape[axis]
    if slice_index < -n or slice_index >= n:
        return (f"Error: slice_index {slice_index} is out of range for axis {axis} "
                f"with {n} slices (valid range: {-n}..{n - 1}).")

    # --- Extract the 2D slice along the requested axis ---
    slice_2d = np.take(data, slice_index, axis=axis)

    # --- Resolve the actual save path (default to .png if no extension given) ---
    saved_path = output_filepath
    if not os.path.splitext(saved_path)[1]:
        saved_path = saved_path + ".png"

    # --- Choose a stable grayscale scaling from the finite values only ---
    finite = slice_2d[np.isfinite(slice_2d)]
    if finite.size:
        vmin = float(finite.min())
        vmax = float(finite.max())
    else:
        vmin, vmax = 0.0, 1.0
    if vmax <= vmin:  # constant (or all-NaN) slice: avoid a zero-width range
        vmax = vmin + 1.0

    # --- Map to an 8-bit grayscale image (min->black, max->white) ---
    # clip() sends +inf->white and -inf->black; nan_to_num() sends NaN->black.
    scaled = (np.asarray(slice_2d, dtype=float) - vmin) / (vmax - vmin)
    scaled = np.nan_to_num(np.clip(scaled, 0.0, 1.0), nan=0.0)
    gray8 = np.rint(scaled * 255.0).astype(np.uint8)

    # --- Make sure the destination directory exists, then save via Pillow ---
    # Pillow infers the format from the filename, so every extension (.png,
    # .tif, .jpg, .bmp, ...) works, unlike matplotlib's extension->format map.
    out_dir = os.path.dirname(os.path.abspath(saved_path))
    try:
        from PIL import Image
        os.makedirs(out_dir, exist_ok=True)
        Image.fromarray(gray8, mode="L").save(saved_path)
    except Exception as e:  # noqa: BLE001 - report any render/save failure to the agent
        return f"Error: Failed to save visualization to '{saved_path}': {e}"

    h, w = int(slice_2d.shape[0]), int(slice_2d.shape[1])
    return (f"Saved slice visualization to {saved_path} "
            f"(slice_index={slice_index}, axis={axis}, image_size={w}x{h}, "
            f"source_shape={tuple(int(s) for s in data.shape)}, "
            f"source_dtype={data.dtype}).")

@mcp.tool()
def skeletonize(input_filepath: str, output_filepath: str) -> str:
    """
    Creates a skeleton from a 3D segmentation mask.
    
    Args:
        input_filepath: Path to the .npy file containing the 3D mask.
        output_filepath: Path to save the extracted skeleton (.npy).
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    # --- Validate paths (skeletonize_mask only *prints* on a missing file and
    #     returns None, which an agent would never see — surface it as text). ---
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not os.path.isfile(input_filepath):
        return f"Error: Input file not found at '{input_filepath}'."
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."

    # --- Resolve the real save path. np.save appends ".npy" UNLESS the path
    #     already ends in ".npy" (so "x" and "x.dat" both become "*.npy"); match
    #     that exact rule so the reported path is the file that lands on disk. ---
    saved_path = output_filepath
    if not saved_path.endswith(".npy"):
        saved_path = saved_path + ".npy"

    # --- Ensure the destination dir exists (skeletonize_mask does not make it). ---
    out_dir = os.path.dirname(os.path.abspath(saved_path))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        return f"Error: Cannot create output directory '{out_dir}': {e}"

    # --- Call the existing API. Its many print() calls would corrupt the MCP
    #     stdio JSON-RPC stream, so capture stdout for the duration. ---
    chatter = io.StringIO()
    try:
        with contextlib.redirect_stdout(chatter):
            skeleton = skeletonize_mask(input_filepath, saved_path)
    except Exception as e:  # noqa: BLE001 - report any failure to the agent as text
        return f"Error: skeletonize_mask failed on '{input_filepath}': {e}"

    # --- skeletonize_mask returns None only when it refused to run. ---
    if skeleton is None:
        tail = chatter.getvalue().strip().splitlines()
        why = tail[-1] if tail else "no skeleton produced"
        return f"Error: skeletonization produced no output ({why})."

    skel = np.asarray(skeleton)
    nz = int(np.count_nonzero(skel))
    return (f"Saved skeleton to {saved_path} "
            f"(shape={tuple(int(s) for s in skel.shape)}, dtype={skel.dtype}, "
            f"skeleton_voxels={nz}).")

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()
