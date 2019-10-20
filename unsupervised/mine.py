"""Build, train and evaluate a MINE Model

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


from tensorflow.keras.layers import Input, Dense, Add, Activation, Flatten
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import LearningRateScheduler
from tensorflow.keras.utils import plot_model
from tensorflow.keras import backend as K
from tensorflow.keras.datasets import mnist
from tensorflow.keras.utils import to_categorical

import numpy as np
import os
import argparse
import vgg

import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats.contingency import margins


from data_generator import DataGenerator
from utils import unsupervised_labels, center_crop, AccuracyCallback, lr_schedule

def sample(joint=True,
           mean=[0, 0],
           cov=[[1, 0.9], [0.9, 1]],
           n_data=1000000):
    xy = np.random.multivariate_normal(mean=mean,
                                       cov=cov,
                                       size=n_data)
    if joint:
        return xy 
    y = np.random.multivariate_normal(mean=mean,
                                      cov=cov,
                                      size=n_data)
    x = xy[:,0].reshape(-1,1)
    y = y[:,1].reshape(-1,1)
   
    xy = np.concatenate([x, y], axis=1)
    return xy


def compute_mi(cov_xy=0.9, n_bins=100):
    cov=[[1, cov_xy], [cov_xy, 1]]
    data = sample(cov=cov)
    joint, edge = np.histogramdd(data, bins=n_bins)
    joint /= joint.sum()
    eps = np.finfo(float).eps
    joint[joint<eps] = eps
    x, y = margins(joint)
    xy = x*y
    xy[xy<eps] = eps
    mi = joint*np.log(joint/xy)
    mi = mi.sum()
    print("Computed MI: %0.6f" % mi)
    return mi


class SimpleMINE():
    def __init__(self,
                 args,
                 input_dim=1,
                 hidden_units=16,
                 output_dim=1):
        self.args = args
        self._model = None
        self.build_model(input_dim,
                         hidden_units,
                         output_dim)


    # build a simple MINE model
    def build_model(self,
                    input_dim,
                    hidden_units,
                    output_dim):
        inputs1 = Input(shape=(input_dim))
        inputs2 = Input(shape=(input_dim))
        x1 = Dense(hidden_units)(inputs1)
        x2 = Dense(hidden_units)(inputs2)
        x = Add()([x1, x2])
        x = Activation('relu')(x)
        outputs = Dense(output_dim)(x)
        inputs = [inputs1, inputs2]
        self._model = Model(inputs,
                            outputs,
                            name='MINE')
        self._model.summary()


    def loss(self, y_true, y_pred):
        size = self.args.batch_size
        # lower half is pred for joint dist
        pred_xy = y_pred[0: size, :]

        # upper half is pred for marginal dist
        pred_x_y = y_pred[size : y_pred.shape[0], :]
        loss = K.mean(pred_xy) \
               - K.log(K.mean(K.exp(pred_x_y)))
        return -loss


    # train MINE to estimate MI between X and Y of a 2D Gaussian
    def train(self):
        optimizer = Adam(lr=0.01)
        self._model.compile(optimizer=optimizer,
                            loss=self.loss)
        plot_loss = []
        cov=[[1, self.args.cov_xy], [self.args.cov_xy, 1]]
        loss = 0.
        for epoch in range(self.args.epochs):
            xy = sample(n_data=self.args.batch_size,
                        cov=cov)
            x1 = xy[:,0].reshape(-1,1)
            y1 = xy[:,1].reshape(-1,1)
            xy = sample(joint=False,
                        n_data=self.args.batch_size,
                        cov=cov)
            x2 = xy[:,0].reshape(-1,1)
            y2 = xy[:,1].reshape(-1,1)
    
            x =  np.concatenate((x1, x2))
            y =  np.concatenate((y1, y2))
            loss_item = self._model.train_on_batch([x, y],
                                                   np.zeros(x.shape))
            loss += loss_item
            plot_loss.append(loss_item)
            if (epoch + 1) % 100 == 0:
                print("Epoch %d MINE MI: %0.6f" % ((epoch+1), -loss/100))
                loss = 0.


    @property
    def model(self):
        return self._model


class LinearClassifier():
    def __init__(self,
                 latent_dim=16,
                 n_classes=10):
        self.args = args
        self.build_model(latent_dim, n_classes)


    def build_model(self, latent_dim, n_classes):
        inputs = Input(shape=(latent_dim,))
        x = Dense(128)(inputs)
        outputs = Dense(n_classes, activation='softmax')(x)
        name = "classifier"
        self._model = Model(inputs, outputs, name=name)
        self._model.compile(loss='categorical_crossentropy',
                            optimizer='adam',
                            metrics=['accuracy'])
        self._model.summary()


    def train(self, x_test, y_test):
        self._model.fit(x_test,
                        y_test,
                        epochs=1,
                        batch_size=128)


    def eval(self, x_test, y_test):
        score = self._model.evaluate(x_test,
                                     y_test,
                                     batch_size=128)
        accuracy = score[1] * 100
        return accuracy


class MINE():
    def __init__(self,
                 args,
                 backbone):
        self.args = args
        self.backbone = backbone
        self._model = None
        self.train_gen = DataGenerator(args, siamese=True, mine=True)
        self.n_labels = self.train_gen.n_labels
        self.build_model()
        self.accuracy = 0


    def build_model(self):
        self.latent_dim = 16
        inputs = Input(shape=self.train_gen.input_shape)
        x = self.backbone(inputs)
        x = Flatten()(x)
        y = Dense(self.latent_dim,
                  activation='linear',
                  name="class")(x)
        self._encoder = Model(inputs, y, name="encoder")
        self._mine = SimpleMINE(self.args,
                                input_dim=self.latent_dim,
                                hidden_units=256,
                                output_dim=1)
        inputs1 = Input(shape=self.train_gen.input_shape)
        inputs2 = Input(shape=self.train_gen.input_shape)
        x1 = self._encoder(inputs1)
        x2 = self._encoder(inputs2)
        outputs = self._mine.model([x1, x2])
        self._model = Model([inputs1, inputs2], outputs, name='encoder')
        optimizer = Adam(lr=1e-3)
        self._model.compile(optimizer=optimizer, loss=self.loss)
        self._model.summary()
        self.load_eval_dataset()
        self._classifier = LinearClassifier(latent_dim=self.latent_dim)



    # MINE loss 
    def loss(self, y_true, y_pred):
        size = self.args.batch_size
        # lower half is pred for joint dist
        pred_xy = y_pred[0: size, :]

        # upper half is pred for marginal dist
        pred_x_y = y_pred[size : y_pred.shape[0], :]
        loss = K.mean(pred_xy) \
               - K.log(K.mean(K.exp(pred_x_y)))
        return -loss


    # train the model
    def train(self):
        accuracy = AccuracyCallback(self)
        lr_scheduler = LearningRateScheduler(lr_schedule, verbose=1)
        callbacks = [accuracy, lr_scheduler]
        self._model.fit_generator(generator=self.train_gen,
                                  use_multiprocessing=True,
                                  epochs=self.args.epochs,
                                  callbacks=callbacks,
                                  workers=4,
                                  shuffle=True)

    # pre-load test data for evaluation
    def load_eval_dataset(self):
        (_, _), (x_test, self.y_test) = self.args.dataset.load_data()
        image_size = x_test.shape[1]
        x_test = np.reshape(x_test,[-1, image_size, image_size, 1])
        x_test = x_test.astype('float32') / 255
        x_eval = np.zeros([x_test.shape[0], *self.train_gen.input_shape])
        for i in range(x_eval.shape[0]):
            x_eval[i] = center_crop(x_test[i])

        self.y_test = to_categorical(self.y_test)
        self.x_test = x_eval


    # reload model weights for evaluation
    def load_weights(self):
        if self.args.restore_weights is None:
            raise ValueError("Must load model weights for evaluation")

        if self.args.restore_weights:
            folder = "weights"
            os.makedirs(folder, exist_ok=True) 
            path = os.path.join(folder, self.args.restore_weights)
            print("Loading weights... ", path)
            self._model.load_weights(path)


    # evaluate the accuracy of the current model weights
    def eval(self):
        y_pred = self._encoder.predict(self.x_test)
        self._classifier.train(y_pred, self.y_test)
        accuracy = self._classifier.eval(y_pred, self.y_test)

        #y_pred = np.argmax(y_pred, axis=1)

        #accuracy = unsupervised_labels(list(self.y_test),
        #                               list(y_pred),
        #                               self.n_labels,
        #                               self.n_labels)

        
        info = "Accuracy: %0.2f%%"
        if self.accuracy > 0:
            info += ", Old best accuracy: %0.2f%%" 
            data = (accuracy, self.accuracy)
        else:
            data = (accuracy)
        print(info % data)
        # if accuracy improves during training, 
        # save the model weights on a file
        if accuracy > self.accuracy \
            and self.args.save_weights is not None:
            folder = self.args.save_dir
            os.makedirs(folder, exist_ok=True) 
            path = os.path.join(folder, self.args.save_weights)
            print("Saving weights... ", path)
            self._model.save_weights(path)

        if accuracy > self.accuracy: 
            self.accuracy = accuracy

    @property
    def model(self):
        return self._model


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MI on 2D Gaussian')
    parser.add_argument('--cov_xy',
                        type=float,
                        default=0.5,
                        help='Gaussian off diagonal element')
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
                        default=1000,
                        metavar='N',
                        help='Number of epochs to train')
    parser.add_argument('--batch-size',
                        type=int,
                        default=10000,
                        metavar='N',
                        help='Train batch size')
    parser.add_argument('--gaussian',
                        default=False,
                        action='store_true',
                        help='Compute MI of 2D Gaussian')
    parser.add_argument('--plot-model',
                        default=False,
                        action='store_true',
                        help='Plot all network models')
    parser.add_argument('--train',
                        default=False,
                        action='store_true',
                        help='Train the model')
    parser.add_argument('--heads',
                        type=int,
                        default=1,
                        metavar='N',
                        help='Number of heads')

    args = parser.parse_args()
    print("Covariace off diagonal:", args.cov_xy)
    if args.gaussian:
        simple_mine = SimpleMINE(args)
        simple_mine.train()
        compute_mi(cov_xy=args.cov_xy)
    else:
        # build backbone
        backbone = vgg.VGG(vgg.cfg['F'])
        backbone.model.summary()
        # instantiate MINE object
        mine = MINE(args, backbone.model)
        if args.plot_model:
            plot_model(backbone.model,
                       to_file="backbone-vgg.png",
                       show_shapes=True)
            plot_model(mine.model,
                       to_file="model-mine.png",
                       show_shapes=True)
        if args.train:
            mine.train()
