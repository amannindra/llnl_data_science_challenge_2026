import os

import matplotlib
import numpy as np
from fastmcp import FastMCP

# The MCP server runs without a desktop display. Configure Matplotlib before
# importing pyplot so visualizations can be generated in headless sessions.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
    if not os.path.isfile(input_filepath):
        return f"Error: Input file not found at '{input_filepath}'."

    # The MCP schema presents this as a string, but validating explicitly keeps
    # direct and programmatic calls from raising an uncaught AttributeError.
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."

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

    # ``np.load`` also accepts .npz archives and returns NpzFile instead of an
    # array. Task 1 is deliberately a single 3D .npy CT-volume operation.
    if not isinstance(data, np.ndarray):
        close = getattr(data, "close", None)
        if close is not None:
            close()
        return (f"Error: Expected a single NumPy array in '{input_filepath}', "
                f"but loaded {type(data).__name__}.")

    if not np.issubdtype(data.dtype, np.number):
        return (f"Error: Expected a numeric array, but '{input_filepath}' has "
                f"dtype {data.dtype}.")
    if data.ndim != 3:
        return (f"Error: Expected a 3D CT volume, but '{input_filepath}' has "
                f"shape {data.shape}.")

    # --- Segment: voxels >= threshold -> 1, everything else (incl. NaN) -> 0 ---
    # `>=` matches the documented convention exactly; the result is a fresh
    # array, so the input `data` is never mutated. uint8 stores literal 0/1.
    mask = (data >= threshold).astype(np.uint8)

    # --- Resolve the actual save path (np.save appends .npy if missing) ---
    saved_path = output_filepath
    if not saved_path.endswith(".npy"):
        saved_path = saved_path + ".npy"
    if os.path.abspath(saved_path) == os.path.abspath(input_filepath):
        return "Error: 'output_filepath' must differ from 'input_filepath' to preserve the raw CT data."

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
    # --- Validate paths and selection parameters ---
    if not isinstance(input_filepath, str) or not input_filepath:
        return "Error: 'input_filepath' must be a non-empty string."
    if not os.path.isfile(input_filepath):
        return f"Error: Input file not found at '{input_filepath}'."
    if not isinstance(output_filepath, str) or not output_filepath:
        return "Error: 'output_filepath' must be a non-empty string."
    if isinstance(axis, bool) or not isinstance(axis, (int, np.integer)):
        return f"Error: 'axis' must be an integer in {{0, 1, 2}}, got {axis!r}."
    if isinstance(slice_index, bool) or not isinstance(slice_index, (int, np.integer)):
        return f"Error: 'slice_index' must be an integer, got {slice_index!r}."
    axis = int(axis)
    slice_index = int(slice_index)
    if axis not in (0, 1, 2):
        return f"Error: 'axis' must be 0, 1, or 2, got {axis}."

    # --- Load and validate the CT volume ---
    try:
        data = np.load(input_filepath, allow_pickle=False)
    except Exception as e:  # noqa: BLE001 - report any load failure to the agent
        return f"Error: Failed to load '{input_filepath}': {e}"
    if not isinstance(data, np.ndarray):
        close = getattr(data, "close", None)
        if close is not None:
            close()
        return (f"Error: Expected a single NumPy array in '{input_filepath}', "
                f"but loaded {type(data).__name__}.")
    if not np.issubdtype(data.dtype, np.number) or np.issubdtype(data.dtype, np.complexfloating):
        return (f"Error: Expected a real numeric array, but '{input_filepath}' "
                f"has dtype {data.dtype}.")
    if data.ndim != 3:
        return (f"Error: Expected a 3D CT volume, but '{input_filepath}' has "
                f"shape {data.shape}.")
    if not 0 <= slice_index < data.shape[axis]:
        return (f"Error: 'slice_index' {slice_index} is out of bounds for axis {axis} "
                f"with size {data.shape[axis]}.")

    selected_slice = np.take(data, slice_index, axis=axis)
    finite = np.isfinite(data)
    if not finite.any():
        return f"Error: '{input_filepath}' contains no finite values to visualize."
    if not np.isfinite(selected_slice).any():
        return (f"Error: slice {slice_index} along axis {axis} contains no finite "
                "values to visualize.")
    vmin = float(data[finite].min())
    vmax = float(data[finite].max())

    # --- Resolve a PNG destination and render the selected 2D plane ---
    root, extension = os.path.splitext(output_filepath)
    if not extension:
        saved_path = output_filepath + ".png"
    elif extension.lower() == ".png":
        saved_path = output_filepath
    else:
        return ("Error: 'output_filepath' must have a .png extension (or no "
                f"extension), got '{output_filepath}'.")
    if os.path.abspath(saved_path) == os.path.abspath(input_filepath):
        return "Error: 'output_filepath' must differ from 'input_filepath' to preserve the raw CT data."

    try:
        os.makedirs(os.path.dirname(os.path.abspath(saved_path)), exist_ok=True)
        # A shared data range makes images comparable between slices of a
        # volume. Constructing the 8-bit RGBA array explicitly avoids implicit
        # colormap lookup-table rounding and writes only the image plane.
        safe_slice = np.where(np.isfinite(selected_slice), selected_slice, vmin)
        if vmax == vmin:
            normalized = np.zeros(selected_slice.shape, dtype=np.float32)
        else:
            normalized = np.clip((safe_slice - vmin) / (vmax - vmin), 0.0, 1.0)
        grayscale = np.rint(normalized * 255.0).astype(np.uint8)
        rgba = np.empty(selected_slice.shape + (4,), dtype=np.uint8)
        rgba[..., :3] = grayscale[..., np.newaxis]
        rgba[..., 3] = 255
        plt.imsave(saved_path, rgba)
    except Exception as e:  # noqa: BLE001 - return tool-friendly failure state
        return f"Error: Failed to save slice visualization to '{saved_path}': {e}"

    return (f"Saved slice visualization to {saved_path} "
            f"(volume_shape={tuple(int(s) for s in data.shape)}, axis={axis}, "
            f"slice_index={slice_index}, slice_shape={tuple(int(s) for s in selected_slice.shape)}, "
            f"display_range=[{vmin}, {vmax}]).")

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
    pass # Implementation goes here, calling skeletonize_mask internally

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()
