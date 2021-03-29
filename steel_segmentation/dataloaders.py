# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/04_dataloaders.ipynb (unless otherwise specified).

__all__ = ['get_classification_dls', 'AlbumentationsTransform', 'get_train_aug', 'get_valid_aug', 'SteelMaskBlock',
           'get_segmnt_dls', 'get_segmentation_dls', 'get_segmentation_dls_from_df', 'get_train_dls']

# Cell
from .metadata import *
from .masks import *
from .datasets import *

from fastcore.test import *
from fastai.vision.all import *

from collections import defaultdict
from matplotlib import pyplot as plt
import torch

import pandas as pd
import numpy as np
import os
import warnings

from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader
import albumentations as alb

# Cell
def get_classification_dls(bs, with_tfms: bool = True, size=None, seed=42):
    """
    Dataloaders from train DataFrame
    """
    b_tfms = [Normalize.from_stats(*imagenet_stats)]

    if with_tfms:
        b_tfms += aug_transforms(
            size=size if size else (256, 1600),
            max_warp=.1,
            max_rotate=5.,
            max_lighting=0.1)

    dblock = DataBlock(
        blocks=(ImageBlock, MultiCategoryBlock()),
        get_x=ColReader(0, pref=train_path),
        get_y=ColReader(1, label_delim=' '),
        splitter=RandomSplitter(valid_pct=0.2, seed=seed),
        batch_tfms=b_tfms)

    return dblock.dataloaders(train_multi, bs=bs)

# Cell
class AlbumentationsTransform(ItemTransform, RandTransform):
    "A transform handler for multiple `Albumentation` transforms"
    split_idx,order=None,2
    def __init__(self, train_aug, valid_aug): store_attr()

    def before_call(self, b, split_idx):
        self.idx = split_idx

    def encodes(self, o):
        img, mask = o # TBD
        if self.idx == 0:
            aug = self.train_aug(image=np.array(img),mask=np.array(mask))
            aug_img = aug['image']
            aug_mask = aug['mask']
        else:
            aug = self.valid_aug(image=np.array(img),mask=np.array(mask))
            aug_img = aug['image']
            aug_mask = aug['mask']
        return PILImage.create(aug_img), PILMask.create(aug_mask)

# Cell
def get_train_aug(): return alb.Compose([
    alb.CropNonEmptyMaskIfExists(256, 256, p=1., ignore_values=[0]),
    alb.OneOf([
        alb.VerticalFlip(p=0.5),
        alb.HorizontalFlip(p=0.5)], p=0.8),
    alb.RandomRotate90(p=0.5),
    alb.OneOf([
        alb.ElasticTransform(p=0.5, alpha=120, sigma=120 * 0.05, alpha_affine=120 * 0.03),
        alb.GridDistortion(p=0.5),
        alb.OpticalDistortion(distort_limit=1, shift_limit=0.5, p=1),
    ], p=0.8)
])

def get_valid_aug(): return alb.Compose([alb.RandomCrop(256, 256)])

# Cell
def SteelMaskBlock(codes=None, mask4channels=True):
    batch_tfms = [IntToFloatTensor, Normalize.from_stats(*imagenet_stats)]
    if mask4channels: batch_tfms += [ChannelMask]
    return TransformBlock(type_tfms=[MakeMask,PILMask.create],
                          item_tfms=AddMaskCodes(codes),
                          batch_tfms=batch_tfms)

