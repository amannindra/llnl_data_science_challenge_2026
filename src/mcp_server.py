from fastmcp import FastMCP
from pathlib import Path

import numpy as np

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
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError):
        return f"Error: threshold must be numeric, got {threshold!r}"

    if not np.isfinite(threshold_value):
        return f"Error: threshold must be finite, got {threshold!r}"

    input_path = Path(input_filepath).expanduser()
    output_path = Path(output_filepath).expanduser()

    if not input_path.exists():
        return f"Error: input file not found: {input_path}"

    if input_path.suffix != ".npy":
        return f"Error: expected a .npy input file, got: {input_path}"

    if output_path.suffix != ".npy":
        return f"Error: output file must end with .npy, got: {output_path}"

    try:
        data = np.load(input_path)
        mask = (data >= threshold_value).astype(np.uint8)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, mask)

        foreground_voxels = int(mask.sum())
        total_voxels = int(mask.size)
        foreground_fraction = foreground_voxels / total_voxels if total_voxels else 0.0

        return (
            f"Saved segmentation mask to {output_path}. "
            f"shape={mask.shape}, dtype={mask.dtype}, threshold={threshold_value}, "
            f"foreground_voxels={foreground_voxels}, total_voxels={total_voxels}, "
            f"foreground_fraction={foreground_fraction:.6f}"
        )
    except Exception as exc:
        return f"Error segmenting dataset: {type(exc).__name__}: {exc}"

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
    pass # Implementation goes here

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
