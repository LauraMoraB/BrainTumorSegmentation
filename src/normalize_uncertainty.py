import os
import numpy as np
from src.dataset.utils.nifi_volume import load_nifi_volume_return_nib, save_segmask_as_nifi_volume, load_nifi_volume
from src.uncertainty.uncertainty import brats_normalize
from tqdm import tqdm


if __name__ == "__main__":

    model_path = "/Users/lauramora/Documents/MASTER/TFM/Code/BrainTumorSegmentation/results/checkpoints/model_1594151267"
    ground_truth_path = "/Users/lauramora/Documents/MASTER/TFM/Data/2020/validation/no_patch"
    input_dir = os.path.join(model_path, "uncertainty_task")
    output_dir = os.path.join(model_path, "uncertainty_task_normalized")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    file_list = sorted([file for file in os.listdir(input_dir) if "unc" in file])
    file_list_all = sorted([file for file in os.listdir(input_dir)])

    max_uncertainty = 0
    min_uncertainty = 10000

    for uncertainty_map in tqdm(file_list, total=len(file_list), desc="Getting min and max"):

        # Load Uncertainty maps
        patient_name = uncertainty_map.split(".")[0].split("_unc")[0]
        path_gt =  os.path.join(ground_truth_path, patient_name, f"{patient_name}_flair.nii.gz")
        flair = load_nifi_volume(path_gt, normalize=False)
        brain_mask = np.zeros(flair.shape, np.float)
        brain_mask[flair > 0] = 1

        path = os.path.join(input_dir, uncertainty_map)
        unc_map, _ = load_nifi_volume_return_nib(path, normalize=False)

        tmp_max = np.max(unc_map[brain_mask==1])
        tmp_min = np.min(unc_map[brain_mask==1])

        if tmp_max > max_uncertainty:
            max_uncertainty = tmp_max

        if tmp_min < min_uncertainty:
            min_uncertainty = tmp_min


    for uncertainty_map_path in tqdm(file_list_all, total=len(file_list_all), desc="Normalizing.."):

        path = os.path.join(input_dir, uncertainty_map_path)
        output_path = os.path.join(output_dir, uncertainty_map_path)

        unc_map, nib_data = load_nifi_volume_return_nib(path, normalize=False)

        if "unc" in uncertainty_map_path:
            uncertainty_map_normalized = brats_normalize(unc_map, max_unc=max_uncertainty, min_unc=min_uncertainty)
            print(f"Saving to: {output_path}")
            save_segmask_as_nifi_volume(uncertainty_map_normalized,  nib_data.get_affine(), output_path)
        else:
            save_segmask_as_nifi_volume(unc_map, nib_data.get_affine(), output_path)