#!/usr/bin/env python3

'Build a h5py dataset from map labelings recorded in the database.'

import argparse
import h5py
from pymongo import MongoClient
from PIL import Image
from skimage import io, transform
from base64 import b64decode
from io import BytesIO
import random
from os import path
import numpy as np

def parse_color(c):
    'Parses a color encoded as a hex string into a tuple of bytes.'
    return tuple(map(lambda x: int(x, 16),
                     [c[2*i:2*(i+1)] for i in range(len(c) // 2)]))

parser = argparse.ArgumentParser('Build a h5py dataset from map labelings stored in MongoDB.')
parser.add_argument('-m', '--mongo-url', help='URL used to connect to MongoDB.',
                    default='mongodb://localhost:27017')
parser.add_argument('-d', '--database', help='Name of the MongoDB database where map labelings are stored.',
                    default='openafro')
parser.add_argument('-i', '--input-size', help='Size of the tiles extracted from the input.',
                    type=int, default=128)
parser.add_argument('-t', '--output-size', help='Size of the tiles to be produced by the model.',
                    type=int, default=128)
parser.add_argument('-o', '--output', help='Path to the output h5py file.',
                    default='dataset.hdf5')
parser.add_argument('--class-colors', help='RGB color of all classes present in the overlay (6-character hex string).',
                    nargs='+', default=['00000000', 'ff0000ff', 'ffff00ff'])
parser.add_argument('--tiles-dir', help='Path to directory containing reference tiles (input to the model).',
                    required=True)
parser.add_argument('-e', '--tiles-extension', help='Extension of reference tile images.',
                    default='tif')
parser.add_argument('--train', help='Fraction of tiles to put in training set.',
                    type=float, default=0.8)
parser.add_argument('--validation', help='Fraction of tiles to put in validation set.',
                    type=float, default=0.1)
parser.add_argument('--test', help='Fraction of tiles to put in test set.',
                    type=float, default=0.1)
parser.add_argument('--rotate', help='Augment data by rotating tiles.',
                    default=False, action='store_const', const=True)
parser.add_argument('--flip', help='Augment data by flipping.',
                    default=False, action='store_const', const=True)
opts = parser.parse_args()

i_side, o_side = opts.input_size, opts.output_size
classes = list(map(parse_color, opts.class_colors))

client = MongoClient(opts.mongo_url)

db = client[opts.database]
map_label_overlays = db['maplabeloverlays']

dataset = []
overlays = []

input_size, output_size = opts.input_size, opts.output_size

print('Classes:', classes)
print(map_label_overlays.count_documents({}), 'map label overlays found.')

def classify_pixels(image, classes):
    '''Gets a WxHxK image and produces a CxWxH matrix where the i-th channel contains only pixels in class i.'''

    assert image.shape[2] == len(classes[0]), 'Classes should be in the same color space as the image.'

    m = np.zeros(((len(classes), image.shape[0], image.shape[1])))

    for c, color in enumerate(classes):
        m[c] = (image == color).all(axis=2)

    return m

def split_dataset(X, y, splits):
    s = []

    p = np.arange(len(X))
    np.random.shuffle(p)

    last = 0

    for i in range(len(splits)):
        l = int(len(X) * splits[i]) if i < len(splits) - 1 else len(X) - last
        s.append((X[p[last:last + l]], y[p[last:last + l]]))
        last += l

    return s

X, y = [], []

for overlay in map_label_overlays.find():
    header, data = overlay["image"].split(",", 1)

    if header != "data:image/png;base64":
        print("Ignoring overlay with type", header, "(only PNG overlays supported for now)")
        continue

    overlay_image = io.imread(BytesIO(b64decode(data)))
    tile_path = path.join(opts.tiles_dir, f'{overlay["tile"]}.{opts.tiles_extension}')
    img_x = io.imread(tile_path, plugin='gdal')
    n_tiles_v, n_tiles_h = img_x.shape[1] // i_side, img_x.shape[2] // i_side

    overlay_classes = classify_pixels(overlay_image, classes)

    assert overlay_classes.shape[1] % n_tiles_v == 0, 'Overlay size should be a multiple of the number of tile divisions.'
    assert overlay_classes.shape[2] % n_tiles_h == 0, 'Overlay size should be a multiple of the number of tile divisions.'
    img_y = transform.downscale_local_mean(overlay_classes, (1, n_tiles_v, n_tiles_h))

    for ti in range(img_x.shape[1] // opts.input_size):
        for tj in range(img_x.shape[2] // opts.input_size):
            x_i = img_x[:, ti*i_side : (ti + 1)*i_side, tj*i_side:(tj + 1)*i_side]
            y_i = img_y[:, ti*o_side : (ti + 1)*o_side, tj*o_side:(tj + 1)*o_side]

            for r in range(4):
                x_i_t = np.rot90(x_i, r, (1, 2))
                y_i_t = np.rot90(y_i, r, (1, 2))

                X.append(x_i_t)
                y.append(y_i_t)

                if r < 2 and opts.flip:
                    for a in (1, 2):
                        X.append(np.flip(x_i_t, axis=a))
                        y.append(np.flip(y_i_t, axis=a))

                if not opts.rotate:
                    break

    print(f'Added example by {overlay["authorName"]} <{overlay["authorEmail"]}>')

X = np.array(X)
y = np.array(y)

print('X shape:', X.shape)
print('y shape:', y.shape)

[train, val, test] = split_dataset(X, y, [opts.train, opts.validation, opts.test])

with h5py.File(opts.output, "w") as output:
    output.create_dataset("X_train", data=train[0])
    output.create_dataset("y_train", data=train[1])
    output.create_dataset("X_val", data=val[0])
    output.create_dataset("y_val", data=val[1])
    output.create_dataset("X_test", data=test[0])
    output.create_dataset("y_test", data=test[1])

    output.attrs.create("input_bands", X.shape[1])
    output.attrs.create("output_bands", y.shape[1])
    output.attrs.create("input_size", X.shape[2])
    output.attrs.create("output_size", y.shape[2])

    output.close()

print('Wrote', opts.output, 'with', len(train[0]), 'training examples,',
      len(val[0]), 'validation examples and',
      len(test[0]), 'test examples.')
