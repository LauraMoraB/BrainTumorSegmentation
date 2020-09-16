import csv
import sys
import os
import numpy as np
from src.config import BratsConfiguration
from src.dataset.utils import dataset, nifi_volume as nifi_utils
from src.dataset import brats_labels
from src.metrics import evaluation_metrics as eval
from tqdm import tqdm


def compute(volume_pred, volume_gt, roi_mask):

    tp, fp, tn, fn = eval.get_confusion_matrix(volume_pred, volume_gt, roi_mask)

    if len(np.unique(volume_pred)) == 1 and len(np.unique(volume_gt)) == 1 and np.unique(volume_pred)[0] == 0 and np.unique(volume_gt)[0] == 0:
        print("There is no tumor for this region")
        dc = 1.0
        hd = 0.0
    else:
        dc = eval.dice(tp, fp, fn)
        hd = eval.hausdorff(volume_pred, volume_gt)

    recall  = eval.recall(tp, fn)
    precision = eval.precision(tp, fp)
    acc = eval.accuracy(tp, fp, tn, fn)
    f1 = eval.fscore(tp, fp, tn ,fn)

    return dc, hd, recall, precision, acc, f1, (tp, fp, tn, fn)


def compute_wt_tc_et(prediction, reference, flair):

    metrics = []
    roi_mask = dataset.create_roi_mask(flair)

    for typee in ["wt", "tc", "et"]:

        if typee == "wt":
            volume_gt = brats_labels.get_wt(reference)
            volume_pred = brats_labels.get_wt(prediction)

        elif typee == "tc":
            volume_gt = brats_labels.get_tc(reference)
            volume_pred = brats_labels.get_tc(prediction)

        elif typee == "et":
            volume_gt = brats_labels.get_et(reference)
            volume_pred = brats_labels.get_et(prediction)
            if len(np.unique(volume_gt)) == 1 and np.unique(volume_gt)[0] == 0:
                print("there is no enchancing tumor region in the ground truth")
        else:
            continue

        dc, hd, recall, precision, acc, f1, conf_matrix = compute(volume_pred, volume_gt, roi_mask)
        metrics.extend([dc, hd, recall, precision, f1])

    return metrics


if __name__ == "__main__":
    config = BratsConfiguration(sys.argv[1])
    model_config = config.get_model_config()
    dataset_config = config.get_dataset_config()
    basic_config = config.get_basic_config()

    data_train, data_test = dataset.read_brats(dataset_config.get("train_csv"))
    data = data_test

    with open(f"results_test.csv", "w") as file:
        writer = csv.writer(file)
        writer.writerow(["subject_ID", "Grade", "Center", "Size",
                         "Dice WT", "HD WT", "Recall WT", "Precision WT", "F1 WT",
                         "Dice TC", "HD TC", "Recall TC", "Precision TC", "F1 TC",
                         "Dice ET", "HD ET", "Recall ET", "Precision ET", "F1 ET"
                         ])

        for patient in tqdm(data, total=len(data)):

            patient_data = []
            gt_path = os.path.join(patient.data_path, patient.patient, f"{patient.seg}")
            data_path = os.path.join(patient.data_path, patient.patient, f"{patient.flair}")
            prediction_path = os.path.join(patient.data_path, patient.patient, f"{patient.patient}_prediction.nii.gz")
            if not os.path.exists(prediction_path):
                print(f"{prediction_path} not found")
                continue

            patient_data.extend([patient.patient, patient.grade, patient.center, patient.size])

            volume_gt_all, _ = nifi_utils.load_nifi_volume(gt_path)
            volume_pred_all, _ = nifi_utils.load_nifi_volume(prediction_path)
            volume, _ = nifi_utils.load_nifi_volume(data_path)

            patient_data = compute_wt_tc_et(volume_pred_all, volume_gt_all, volume)
            writer.writerow(patient_data)