# Cell
@delegates(to=DataLoaders)
def get_segmnt_dls(source:pd.DataFrame=None, bs:int=16, size:tuple=None,
                   train_aug:alb.Compose=None, valid_aug:alb.Compose=None,
                   splitter:tuple=None, flatten_mask:bool=False, **kwargs):
    """
    Create a DataLoaders obj for segmentation models.

    Attributes:
    -----------
        source: pd.DataFrame, the source file with labels, only `train_pivot` or its slices atm.

        bs: int, batch size for training and validation phases.

        size: tuple of ints, crops the images with this size, only squared sizes atm.

        train_aug, valid_aug: albumentations.core.composition.Compose,
        List of augmentation to be applied over the training and validation batches

        splitter: tuple of indexes, idxs for split into training and validation

        flatten_mask: bool, if True returns a flatten mask of shape `size` for each image in the batch.
        Set to True for fastai models (`unet_learner`).

    """
    if source is None:    source=train_pivot
    if size is None:      size=(256,256)
    if train_aug is None: train_aug=get_train_aug()
    if valid_aug is None: valid_aug=get_valid_aug()
    if splitter is None:  splitter=TrainTestSplitter(test_size=0.2)

    # Albumentations tfms
    itfms = [AlbumentationsTransform(train_aug, valid_aug)]
    # Datablock
    block = DataBlock(
        blocks = (ImageBlock,SteelMaskBlock(codes=[1,2,3,4],
                                            mask4channels=flatten_mask)),
        get_x = ReadImagePathFromIndex,
        get_y = ReadRLEs(cols=[1,2,3,4]),
        splitter = splitter,
        item_tfms = itfms
    )
    return block.dataloaders(source=source, bs=bs, **kwargs)

# Cell
def get_segmentation_dls(bs, size, with_btfms=True, seed=42):
    """Deprecated function: Dataloaders from `train_path` folder"""
    warnings.warn("Deprecated function, use `get_segmnt_dls(flatten_mask=True)`")

    b_tfms = [Normalize.from_stats(*imagenet_stats)]

    if with_btfms:
        b_tfms += aug_transforms(
            size=size if size else (256, 1600),
            max_warp=.1,
            max_rotate=5.,
            max_lighting=0.1)

    def get_labels_from_img(p):
        return labels_path/f'{p.stem}_P.png'

    dblock = DataBlock(
        blocks=(ImageBlock, MaskBlock(codes=classes)),
        get_items=get_image_files,
        get_y=get_labels_from_img,
        splitter=RandomSplitter(valid_pct=0.2, seed=seed),
        batch_tfms=b_tfms)

    return dblock.dataloaders(train_path, bs=bs)

# Cell
def get_segmentation_dls_from_df(train_df, bs, size, with_btfms=True, seed=42):
    """Deprecated function: Dataloaders from `train` DataFrame"""
    warnings.warn("Deprecated function, use `get_segmnt_dls(flatten_mask=True)`")

    def get_x(df):
        img_name = df["ImageId"]
        return train_path / str(img_name)

    def get_y(df):
        img_name = df["ImageId"].split(".")[0] + "_P.png"
        return labels_path / img_name

    b_tfms = [Normalize.from_stats(*imagenet_stats)]

    if with_btfms:
        b_tfms += aug_transforms(
            size=size if size else (256, 1600),
            max_warp=.1,
            max_rotate=5.,
            max_lighting=0.1)

    dblock = DataBlock(
        blocks=(ImageBlock, MaskBlock(codes=classes)),
        get_x=get_x,
        get_y=get_y,
        splitter=RandomSplitter(valid_pct=0.2, seed=seed),
        batch_tfms=b_tfms)

    return dblock.dataloaders(train_df, bs=bs)

# Cell
def get_train_dls(
        phase,
        mean=None,
        std=None,
        batch_size=8,
        num_workers=4,
    ):
    '''Returns dataloader for the model training.'''
    warnings.warn("Deprecated function, use `get_segmnt_dls()`")

    df = train_pivot
    if (mean is None) or (std is None):
        mean, std = imagenet_stats

    train_df, val_df = train_test_split(
        df, test_size=0.2, stratify=df["n"], random_state=69)

    df = train_df if phase == "train" else val_df
    image_dataset = SteelDataset(df, mean, std, phase)

    dataloader = DataLoader(
        image_dataset,
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=True,
        shuffle=True,
    )

    return dataloader