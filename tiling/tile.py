import argparse
import os
import numpy

from osgeo import gdal
from osgeo import osr

def tile_image(images, output_dir, tile_w, tile_h):
    print('Tiling', images)
    print('Writing to', output_dir)
    print('Generating {} x {} tiles'.format(tile_w, tile_h))

    datasets = []
    out_bands = []
    band_stats = []
    data_type = None
    width, height = 1, 1
    projection = None
    geotransform = None

    for img in images:
        dataset = gdal.OpenEx(img, gdal.OF_READONLY | gdal.OF_RASTER | gdal.OF_SHARED | gdal.OF_VERBOSE_ERROR)
        n_bands = dataset.RasterCount
        dataset_projection = dataset.GetProjection()

        if projection is None:
            projection = dataset_projection
        else:
            assert projection == dataset_projection,\
                'Merging bands with different projections: {} vs {}'.format(projection, dataset_projection)

        print(img, 'has', n_bands, 'band(s).')

        for i in range(1, n_bands + 1):
            band = dataset.GetRasterBand(i)
            band_stats.append(band.GetStatistics(False, True))

            if data_type is None:
                data_type = band.DataType
            else:
                assert data_type == band.DataType, 'Merging bands with different data types'

            if width < band.XSize:
                assert band.XSize % width == 0,\
                    'Incompatible band width: {} vs {}'.format(band.XSize, width)
                assert band.YSize % height == 0,\
                    'Incompatible band height: {} vs {}'.format(band.YSize, height)
                width, height = band.XSize, band.YSize

                # TODO: we should assert that all bands cover exactly the same area by using their
                # geotransform coefficients. In particular, coefficients 0 and 3 should be equal,
                # c[0] + band_width*c[1] + band_height*c[2] should be equal, and so should be
                # c[3] + band_width*c[4] + band_height*c[5].
                geotransform = dataset.GetGeoTransform()
            else:
                assert width % band.XSize == 0,\
                    'Incompatible band width: {} vs {}'.format(band.XSize, width)
                assert height % band.YSize == 0,\
                    'Incompatible band height: {} vs {}'.format(band.YSize, height)

            out_bands.append(band.ReadAsArray())

    os.makedirs(output_dir, exist_ok=True)

    # Make all bands the same size (width x height) and data type (0-255)
    for i, band in enumerate(out_bands):
        out_bands[i] = (band
                        .repeat(height // band.shape[0], axis = 0)
                        .repeat(width // band.shape[1], axis = 1))

    for i in range(height // tile_h):
        for j in range(width // tile_w):
            tile_name = 'T_{:02}_{:02}.tif'.format(i, j)
            path = os.path.join(output_dir, tile_name)
            print('Creating {}'.format(path))

            tile = gdal.GetDriverByName('GTiff').Create(path, tile_h, tile_w,
                                                        len(out_bands), data_type)
            tile.SetProjection(projection)

            # For reference, check the documentation of GDALDataset::GetGeoTransform:
            # https://www.gdal.org/classGDALDataset.html#a5101119705f5fa2bc1344ab26f66fd1d
            tile.SetGeoTransform([
                geotransform[0] + j * tile_w * geotransform[1] + i * tile_h * geotransform[2],
                geotransform[1],
                geotransform[2],
                geotransform[3] + j * tile_w * geotransform[4] + i * tile_h * geotransform[5],
                geotransform[4],
                geotransform[5]
            ])

            for band, data in enumerate(out_bands):
                tile_data = data[i*tile_h : (i+1)*tile_h, j*tile_w : (j+1)*tile_w]
                tile_band = tile.GetRasterBand(band + 1)
                tile_band.WriteArray(tile_data)
                tile_band.SetStatistics(*band_stats[band])

            tile.FlushCache()

    print('Done!')

parser = argparse.ArgumentParser(description='Tiles a large input image and combines various bands')

parser.add_argument('-o', '--output-dir', help='Output directory where tiles will be written.',
                  required=True)
parser.add_argument('I', metavar='Image', nargs='+', help='Input GeoTIFF images to be tiled.')
parser.add_argument('-W', '--tile-width', help='Width of each of the output tiles',
                    type=int, default=256)
parser.add_argument('-H', '--tile-height', help='Height of each output tile',
                    type=int, default=256)

opts = parser.parse_args()

tile_image(opts.I, opts.output_dir, opts.tile_width, opts.tile_height)
