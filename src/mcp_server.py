from pathlib import Path

import matplotlib
import numpy as np
from fastmcp import FastMCP

try:
    from .skeletonization import skeletonize_mask
except ImportError:
    from skeletonization import skeletonize_mask

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
    input_path = Path(input_filepath).expanduser()
    output_path = Path(output_filepath).expanduser()

    if not input_path.is_file():
        return f"Error: Input file does not exist: {input_path}"

    if input_path.suffix.lower() != ".npy":
        return f"Error: Input file must be a .npy file: {input_path}"

    if output_path.suffix.lower() != ".npy":
        return f"Error: Output file must use the .npy extension: {output_path}"

    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError):
        return f"Error: Threshold must be a finite numeric value, got {threshold!r}"

    if not np.isfinite(threshold_value):
        return f"Error: Threshold must be a finite numeric value, got {threshold!r}"

    try:
        ct_data = np.load(input_path, allow_pickle=False)
    except Exception as exc:
        return f"Error: Could not load input dataset '{input_path}': {exc}"

    if not isinstance(ct_data, np.ndarray):
        return f"Error: Input file does not contain a NumPy array: {input_path}"

    if ct_data.ndim != 3:
        return (
            "Error: Input dataset must be three-dimensional; "
            f"received shape {ct_data.shape}"
        )

    segmented_mask = (ct_data >= threshold_value).astype(np.uint8)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, segmented_mask, allow_pickle=False)
    except Exception as exc:
        return f"Error: Could not save segmented dataset to '{output_path}': {exc}"

    return f"Successfully saved segmented dataset to {output_path.resolve()}"

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
    input_path = Path(input_filepath).expanduser()
    output_path = Path(output_filepath).expanduser()

    if not input_path.is_file():
        return f"Error: Input file does not exist: {input_path}"

    if input_path.suffix.lower() != ".npy":
        return f"Error: Input file must be a .npy file: {input_path}"

    if not isinstance(axis, (int, np.integer)) or isinstance(axis, bool):
        return f"Error: Axis must be an integer in {{0, 1, 2}}, got {axis!r}"

    if axis not in (0, 1, 2):
        return f"Error: Axis must be 0, 1, or 2, got {axis}"

    if not isinstance(slice_index, (int, np.integer)) or isinstance(slice_index, bool):
        return f"Error: Slice index must be an integer, got {slice_index!r}"

    try:
        ct_data = np.load(input_path, allow_pickle=False)
    except Exception as exc:
        return f"Error: Could not load input dataset '{input_path}': {exc}"

    if not isinstance(ct_data, np.ndarray):
        return f"Error: Input file does not contain a NumPy array: {input_path}"

    if ct_data.ndim != 3:
        return (
            "Error: Input dataset must be three-dimensional; "
            f"received shape {ct_data.shape}"
        )

    axis_size = ct_data.shape[axis]
    if not 0 <= slice_index < axis_size:
        return (
            f"Error: Slice index {slice_index} is out of range for axis {axis}; "
            f"valid indices are 0 through {axis_size - 1}"
        )

    requested_slice = np.take(ct_data, slice_index, axis=axis)

    figure = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure, axes = plt.subplots()
        axes.imshow(requested_slice, cmap="gray", interpolation="nearest")
        axes.set_title(f"Axis {axis}, slice {slice_index}")
        axes.set_axis_off()
        figure.savefig(output_path, bbox_inches="tight", pad_inches=0)
    except Exception as exc:
        return f"Error: Could not save slice image to '{output_path}': {exc}"
    finally:
        if figure is not None:
            plt.close(figure)

    return (
        f"Successfully saved slice image to {output_path.resolve()} "
        f"(axis={axis}, slice_index={slice_index})"
    )

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
    input_path = Path(input_filepath).expanduser()
    output_path = Path(output_filepath).expanduser()

    if not input_path.is_file():
        return f"Error: Input file does not exist: {input_path}"

    if input_path.suffix.lower() != ".npy":
        return f"Error: Input file must be a .npy file: {input_path}"

    if output_path.suffix.lower() != ".npy":
        return f"Error: Output file must use the .npy extension: {output_path}"

    try:
        mask = np.load(input_path, allow_pickle=False)
    except Exception as exc:
        return f"Error: Could not load input mask '{input_path}': {exc}"

    if not isinstance(mask, np.ndarray):
        return f"Error: Input file does not contain a NumPy array: {input_path}"

    if mask.ndim != 3:
        return (
            "Error: Input mask must be three-dimensional; "
            f"received shape {mask.shape}"
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        skeletonize_mask(str(input_path), str(output_path))
    except Exception as exc:
        return f"Error: Could not skeletonize input mask '{input_path}': {exc}"

    return f"Successfully saved skeleton to {output_path.resolve()}"

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()
