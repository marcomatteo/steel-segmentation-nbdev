# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_data.ipynb (unless otherwise specified).

__all__ = ['defeat_position', 'rle_to_mask', 'multi_rle_to_mask', 'img_with_mask', 'get_random_idx',
           'get_perm_imgs_path', 'plot_defected_image', 'show_defects']

# Cell
from .core import *
from fastcore.foundation import *
from PIL import Image
from collections import defaultdict
from matplotlib import pyplot as plt

import pandas as pd
import numpy as np

# Cell
def defeat_position(img_id:str, class_id:int, df:pd.DataFrame=train):
    """
    Get coordinates of defects `(x, y)` given an ImageId and a ClassId
    """
    # Select the image to mask
    # cond = df.ImageId_ClassId == f"{img_id}_{class_id}"
    cond = (df.ImageId == img_id) & (df.ClassId == class_id)
    train_s = df[cond]

    encoded_pixels = [int(i) for i in train_s.EncodedPixels.values[0].split(" ")]

    pixcels = []
    pos_pixels = encoded_pixels[0:len(encoded_pixels):2]
    offs_pixels = encoded_pixels[1:len(encoded_pixels):2]

    for pos, offset in zip(pos_pixels, offs_pixels):
        pixcels.extend(list(range(pos, pos+offset)))

    pixcels = np.array(pixcels)
    x = pixcels // 256
    y = pixcels % 256

    return x, y

# Cell
def rle_to_mask(rle:str, class_id:int, height:int, width:int) -> np.ndarray:
    """
    Convert RLE encoded pixels to numpy array for only one class_id
    """
    rows, cols = height, width
    mask = np.zeros(rows*cols, dtype=np.uint8)

    if rle == -1:
        return mask.reshape(cols, rows).T

    encoded_pixels = [int(i) for i in rle.split(" ")]

    rle_pairs = np.array(encoded_pixels).reshape(-1, 2) # (n, 2) as [[pos, offs], ... ]

    for index, length in rle_pairs:
        index -= 1
        mask[index : (index + length)] = class_id

    mask = mask.reshape(cols, rows)
    return mask.T

# Cell
def multi_rle_to_mask(img_path:str, df:pd.DataFrame=train_all) -> np.ndarray:
    """
    Convert all RLE encoded pixels for an image and returns the mask
    """
    height, width = 256, 1600

    def build_mask(df) -> np.ndarray:
        masks = defaultdict(np.ndarray)
        for num, row in enumerate(df.itertuples()):
            masks[num] = rle_to_mask(row.EncodedPixels, row.ClassId, height, width)

        mask = masks.pop(0)

        items_left = len(masks)
        if items_left:
            for item in range(items_left):
                mask_to_add = masks.get(item + 1)
                mask = np.add(mask, mask_to_add)

        return mask

    img_id = img_path.name
    img_df = df.loc[df["ImageId"] == img_id]
    return build_mask(img_df)

# Cell
def img_with_mask(img_path:str):
    return np.array(Image.open(img_path)), multi_rle_to_mask(img_path)

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
def plot_defected_image(img_path:str, df:pd.DataFrame=train):
    """
    Plot image with segmented area
    """
    def color(x, y, classid):
        if classid == 4:
            im[y, x, 1] += 50
            im[y, x, 2] += 50
        else:
            im[y, x, classid-1] += 50

    def plot(im, imgid, classids):
        clip_im = np.clip(im, 0, 255)
        title = "ImageId: {} - ClassId: {}".format(imgid, " ".join(map(str, classids)))

        plt.figure(figsize=(25,5))
        plt.imshow(clip_im)
        plt.xticks([]);plt.yticks([]);
        plt.title(title, fontsize=20)
        plt.show()

    im = np.array(Image.open(img_path))

    img_id = img_path.name
    df = df.loc[df["ImageId"] == img_id]

    classids = []
    for img in df.itertuples(index=False):
        classids.append(img.ClassId)
        classid = img.ClassId

        x, y = defeat_position(img_id, classid)

        color(x,y,classid)

    plot(im, img_id, classids)

# Cell
def show_defects(class_id=None, n=20, only_defects=True, multi_defects=False):
    """
    Plot multiple images.
    Attributes:
    `class_id`: [str or int] select a type of defect otherwise plot all kinds,
    `n`: select the number of images to plot
    `only_defects` [bool, default True]: if False it shows even the no faulty images
    `multi_defects` [bool, default False]: if True it shows imgs with multi defects
    """
    df = train_multi

    cond_no_defects = df["ClassId_multi"] == '0'
    cond_multi_defects = df["ClassId_multi"].map(lambda x: len(x) > 1)
    cond_classId = df["ClassId_multi"].map(lambda x: str(class_id) in x)

    df = df.loc[cond_no_defects]    if not only_defects else df.loc[~cond_no_defects]
    df = df.loc[cond_multi_defects] if multi_defects    else df.loc[~cond_multi_defects]
    df = df.loc[cond_classId]       if class_id         else df

    imgid_from_df = df["ImageId"].tolist()
    pfiles_list = L([train_path / imgid for imgid in imgid_from_df])

    perm_paths = get_perm_imgs_path(pfiles_list, df)
    for img_path in perm_paths[:n]:
        plot_defected_image(img_path)