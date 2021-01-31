# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/02_dataset.ipynb (unless otherwise specified).

__all__ = ['get_classification_dls', 'classes', 'get_segmentation_dls', 'get_segmentation_dls_from_df',
           'get_transforms', 'SteelDataset', 'TestDataset', 'get_train_dls', 'get_test_dls']

# Cell
from .core import *
from .data import *

from fastcore.test import *
from fastai.vision.all import *
from PIL import Image
from collections import defaultdict
from matplotlib import pyplot as plt

import pandas as pd
import numpy as np
import os
import cv2

from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset, sampler
from albumentations import (
    HorizontalFlip, ShiftScaleRotate, Resize, Compose, GaussNoise)
from albumentations.pytorch import ToTensor
import albumentations as alb

# Cell
def get_classification_dls(bs, with_tfms: bool = True, size=None):
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
        splitter=RandomSplitter(valid_pct=0.2, seed=42),
        batch_tfms=b_tfms)

    return dblock.dataloaders(train_multi, bs=bs)

# Cell
classes = [0, 1, 2, 3, 4]

# Cell
def get_segmentation_dls(bs, size, with_btfms=True):
    """Dataloaders from `train_path` folder"""

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
        splitter=RandomSplitter(valid_pct=0.2, seed=42),
        batch_tfms=b_tfms)

    return dblock.dataloaders(train_path, bs=bs)

# Cell
def get_segmentation_dls_from_df(train_df, bs, size, with_btfms=True):
    """Dataloaders from `train` DataFrame"""
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
        splitter=RandomSplitter(valid_pct=0.2, seed=42),
        batch_tfms=b_tfms)

    return dblock.dataloaders(train_df, bs=bs)

# Cell
def get_transforms(phase, mean, std):
    list_transforms = []
    if phase == "train":
        list_transforms.extend(
            [
                HorizontalFlip(p=0.5),  # only horizontal flip for now
            ]
        )
    list_transforms.extend(
        [
            alb.Normalize(mean=mean, std=std, p=1),
            ToTensor(),
        ]
    )
    list_trfms = Compose(list_transforms)
    return list_trfms

# Cell
class SteelDataset(Dataset):

    def __init__(self, df, data_folder, mean, std, phase):
        self.df = df
        self.root = data_folder
        self.mean = mean
        self.std = std
        self.phase = phase
        self.transforms = get_transforms(phase, mean, std)
        self.fnames = self.df.index.tolist()

    def __getitem__(self, idx):
        image_id, mask = make_mask(idx, self.df)
        image_path = train_path / image_id
        img = cv2.imread(str(image_path))
        augmented = self.transforms(image=img, mask=mask)
        img = augmented['image']
        mask = augmented['mask']         # 1x256x1600x4
        mask = mask[0].permute(2, 0, 1)  # 4x256x1600
        return img, mask

    def __len__(self):
        return len(self.fnames)

# Cell
class TestDataset(Dataset):
    '''Dataset for test prediction'''

    def __init__(self, root, df, mean, std):
        self.root = root
        self.fnames = df['ImageId'].unique().tolist()
        self.num_samples = len(self.fnames)
        self.transform = alb.Compose(
            [
                alb.Normalize(mean=mean, std=std, p=1),
                ToTensor(),
            ]
        )

    def __getitem__(self, idx):
        fname = self.fnames[idx]
        fpath = self.root / fname
        image = cv2.imread(str(fpath))
        images = self.transform(image=image)["image"]
        return fname, images

    def __len__(self):
        return self.num_samples

# Cell
def get_train_dls(
        phase,
        data_folder=path,
        mean=None,
        std=None,
        batch_size=8,
        num_workers=4,
    ):
    '''Returns dataloader for the model training.'''
    df = train_pivot
    if not mean and not std:
        mean, std = imagenet_stats

    train_df, val_df = train_test_split(
        df, test_size=0.2, stratify=df["n"], random_state=69)

    df = train_df if phase == "train" else val_df
    image_dataset = SteelDataset(df, data_folder, mean, std, phase)

    dataloader = DataLoader(
        image_dataset,
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=True,
        shuffle=True,
    )

    return dataloader

# Cell
def get_test_dls(
        sample_submission_path,
        best_threshold=0.5, num_workers=2,
        batch_size=4, min_size=3500,
        mean=None, std=None
    ):
    """Returns dataloader for testing."""
    if not mean and not std:
        mean, std = imagenet_stats
    df = pd.read_csv(sample_submission_path)
    testset = DataLoader(
        TestDataset(test_path, df, mean, std),
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )
    return testset