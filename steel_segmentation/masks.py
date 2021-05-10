# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/02_masks.ipynb (unless otherwise specified).

__all__ = ['get_random_idx', 'get_perm_imgs_path', 'rle2mask', 'make_mask', 'mask2rle', 'palet',
           'get_img_with_contours', 'plot_mask_image', 'plot_defected_image', 'show_defects', 'create_masks',
           'labels_path']

# Cell
from .metadata import *

from fastcore.foundation import *
from PIL import Image
from collections import defaultdict
from matplotlib import pyplot as plt
from fastcore.test import test_eq
from fastai.data.transforms import get_image_files
from fastai.vision.all import *

import pandas as pd
import numpy as np
from functools import partial
import cv2
from pathlib import Path

# Cell
def get_random_idx(n: int) -> np.ndarray:
    """
    Return a random sequence of size `n`.
    """
    rng = np.random.default_rng()
    return rng.permutation(n)

# Cell
def get_perm_imgs_path(train_pfiles: L, df: pd.DataFrame) -> L:
    """
    Return img Path list of selected df.
    """
    imgId_vals = df["ImageId"].drop_duplicates().values
    path_idx = train_pfiles.argwhere(lambda x: x.name in imgId_vals)
    sel_paths = train_pfiles[path_idx]
    idx = get_random_idx(len(sel_paths))
    return sel_paths[idx]

# Cell
def rle2mask(rle: str, value: int, shape):
    """
    From a RLE encoded pixels returns a mask
    with `value` for defected pixels
    (e.g. `value`=1 so 1 -> defected, 0 -> groundtruth)
    and `shape` as tuple (height, width).
    """
    assert len(shape) == 2, "The shape must be (height, width)"
    assert isinstance(shape[0], int)
    assert isinstance(shape[1], int)

    h, w = shape
    mask = np.zeros(h * w, dtype=np.uint8)

    rle = rle.split(" ")
    positions = map(int, rle[0::2])
    length = map(int, rle[1::2])

    for pos, le in zip(positions, length):
        mask[pos:(pos + le)] = value

    return mask.reshape(h, w, order='F')

# Cell
def make_mask(item, flatten=False, df=None):
    '''
    Given an item as:
    - row index [int] or
    - ImageId [str] or
    - file [Path] or
    - query [pd.Series],

    returns the image_item and mask with two types of shapes:
    - (256, 1600) if `flatten`,
    - (256, 1600, 4) if not `flatten`,

    from the dataframe `train_pivot` if not specified into `df`.
    '''
    if df is None: df = train_pivot
    if isinstance(item, str):         cond = df.loc[item]
    elif isinstance(item, int):       cond = df.iloc[item]
    elif isinstance(item, Path):      cond = df.loc[item.name]
    elif isinstance(item, pd.Series): cond = df.loc[item["ImageId"]]
    else:
        print(item, type(item))
        raise KeyError("invalid item")

    fname = cond.name
    # without 0 ClassId, only 1,2,3,4 ClassId
    labels = cond[1:-1]

    h, w = (256, 1600)
    masks = np.zeros((h, w, 4), dtype=np.float32) # 4:class 1～4 (ch:0～3)

    for itemx, label in enumerate(labels.values):
        if label is not np.nan:
            masks[:, :, itemx] = rle2mask(rle=label, value=1, shape=(h,w))

    if flatten:
        classes = np.array([1, 2, 3, 4])
        masks = (masks * classes).sum(-1)

    return fname, masks

# Cell
def mask2rle(mask):
    '''
    From https://www.kaggle.com/paulorzp/rle-functions-run-lenght-encode-decode

    Attributes: `mask`: numpy array with 1 -> mask, 0 -> background.

    Returns: run length as string formated
    '''
    pixels= mask.T.flatten()
    pixels = np.concatenate([pixels, [0]])
    runs = np.where(pixels[1:] != pixels[:-1])[0] + 1
    runs[1::2] -= runs[::2]
    return ' '.join(str(x) for x in runs)

# Cell
palet = [
        (249, 192, 12), # ClassId 1
        (0, 185, 241),  # ClassId 2
        (114, 0, 218),  # ClassId 3
        (249,50,12)     # ClassId 4
]

# Cell
def get_img_with_contours(img: np.array, mask: np.array):
    """Plot a np.array image and mask with contours."""
    mask = mask.astype(np.uint8)
    for ch in range(4):
        contours, _ = cv2.findContours(mask[:, :, ch], cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for i in range(len(contours)):
            cv2.polylines(img, contours[i], True, palet[ch], 2)
    return img

# Cell
def plot_mask_image(name: str, img: np.array, mask: np.array):
    """Plot a np.array image and mask with contours."""
    fig, ax = plt.subplots(figsize=(15, 5))

    img = get_img_with_contours(img, mask)

    ax.set_title(name, fontsize=13)
    ax.imshow(img)
    plt.xticks([])
    plt.yticks([])
    plt.show()

# Cell
def plot_defected_image(img_path: Path, class_id=None, df=None):
    """Plot a `img_path` Path image from the training folder with contours."""
    img_name = img_path.name
    img = cv2.imread(str(img_path))
    _, mask = make_mask(item=img_path, df=df)
    class_ids = np.arange(1, 5)
    cond = np.argmax(mask, axis=0).argmax(axis=0) > 0
    classid = class_ids[cond]
    if class_id is None:
        title = f"Original: Image {img_name} with defect type: {list(classid)}"
        plot_mask_image(title, img, mask)
    else:
        title = f"Original: Image {img_name} with defect type {class_id}"
        idx = class_id-1
        filter_mask = np.zeros((256, 1600, 4), dtype=np.float32)
        filter_mask[:, :, idx] = mask[:, :, idx]
        plot_mask_image(title, img, filter_mask)

# Cell
def show_defects(class_id=None, n=20, only_defects=True, multi_defects=False):
    """
    Plot multiple images.
    Attributes:
    `class_id`: [str or int] select a type of defect otherwise plot all kinds;
    `n`: select the number of images to plot;
    `only_defects` [bool, default True]: if False it shows even the no faulty images;
    `multi_defects` [bool, default False]: if True it shows imgs with multi defects.
    """
    df = train_multi

    cond_no_defects = df["ClassId_multi"] == '0'
    cond_multi_defects = df["ClassId_multi"].map(lambda x: len(x) > 1)
    cond_classId = df["ClassId_multi"].map(lambda x: str(class_id) in x)

    df = df.loc[cond_no_defects] if not only_defects else df.loc[~cond_no_defects]
    df = df.loc[cond_multi_defects] if multi_defects else df.loc[~cond_multi_defects]
    df = df.loc[cond_classId] if class_id else df

    imgid_from_df = df["ImageId"].tolist()
    pfiles_list = L([train_path / imgid for imgid in imgid_from_df])

    perm_paths = get_perm_imgs_path(pfiles_list, df)
    for img_path in perm_paths[:n]:
        plot_defected_image(img_path)

# Cell
labels_path = path / "labels"

def create_masks(df: pd.DataFrame):
    """Create the masks for ImageId in df"""
    paths = []
    for img_id in df["ImageId"].tolist():
        img_path = train_path / img_id
        img_label = labels_path/f"{img_path.stem}_P.png"
        if not img_label.is_file():
            _, mask = make_mask(img_path, flatten=True)
            im = Image.fromarray(mask)
            im.save(img_label)
        paths.append(img_label)
    return L(paths)