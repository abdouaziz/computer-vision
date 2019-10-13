"""VGG Model

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import tensorflow as tf

from tensorflow.keras.layers import Dense, Conv2D, BatchNormalization, Activation
from tensorflow.keras.layers import MaxPooling2D, Input, Flatten, AveragePooling2D
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import ModelCheckpoint, LearningRateScheduler
from tensorflow.keras.callbacks import ReduceLROnPlateau
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.models import Model
from tensorflow.keras.utils import plot_model

import numpy as np
import os
from data_generator import DataGenerator

cfg = {
    'A': [64, 'M', 128, 'M', 256, 256, 'M', 512, 512, 'M', 512, 512, 'M'],
    'B': [64, 64, 'M', 128, 128, 'M', 256, 256, 'M', 512, 512, 'M', 512, 512, 'M'],
    'D': [64, 64, 'M', 128, 128, 'M', 256, 256, 256, 'M', 512, 512, 512, 'M', 512, 512, 512, 'M'],
    'E': [64, 64, 'M', 128, 128, 'M', 256, 256, 256, 256, 'M', 512, 512, 512, 512, 'M',512, 512, 512, 512, 'M'],
    'F': [64, 'M', 128, 'M', 256, 'M', 512],
    'G': [64, 'M', 128, 'M', 256, 256, 'M', 512, 512, 'A'],
}


class VGG():
    def __init__(self, cfg, input_shape=(24, 24, 1)):
        self.cfg = cfg
        self.input_shape = input_shape
        self._model = None
        self.build_model()

    def build_model(self):
        inputs = Input(shape=self.input_shape)
        x = make_layers(self.cfg, inputs)
        self._model = Model(inputs, x)

    @property
    def model(self):
        return self._model


def make_layers(cfg, inputs, batch_norm=True, in_channels=1):
    x = inputs
    for v in cfg:
        if v == 'M':
            x = MaxPooling2D()(x)
        elif v == 'A':
            x = AveragePooling2D(pool_size=3)(x)
        else:
            x = Conv2D(v,
                       kernel_size=3,
                       padding='same',
                       kernel_initializer='he_normal'
                       )(x)
            if batch_norm:
                x = BatchNormalization()(x)
            x = Activation('relu')(x)
    
    return x

        
if __name__ == '__main__':
    backbone = VGG(cfg['F'])
    backbone.model.summary()
