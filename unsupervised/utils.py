from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
from scipy.optimize import linear_sum_assignment

# linear assignment algorithm
def unsupervised_labels(y, yp, n_classes, n_clusters):
    assert n_classes == n_clusters

    # initialize count matrix
    C = np.zeros([n_clusters, n_classes])

    # populate count matrix
    for i in range(len(y)):
        C[int(yp[i]), int(y[i])] += 1

    # optimal permutation using Hungarian Algo
    # the higher the count, the lower the cost
    # so we use -C for linear assignment
    row, col = linear_sum_assignment(-C)

    # compute accuracy
    accuracy = C[row, col].sum() / C.sum()

    return accuracy * 100

# crop the image from the center
def center_crop(image, crop_size=4):
    height, width = image.shape[0], image.shape[1]
    x = height - crop_size
    y = width - crop_size
    dx = dy = crop_size // 2
    image = image[dy:(y + dy), dx:(x + dx), :]
    return image

