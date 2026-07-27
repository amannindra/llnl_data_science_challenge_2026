import contextlib
import io
import os
import sys

import numpy as np
from fastmcp import FastMCP

# Task 3 is an API wrapper: expose the *existing* skeletonize_mask() from
# skeletonization.py rather than reimplementing it. Make sure this file's own
# directory is importable so the import works both when the server is run as a
# script (python Aman_src/mcp_server.py) and when it is loaded by absolute path.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
from skeletonization import skeletonize_mask

# Initialize the MCP server
mcp = FastMCP("CT Segmentation")

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
