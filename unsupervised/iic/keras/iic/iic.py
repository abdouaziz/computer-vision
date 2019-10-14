"""Build, train and evaluate an IIC Model

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import tensorflow as tf
from tensorflow.keras.layers import Input, Dense, Flatten
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import ModelCheckpoint, LearningRateScheduler, Callback
from tensorflow.keras.utils import plot_model
from tensorflow.keras import backend as K
from tensorflow.keras.datasets import mnist

import numpy as np
import os
import argparse
import vgg

from data_generator import DataGenerator
from utils import unsupervised_labels


def lr_schedule(epoch):
    lr = 1e-3
    power = epoch // 400
    lr *= 0.8**power

    return lr


class AccuracyCallback(Callback):
    def __init__(self, iic):
        super(AccuracyCallback, self).__init__()
        self.iic = iic

    def on_epoch_end(self, epoch, logs=None):
        self.iic.eval()


class IIC():
    def __init__(self,
                 args,
                 backbone):
        self.args = args
        self.backbone = backbone
        self._model = None
        self.train_gen = DataGenerator(args, siamese=True)
        self.n_labels = self.train_gen.n_labels
        self.build_model()
        self.load_eval_dataset()
        self.accuracy = 0


    def build_model(self):
        inputs = Input(shape=self.train_gen.input_shape)
        x = self.backbone(inputs)
        x = Flatten()(x)
        outputs = []
        for i in range(self.args.heads):
            name = "head%d" % i
            outputs.append(Dense(self.n_labels,
                                 activation='softmax',
                                 name=name)(x))
        self._model = Model(inputs, outputs)
        optimizer = Adam(lr=1e-3)
        self._model.compile(optimizer=optimizer, loss=self.loss)
        self._model.summary()

    
    def loss(self, y_true, y_pred):
        size = self.args.batch_size
        n_labels = y_pred.shape[-1]
        y = y_pred[0: size, :]
        y = K.expand_dims(y, axis=2)
        yt = y_pred[size: y_pred.shape[0], :]
        yt = K.expand_dims(yt, axis=1)
        P = K.batch_dot(y, yt)
        P = K.sum(P, axis=0)
        P = (P + K.transpose(P)) / 2.0
        P = P / K.sum(P)
        Pi = K.expand_dims(K.sum(P, axis=1), axis=1)
        Pj = K.expand_dims(K.sum(P, axis=0), axis=0)
        Pi = K.repeat_elements(Pi, rep=n_labels, axis=1)
        Pj = K.repeat_elements(Pj, rep=n_labels, axis=0)
        #Pi = K.tile(Pi, [1, self.n_labels])
        #Pj = K.tile(Pj, [self.n_labels, 1])
        P = K.clip(P, K.epsilon(), np.finfo(float).max)
        Pi = K.clip(Pi, K.epsilon(), np.finfo(float).max)
        Pj = K.clip(Pj, K.epsilon(), np.finfo(float).max)
        neg_mi = K.sum((P * (K.log(Pi) + K.log(Pj) - K.log(P))))
        return neg_mi
        #return neg_mi/self.args.heads


    def train(self):
        save_dir = self.args.save_dir
        if not os.path.isdir(save_dir):
            os.makedirs(save_dir)

        #model_name = "heads-%d" % self.args.n_heads
        #model_name += '-{epoch:04d}.h5'
        #filepath = os.path.join(save_dir, model_name)
        #checkpoint = ModelCheckpoint(filepath=filepath,
        #                             verbose=1,
        #                             save_weights_only=True)

        accuracy = AccuracyCallback(self)
        lr_scheduler = LearningRateScheduler(lr_schedule, verbose=1)
        callbacks = [accuracy, lr_scheduler]
        self._model.fit_generator(generator=self.train_gen,
                                  use_multiprocessing=True,
                                  epochs=self.args.epochs,
                                  callbacks=callbacks,
                                  workers=8,
                                  shuffle=True)


    def crop(self, image, crop_size=4):
        height, width = image.shape[0], image.shape[1]
        x = height - crop_size
        y = width - crop_size
        dx = dy = crop_size // 2
        image = image[dy:(y + dy), dx:(x + dx), :]
        return image


    def load_eval_dataset(self):
        (_, _), (x_test, self.y_test) = self.args.dataset.load_data()
        image_size = x_test.shape[1]
        x_test = np.reshape(x_test,[-1, image_size, image_size, 1])
        x_test = x_test.astype('float32') / 255
        #x_eval = np.zeros((x_test.shape[0], image_size - self.args.crop, image_size - self.args.crop, 1))
        x_eval = np.zeros([x_test.shape[0], *self.train_gen.input_shape])
        for i in range(x_eval.shape[0]):
            x_eval[i] = self.crop(x_test[i])

        self.x_test = x_eval


    def load_weights(self):
        if self.args.restore_weights is None:
            raise ValueError("Must load model weights for evaluation")

        if self.args.restore_weights:
            folder = "weights"
            os.makedirs(folder, exist_ok=True) 
            path = os.path.join(folder, self.args.restore_weights)
            print("Loading weights... ", path)
            self._model.load_weights(path)


    def eval(self):
        y_pred = self._model.predict(self.x_test)
        print("")
        for head in range(self.args.heads):
            if self.args.heads == 1:
                y_head = y_pred
            else:
                y_head = y_pred[head]
            y_head = np.argmax(y_head, axis=1)

            accuracy = unsupervised_labels(list(self.y_test), list(y_head), self.n_labels, self.n_labels)
            print("Head %d accuracy: %0.2f%%, Current best accuracy: %0.2f%%" % (head, accuracy, self.accuracy))
            if accuracy > self.accuracy and args.save_weights is not None:
                self.accuracy = accuracy
                folder = args.save_dir
                os.makedirs(folder, exist_ok=True) 
                path = os.path.join(folder, self.args.save_weights)
                print("Saving weights... ", path)
                self._model.save_weights(path)


    @property
    def model(self):
        return self._model


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='IIC Keras')
    parser.add_argument('--save-dir',
                       default="weights",
                       help='Folder for storing model weights (h5)')
    parser.add_argument('--save-weights',
                       default=None,
                       help='Folder for storing model weights (h5)')
    parser.add_argument('--dataset',
                       default=mnist,
                       help='Dataset to use')
    parser.add_argument('--epochs',
                        type=int,
                        default=4375,
                        metavar='N',
                        help='Number of epochs to train')
    parser.add_argument('--batch-size',
                        type=int,
                        default=512,
                        help='Train batch size')
    parser.add_argument('--heads',
                        type=int,
                        default=1,
                        metavar='N',
                        help='Number of heads')
    parser.add_argument('--restore-weights',
                        default=None,
                        help='Restore saved model weights')
    parser.add_argument('--train',
                        default=False,
                        action='store_true',
                        help='Evaluate')
    parser.add_argument('--eval',
                        default=False,
                        action='store_true',
                        help='Evaluate')
    parser.add_argument('--crop',
                        type=int,
                        default=4,
                        help='Pixels to crop from the image')

    args = parser.parse_args()

    backbone = vgg.VGG(vgg.cfg['F'])
    backbone.model.summary()
    iic = IIC(args, backbone.model)
    if args.eval:
        iic.load_weights()
        iic.eval()
    elif args.train:
        iic.train()
