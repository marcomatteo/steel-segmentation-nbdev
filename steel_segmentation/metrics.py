# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/05_metrics.ipynb (unless otherwise specified).

__all__ = ['ModDiceMulti']

# Cell
import torch
import numpy as np
from fastai.torch_core import TensorBase, flatten_check
from fastai.metrics import Metric

# Cell
class ModDiceMulti(Metric):
    "Averaged Dice metric (Macro F1) for multiclass target in segmentation"

    def __init__(self, axis=1, with_logits=False):
        self.axis = axis
        self.with_logits = with_logits

    def reset(self): self.inter, self.union =  {}, {}

    def accumulate(self, learn):
        if self.with_logits:
            logit = learn.pred
            prob = torch.sigmoid(logit)
            pred = (prob > 0.5).float().argmax(dim=self.axis)
        else:
            pred = learn.pred.argmax(dim=self.axis)

        y = learn.yb[0]
        # Added to deal with 4-channels masks
        if pred.shape != y.shape:
            y = y.argmax(dim=self.axis)

        pred, targ = flatten_check(pred, y)
        for c in range(learn.pred.shape[self.axis]):
            p = torch.where(pred == c, 1, 0)
            t = torch.where(targ == c, 1, 0)
            p, t = TensorBase(p), TensorBase(t) # may be redundant (old fastai bug)
            c_inter = (p*t).float().sum().item()
            c_union = (p+t).float().sum().item()
            if c in self.inter:
                self.inter[c] += c_inter
                self.union[c] += c_union
            else:
                self.inter[c] = c_inter
                self.union[c] = c_union

    @property
    def value(self):
        binary_dice_scores = np.array([])
        for c in self.inter:
            binary_dice_scores = np.append(
                binary_dice_scores,
                2.*self.inter[c]/self.union[c] if self.union[c] > 0 else np.nan)
        self.binary_dice_scores = binary_dice_scores
        return np.nanmean(binary_dice_scores)