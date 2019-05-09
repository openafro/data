import argparse
import os
import numpy

from osgeo import gdal
from osgeo import osr

def match_names(reference, output):
    print('Renaming tiles in', output, 'to match those in', reference)
    reference_grid = {}

    for root, dirs, files in os.walk(reference):
        for f in files:
            if not f.endswith('.tif'):
                continue
            path = os.path.join(root, f)
            dataset = gdal.OpenEx(path, gdal.OF_READONLY | gdal.OF_RASTER | gdal.OF_SHARED | gdal.OF_VERBOSE_ERROR)
            coefficients = dataset.GetGeoTransform()
            reference_grid[coefficients[0], coefficients[3]] = f

    ok, not_found = 0, 0

    for root, dirs, files in os.walk(output):
        for f in files:
            if not f.endswith('.tif'):
                continue
            path = os.path.join(root, f)
            dataset = gdal.OpenEx(path, gdal.OF_READONLY | gdal.OF_RASTER | gdal.OF_SHARED | gdal.OF_VERBOSE_ERROR)
            coefficients = dataset.GetGeoTransform()
            corner = (coefficients[0], coefficients[3])

            if corner in reference_grid:
                matched_name = os.path.join(root, reference_grid[corner])
                os.rename(path, matched_name)
                print('Renamed', path, '->', matched_name)
                ok += 1
            else:
                print('No tile corresponding to', path, 'found.')
                not_found += 1

    print('Matched', ok, 'tile(s),', not_found, 'unmatched.')

parser = argparse.ArgumentParser(description='Renames tiles in one dataset to match a reference mosaic.')
parser.add_argument('-r', '--reference', help='Reference mosaic.', required=True)
parser.add_argument('-d', '--dataset', help='Dataset to be renamed to match the reference mosaic', required=True)

opts = parser.parse_args()

match_names(opts.reference, opts.dataset)
