#!/usr/bin/env python
# Copyright 2022 Adrien Vergé
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import collections
import glob
import multiprocessing
import os
import re
import subprocess
import tempfile
import zlib


# I found empirically that 8 is too low (too many false positives), but 16
# seems good.
THUMBNAIL_SIZE = 16

SSIM_THRESHOLD = 0.9


def checksum_of_thumbnail(file):
    with tempfile.NamedTemporaryFile(suffix='.png') as f:
        subprocess.check_call((
            'convert', '-auto-orient', file, '-resize',
            f'{THUMBNAIL_SIZE}x{THUMBNAIL_SIZE}^', '-type', 'bilevel',
            '-strip', f.name))

        return file, zlib.crc32(f.read())


def image_dimensions(file):
    res = subprocess.check_output(('identify', '-format', '%w %h', file))
    return res.decode().split(' ')


def image_is_rotated(file):
    orientation = subprocess.check_output(
        ('identify', '-format', '%[EXIF:orientation]', file),
        stderr=subprocess.DEVNULL)
    orientation = int(orientation or '1')
    return orientation in (6, 8)  # 6: 90°, 8: 270°


def compute_SSIM(file1, file2):
    w1, h1 = image_dimensions(file1)
    w2, h2 = image_dimensions(file2)
    w1, h1 = (h1, w1) if image_is_rotated(file1) else (w1, h1)
    w2, h2 = (h2, w2) if image_is_rotated(file2) else (w2, h2)

    if w1 > w2:
        file1, file2 = file2, file1
        w1, h1, w2, h2 = w2, h2, w1, h1

    with tempfile.NamedTemporaryFile(suffix='.jpg') as f:
        subprocess.check_call((
            'convert', '-auto-orient', file2, '-resize', f'{w1}x{h1}!',
            '-strip', f.name))

        out = subprocess.run(
            ('ffmpeg', '-i', file1, '-i', f.name, '-lavfi', 'ssim', '-f',
             'null', '-'), stderr=subprocess.PIPE).stderr
        res = [l for l in out.splitlines() if b' SSIM ' in l and b'All:' in l]
        assert len(res) == 1, f'failed to parse ffmpeg output: {out}'
        ssim = float(re.search(r' All:(0\.[0-9]+) ', res[0].decode()).group(1))

        return file1, file2, ssim


def main():
    parser = argparse.ArgumentParser(
        description='Find visually similar images in a list of paths.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('path', nargs='+',
                        help='list of images or directories')
    args = parser.parse_args()

    full_paths = args.path
    files = set()
    for path in full_paths:
        if os.path.isfile(path):
            _, ext = os.path.splitext(path)
            if ext.lower() in ('.jpg', '.jpeg'):
                files.add(path)
        else:
            full_paths += glob.glob(path + '/*')

    print(f'Found {len(files)} JPEG files to check')

    print('Computing visually-tolerant checksums of images…')
    outputs = multiprocessing.Pool().map(checksum_of_thumbnail, files)
    checksums = [i[1] for i in outputs]
    redundant = [i for i, n in collections.Counter(checksums).items() if n > 1]
    duplicates = [[i[0] for i in outputs if i[1] == s] for s in redundant]
    n = len(set.union(set(), *(set(list) for list in duplicates)))
    print(f'Found {n} potentially identical images')

    pairs = []
    for matches in duplicates:
        for i in range(len(matches)):
            for j in range(i + 1, len(matches)):
                pairs.append((matches[i], matches[j]))

    print('Computing structural similarity of pairs of images…')
    outputs = multiprocessing.Pool().starmap(compute_SSIM, pairs)

    for file1, file2, ssim in outputs:
        if ssim >= SSIM_THRESHOLD:
            print(f'\nImages are potentially the same (SSIM = {ssim}):')
            size1 = '×'.join(image_dimensions(file1))
            size2 = '×'.join(image_dimensions(file2))
            print(f'    {size1: <13}  {file1}')
            print(f'    {size2: <13}  {file2}')


if __name__ == '__main__':
    main()
