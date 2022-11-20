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
import json
import multiprocessing
import os
import re
import subprocess
import tempfile
import webbrowser
import zlib


# I found empirically that 8 is too low (too many false positives), but 16
# seems good.
THUMBNAIL_SIZE = 16

SSIM_THRESHOLD = 0.8


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
        if w1 == w2 and h1 == h2:
            second = file2
        else:
            subprocess.check_call((
                'convert', '-auto-orient', file2, '-resize', f'{w1}x{h1}!',
                '-strip', f.name))
            second = f.name

        out = subprocess.run(
            ('ffmpeg', '-nostdin', '-i', file1, '-i', second, '-lavfi', 'ssim',
             '-f', 'null', '-'), stderr=subprocess.PIPE).stderr
        res = [l for l in out.splitlines() if b' SSIM ' in l and b'All:' in l]
        assert len(res) == 1, f'failed to parse ffmpeg output: {out}'
        search = re.search(r' All:([01]\.[0-9]+) ', res[0].decode())
        assert search, f'failed to parse ffmpeg output: {res[0]}'
        ssim = float(search.group(1))

        return file1, file2, ssim


def ask_manual_comparison(file1, file2):
    with (tempfile.NamedTemporaryFile(suffix='.jpg') as f1,
            tempfile.NamedTemporaryFile(suffix='.jpg') as f2,
            tempfile.NamedTemporaryFile(suffix='.jpg') as f):
        subprocess.check_call((
            'convert', '-auto-orient', file1, '-resize', '360x360',
            '-background', 'white', '-gravity', 'center', '-extent', '400x400',
            f1.name))
        subprocess.check_call((
            'convert', '-auto-orient', file2, '-resize', '360x360',
            '-background', 'white', '-gravity', 'center', '-extent', '400x400',
            f2.name))
        subprocess.check_call(('convert', '+append', f1.name, f2.name, f.name))
        webbrowser.open(f.name)

        res = None
        while res not in ('y', 'n'):
            res = input('Are these the same images? [y/n] ')
        return res == 'y'


class Cache:
    def __init__(self):
        self.file = os.path.join(
            tempfile.gettempdir(),
            f'find-duplicate-images-{os.getuid()}-cache.json')
        self._load_from_disk()

    def _load_from_disk(self):
        try:
            with open(self.file, 'r') as f:
                contents = json.loads(f.read())
                self.checksums = contents.get('checksums', {})
                self.similarities = contents.get('similarities', {})
        except FileNotFoundError:
            self.checksums = {}
            self.similarities = {}

    def _save_to_disk(self):
        with open(self.file, 'w') as f:
            json.dump({'checksums': self.checksums,
                       'similarities': self.similarities}, f)

    def path_hash(self, file):
        return str(zlib.crc32(os.path.abspath(file).encode()))

    def get_checksum(self, file):
        return self.checksums.get(self.path_hash(file))

    def save_checksums(self, results):
        self._load_from_disk()
        new = {self.path_hash(file): checksum for file, checksum in results}
        self.checksums = self.checksums | new
        self._save_to_disk()

    def paths_hash(self, file1, file2):
        h1, h2 = self.path_hash(file1), self.path_hash(file2)
        h1, h2 = min(int(h1), int(h2)), max(int(h1), int(h2))
        return f'{h1} {h2}'

    def get_similarity(self, file1, file2):
        return self.similarities.get(self.paths_hash(file1, file2))

    def save_similarities(self, results):
        self._load_from_disk()
        new = {self.paths_hash(f1, f2): ssim for f1, f2, ssim in results}
        self.similarities = self.similarities | new
        self._save_to_disk()


def main():
    parser = argparse.ArgumentParser(
        description='Find visually similar images in a list of paths.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('path', nargs='+',
                        help='list of images or directories')
    parser.add_argument('--manual-validation', action='store_true',
                        help='show an image to manually confirm duplicates')
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

    cache = Cache()

    cached = [(f, cache.get_checksum(f)) for f in files]
    todo = [f for f, c in cached if c is None]
    cached_outputs = [(f, c) for f, c in cached if c is not None]
    print(f'Computing {len(todo)} visually-tolerant checksums of '
          f'images (found {len(cached_outputs)} in cache)…')
    outputs = multiprocessing.Pool().map(checksum_of_thumbnail, todo)
    cache.save_checksums(outputs)
    outputs = cached_outputs + outputs

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

    cached = [(*p, cache.get_similarity(*p)) for p in pairs]
    todo = [(f1, f2) for f1, f2, s in cached if s is None]
    cached_outputs = [(f1, f2, s) for f1, f2, s in cached if s is not None]
    print(f'Computing structural similarity of {len(todo)} pairs of images '
          f'(found {len(cached_outputs)} in cache)…')
    outputs = multiprocessing.Pool().starmap(compute_SSIM, todo)
    cache.save_similarities(outputs)
    outputs = cached_outputs + outputs

    for file1, file2, ssim in outputs:
        if ssim >= SSIM_THRESHOLD:
            print(f'\nImages are potentially the same (SSIM = {ssim}):')
            if args.manual_validation:
                if not ask_manual_comparison(file1, file2):
                    continue
                print('You confirmed that images ARE the same:')
            size1 = '×'.join(image_dimensions(file1))
            size2 = '×'.join(image_dimensions(file2))
            print(f'    {size1: <13}  {file1}')
            print(f'    {size2: <13}  {file2}')


if __name__ == '__main__':
    main()
