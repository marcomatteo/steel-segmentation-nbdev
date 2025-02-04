# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/02_transforms.ipynb (unless otherwise specified).

__all__ = ['ReadImagePathFromIndex', 'ReadRLEs', 'MakeMask', 'ChannelMask', 'get_train_aug', 'get_valid_aug',
           'AlbumentationsTransform', 'SteelMaskBlock', 'SteelDataBlock', 'get_kfold_splits', 'KFoldSplitter',
           'SteelDataLoaders']

# Cell
from fastai.vision.all import *
import os
import pandas as pd
import numpy as np
import torch
from sklearn.model_selection import StratifiedKFold
from .utils import rle2mask, mask2rle, get_train_df
import albumentations as alb

# Cell
class ReadImagePathFromIndex(Transform):
    """Read image name from `train_pivot` and returns the image path"""
    def __init__(self, pref):
        self.pref = str(pref) + os.path.sep if isinstance(pref, Path) else pref

    def encodes(self, row:pd.Series, **kwargs):
        o = row.name # ImageId
        return f'{self.pref}{o}'

# Cell
class ReadRLEs(Transform):
    """Read RLEs from `train_pivot` and return a list or RLEs."""
    def __init__(self, cols=[1,2,3,4]):
        self.cols = L(cols)

    def encodes(self, row:pd.Series, **kwargs):
        return [row[i] if not row[i] is np.nan else ''
                for i in self.cols]

# Cell
class MakeMask(Transform):
    """Read RLEs list and return a np.array of the mask"""
    h, w = (256, 1600)

    def __init__(self, flatten=True):
        self.flatten = flatten

    def encodes(self, o:list, **kwargs):
        mask = np.zeros((self.h, self.w, 4), dtype=np.float32) # 4:class 1～4 (ch:0～3)

        for i in range(4):
            rle = o[i]
            if rle != '':
                mask[:, :, i] = rle2mask(rle=rle, value=1, shape=(self.h,self.w))

        if self.flatten:
            classes = np.array(range(1,5))
            return (mask * classes).sum(-1)

        return mask

    def decodes(self, mask, **kwargs):
        mask = (mask * np.array(range(1,5))).sum(-1) if len(mask.shape) == 3 else mask
        return [mask2rle(np.where(mask==c, mask, 0)) for c in range(1,5)]

# Cell
class ChannelMask(Transform):
    """Transform (x,y) tensor masks from [w, h] to [channels, w, h]"""
    order=9

    def create_mask(self, mask):
        new_mask = torch.zeros(4, mask.shape[0], mask.shape[1])
        for i in range(4):
            new_mask[i] = torch.where(mask==(i+1), 1, 0)
        return new_mask

    def decode_mask(self, mask, classes):
        # tensorboard log images bug in TensorBoardCallback after_epoch
        if mask.device != classes.device:
            mask = mask.to(classes.device)
        if mask.shape[0] != classes.shape[0]:
            return mask # bad workaround for TensorBoardCallback log_preds=True
        return (mask * classes).sum(0)

    def encodes(self, o:TensorMask):
        if o.dim() == 2: return self.create_mask(o)
        elif o.dim() == 3:
            new_batch = []
            for mask in o: new_batch.append(self.create_mask(mask))
            return torch.stack(new_batch, axis=0)
        else: return o

    def decodes(self, o:TensorMask):
        classes = torch.tensor(range(1,5)).unsqueeze(-1).unsqueeze(-1)
        if o.dim() == 3: return self.decode_mask(o, classes)
        elif o.dim() == 4:
            new_masks = []
            for mask in o:
                new_masks.append(self.decode_mask(mask, classes))
            return torch.stack(new_masks, axis=0)
        else: return o

# Cell
HEIGHT, WIDTH = (224, 1568)

def get_train_aug(height, width):
    tfm_list = [
      alb.RandomCrop(height, width, p=1.0),
      #alb.Resize(128, 800),
      alb.OneOf(
          [
           alb.VerticalFlip(p=0.5),
           alb.HorizontalFlip(p=0.5),
          ], p=0.6),
      alb.OneOf(
          [
           alb.RandomBrightnessContrast(
               brightness_limit=(-0.2, 0.2), contrast_limit=(-0.2, 0.2), p=0.5),
           alb.RandomGridShuffle(grid=(1, 2), p=0.2),
          ], p=0.6),
    ]
    return alb.Compose(tfm_list)

def get_valid_aug(height, width):
    tfms = [alb.RandomCrop(height, width)]
    return alb.Compose(tfms)

class AlbumentationsTransform(ItemTransform, RandTransform):
    "A transform handler for multiple `Albumentation` transforms"
    split_idx,order=None,2
    def __init__(self, train_aug, valid_aug):
        self.train_aug, self.valid_aug = train_aug, valid_aug

    def before_call(self, b, split_idx):
        self.idx = split_idx

    def encodes(self, o):
        img, mask = o
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
def SteelMaskBlock(train_aug, valid_aug):
    # get_y tfms
    type_tfms = [
        MakeMask(),
        PILMask.create
    ]
    # input, target tfms
    item_tfms = [
        AddMaskCodes([1,2,3,4]),
        ToTensor(),
        AlbumentationsTransform(train_aug, valid_aug)
    ]
    # batch tfms
    batch_tfms = [
        IntToFloatTensor(),
        Normalize.from_stats(*imagenet_stats),
        ChannelMask()
    ]
    return TransformBlock(type_tfms=type_tfms, item_tfms=item_tfms, batch_tfms=batch_tfms)

# Cell
def SteelDataBlock(path, splitter=None, train_aug=None, valid_aug=None, *args, **kwargs) -> DataBlock:
    """Get the DataBlock for Severstal Dataset."""
    if train_aug is None:
        train_aug = get_train_aug(HEIGHT, WIDTH)
    if valid_aug is None:
        valid_aug = get_valid_aug(HEIGHT, WIDTH)
    if splitter is None:
        splitter = TrainTestSplitter(0.2)

    steel_block = SteelMaskBlock(train_aug, valid_aug)
    block = DataBlock(
        blocks = (ImageBlock, steel_block),
        get_x = ReadImagePathFromIndex(pref=(path/"train_images")),
        get_y = ReadRLEs(),
        splitter = splitter,
        *args, **kwargs
    )
    return block

# Cell
def get_kfold_splits(df_pivot, nsplits=2):
    df = df_pivot.reset_index()
    X = df["ImageId"].to_numpy()
    y = df["ClassIds"].to_numpy()
    skf = StratifiedKFold(n_splits=nsplits, shuffle=True)
    splits = []
    for i, (train_index, valid_index) in enumerate(skf.split(X, y)):
        print(
            f"{i}-fold:",
            f"Train: #{len(train_index)}, e.g. {train_index[:5]}",
            f"Valid: #{len(valid_index)}, e.g. {valid_index[:5]}",
            sep='\n', end='\n\n')
        splits.append([L(list(train_index)), L(list(valid_index))])

    return splits

# Cell
def KFoldSplitter(splits, idx):

    def _inner(o):
        return splits[idx]

    return _inner

# Cell
def SteelDataLoaders(block, source, bs, *args, **kwargs) -> DataLoaders:
    """Get the DataLoaders for Severstal Dataset."""
    dls = block.dataloaders(
        source=source,
        bs=bs,
        num_workers=0,
        *args, **kwargs
    )
    return dls