"""Data generator for original and affine MNIST images

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

#from tensorflow.python.keras.utils.data_utils import Sequence
import tensorflow as tf
from tensorflow.keras.utils import Sequence
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.datasets import mnist

import numpy as np
import os
import skimage
from skimage.transform import resize


class DataGenerator(Sequence):
    def __init__(self,
                 args,
                 shuffle=True,
                 siamese=False,
                 crop_size=4):
        self.args = args
        self.shuffle = shuffle
        self.siamese = siamese
        self.crop_size = crop_size
        self._dataset()
        self.on_epoch_end()

    def __len__(self):
        # number of batches per epoch
        return int(np.floor(len(self.indexes) / self.args.batch_size))


    def __getitem__(self, index):
        # indexes of the batch
        start_index = index * self.args.batch_size
        end_index = (index+1) * self.args.batch_size
        return self.__data_generation(start_index, end_index)


    def _dataset(self):
        dataset = self.args.dataset
        if self.args.train:
            (self.data, self.label), (_, _) = dataset.load_data()
        else:
            (_, _), (self.data, self.label) = dataset.load_data()

        if self.args.dataset == mnist:
            self.n_channels = 1
        else:
            self.n_channels = self.data.shape[3]

        image_size = self.data.shape[1]
        side = image_size - self.crop_size
        self.input_shape = [side, side, self.n_channels]

        # from sparse label to categorical
        self.n_labels = len(np.unique(self.label))
        self.label = to_categorical(self.label)

        # reshape and normalize input images
        orig_shape = [-1, image_size, image_size, self.n_channels]
        self.data = np.reshape(self.data, orig_shape)
        self.data = self.data.astype('float32') / 255
        self.indexes = [i for i in range(self.data.shape[0])]


    def on_epoch_end(self):
        # shuffle after each epoch'
        if self.shuffle == True:
            np.random.shuffle(self.indexes)


    def apply_random_noise(self, image, percent=30):
        random = np.random.randint(0, 100)
        if random < percent:
            image = random_noise(image)
        return image


    def random_crop(self, image, target_shape, crop_sizes):
        height, width = image.shape[0], image.shape[1]
        choice = np.random.randint(0, len(crop_sizes))
        d = crop_sizes[choice]
        x = height - d
        y = width - d
        center = np.random.randint(0, 2)
        if center:
            dx = dy = d // 2
            #image = image[dy:(y + dy), dx:(x + dx), :]
        else:
            dx = np.random.randint(0, d + 1)
            dy = np.random.randint(0, d + 1)

        image = image[dy:(y + dy), dx:(x + dx), :]
        image = resize(image, target_shape)
        return image


    def __data_generation(self, start_index, end_index):

        d = self.crop_size // 2
        crop_sizes = [self.crop_size*2 + i for i in range(0,5,2)]
        image_size = self.data.shape[1] - self.crop_size
        x = self.data[self.indexes[start_index : end_index]]
        y1 = self.label[self.indexes[start_index : end_index]]

        #x1 = tf.image.random_crop(x, self.input_shape)
        #x2 = tf.image.random_crop(x, self.input_shape)
        #if self.siamese:
        #    y2 = y1 
        
        #if self.siamese:
        #    x_train = np.concatenate([x1, x2], axis=0)
        #    y_train = np.concatenate([y1, y2], axis=0)
        #    y = []
        #    for i in range(self.args.heads):
        #        y.append(y_train)
        #    return x_train, y

        #return x1, y1


        target_shape = (x.shape[0], *self.input_shape)
        x1 = np.zeros(target_shape)
        if self.siamese:
            y2 = y1 
            x2 = np.zeros(target_shape)

        for i in range(x1.shape[0]):
            image = x[i]
            #x1[i] = image[d: image_size + d, d: image_size + d]
            x1[i] = self.random_crop(image, target_shape[1:], crop_sizes)
            if self.siamese:
                x2[i] = self.random_crop(image, target_shape[1:], crop_sizes)

        if self.siamese:
            x_train = np.concatenate([x1, x2], axis=0)
            y_train = np.concatenate([y1, y2], axis=0)
            y = []
            for i in range(self.args.heads):
                y.append(y_train)
            return x_train, y

        return x1, y1


if __name__ == '__main__':
    datagen = DataGenerator()

