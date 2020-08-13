import numpy as np
from src.dataset.patching.commons import array4d_crop, fix_crop_center_3d


def _select_random_start_in_tumor(segmentation_mask, patch_size):

    tumor_indices = np.nonzero(segmentation_mask)
    start_x = np.random.randint(0, len(tumor_indices[0]))
    start_y = np.random.randint(0, len(tumor_indices[1]))
    start_z = np.random.randint(0, len(tumor_indices[2]))
    center_coord = (tumor_indices[0][start_x], tumor_indices[1][start_y], tumor_indices[2][start_z])


    return fix_crop_center_3d(segmentation_mask, patch_size, center_coord)


def patching(volume: np.ndarray, labels: np.ndarray, patch_size: tuple, mask: np.ndarray):
    """
    Randomly chosen inside the tumor region
    """
    center = _select_random_start_in_tumor(labels, patch_size)
    volume_patch = array4d_crop(volume, patch_size, center)
    seg_patch = array4d_crop(labels[None], patch_size, center)[0, :, :, :]

    return volume_patch, seg_patch
