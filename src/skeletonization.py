import numpy as np
import os
from skimage.morphology import skeletonize

def skeletonize_mask(file_path, output_path):
    """
    Creates a skeleton from a 3D segmentation mask.
    
    Args:
        file_path (str): Path to the .npy file containing the 3D mask.
        output_path (str): Path to save the extracted skeleton (.npy).
    """
    if not os.path.exists(file_path):
        return None

    mask = np.load(file_path, allow_pickle=False)
    
    # Ensure the mask is boolean
    if mask.dtype != bool:
        # Assuming background is 0 and object is > 0
        mask = mask > 0

    skeleton = skeletonize(mask)
    np.save(output_path, skeleton, allow_pickle=False)
    
    return skeleton

if __name__ == "__main__":
    # Hardcoded parameters for testing
    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "unitcell", "unitcell.npy"))
    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "octet_truss_unit_cell_skeleton.npy"))
    
    # Create the data directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    skeletonize_mask(
        file_path=file_path, 
        output_path=output_path
    )
