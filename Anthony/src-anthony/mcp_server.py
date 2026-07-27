
from fastmcp import FastMCP
import numpy as np
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

try:
    from .skeletonization import skeletonize_mask
except ImportError:
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
    try:
        data = np.load(input_filepath)

        if data.ndim != 3:
            return (
                f"Error: expected a 3D dataset, "
                f"but received shape {data.shape}."
            )

        segmentation_mask = (data >= threshold).astype(np.uint8)
        np.save(output_filepath, segmentation_mask)

        return f"Segmentation saved successfully to {output_filepath}"

    except Exception as error:
        return f"Error segmenting CT dataset: {error}"

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
    try:
        data = np.load(input_filepath)

        if data.ndim != 3:
            return (
                f"Error: expected a 3D dataset, "
                f"but received shape {data.shape}."
            )

        if axis not in (0, 1, 2):
            return f"Error: axis must be 0, 1, or 2; received {axis}."

        if not 0 <= slice_index < data.shape[axis]:
            return (
                f"Error: slice_index must be between 0 and "
                f"{data.shape[axis] - 1} for axis {axis}; "
                f"received {slice_index}."
            )

        slice_data = np.take(data, slice_index, axis=axis)

        plt.figure(figsize=(8, 8))
        plt.imshow(slice_data, cmap="gray")
        plt.title(f"Slice {slice_index} along axis {axis}")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_filepath, dpi=150, bbox_inches="tight")
        plt.close()

        return f"Slice visualization saved successfully to {output_filepath}"

    except Exception as error:
        plt.close()
        return f"Error visualizing slice: {error}"

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
    try:
        skeleton = skeletonize_mask(input_filepath, output_filepath)

        if skeleton is None:
            return f"Error: could not skeletonize {input_filepath}."

        return f"Skeleton saved successfully to {output_filepath}"

    except Exception as error:
        return f"Error skeletonizing mask: {error}"

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()
