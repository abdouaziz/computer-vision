"""Data generator for center cropped and transformed MNIST images

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow.keras.utils import Sequence
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.datasets import mnist

import numpy as np
from skimage.transform import resize, rotate


class DataGenerator(Sequence):
    def __init__(self,
                 args,
                 shuffle=True,
                 siamese=False,
                 mine=False,
                 crop_size=4):
        self.args = args
        self.shuffle = shuffle
        self.siamese = siamese
        self.mine = mine
        self.crop_size = crop_size
        self._dataset()
        self.on_epoch_end()

    # number of batches per epoch
    def __len__(self):
        return int(np.floor(len(self.indexes) / self.args.batch_size))


    # indexes for the current batch
    def __getitem__(self, index):
        start_index = index * self.args.batch_size
        end_index = (index+1) * self.args.batch_size
        return self.__data_generation(start_index, end_index)

    # load dataset and normalize it
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


    # shuffle dataset after each epoch
    def on_epoch_end(self):
        if self.shuffle == True:
            np.random.shuffle(self.indexes)


    # random crop, resize back to its target shape
    def random_crop(self, image, target_shape, crop_sizes):
        height, width = image.shape[0], image.shape[1]
        choice = np.random.randint(0, len(crop_sizes))
        d = crop_sizes[choice]
        x = height - d
        y = width - d
        center = np.random.randint(0, 2)
        if center:
            dx = dy = d // 2
        else:
            dx = np.random.randint(0, d + 1)
            dy = np.random.randint(0, d + 1)

        image = image[dy:(y + dy), dx:(x + dx), :]
        image = resize(image, target_shape)
        return image


    # random image rotation
    def random_rotate(self, image, deg=20, target_shape=(24, 24, 1)):
        choice = np.random.randint(-deg, deg)
        image = rotate(image, choice)
        image = resize(image, target_shape)
        return image


    # data generation algorithm
    def __data_generation(self, start_index, end_index):

        d = self.crop_size // 2
        crop_sizes = [self.crop_size*2 + i for i in range(0,5,2)]
        image_size = self.data.shape[1] - self.crop_size
        x = self.data[self.indexes[start_index : end_index]]
        y1 = self.label[self.indexes[start_index : end_index]]

        target_shape = (x.shape[0], *self.input_shape)
        x1 = np.zeros(target_shape)
        if self.siamese:
            y2 = y1 
            x2 = np.zeros(target_shape)

        for i in range(x1.shape[0]):
            image = x[i]
            x1[i] = image[d: image_size + d, d: image_size + d]
            if self.siamese:
                choice = np.random.randint(0, 4)
                # 50-50% chance of crop or rotate
                if choice < 2:
                    x2[i] = self.random_rotate(image,
                                               target_shape=target_shape[1:])
                else:
                    x2[i] = self.random_crop(image,
                                             target_shape[1:],
                                             crop_sizes)

        # for IIC, we are mostly interested in paired images
        # X and Xbar = G(X)
        if self.siamese:
            if self.mine:
                y = np.concatenate([y1, y2], axis=0)
                m1 = np.copy(x1)
                m2 = np.copy(x2)
                #np.random.shuffle(m1) 
                np.random.shuffle(m2)

                x1 =  np.concatenate((x1, m1), axis=0)
                x2 =  np.concatenate((x2, m2), axis=0)
                x = (x1, x2)
                return x, y

            x_train = np.concatenate([x1, x2], axis=0)
            y_train = np.concatenate([y1, y2], axis=0)
            y = []
            for i in range(self.args.heads):
                y.append(y_train)
            return x_train, y

        return x1, y1


if __name__ == '__main__':
    datagen = DataGenerator()

