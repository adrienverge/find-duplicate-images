find-duplicate-images
=====================

This is a Python script to search similar images in a list of files or
directories. Duplicated images are found whatever their dimensions (e.g. if one
of them was saved as a thumbnail) and with some tolerance (e.g. if files were
slightly altered by saving them to lossy JPEG).

Installation
------------

Just run the script with ``./find-duplicate-images.py``.

It needs 2 dependencies: ImageMagick and FFmpeg. For example on Fedora:
``sudo dnf install ImageMagick ffmpeg``.

Examples
--------

.. code:: shell

 $ ./find-duplicate-images.py /sdcard /disk
 Found 53 JPEG files to check
 Computing visually-tolerant checksums of images…
 Found 12 potentially identical images
 Computing structural similarity of pairs of images…

 Images are potentially the same (SSIM = 0.936682):
     1599×899       /sdcard/IMG-20220827-WA0004.jpg
     3840×2160      /disk/photos/IMG_20220827_164950.JPG

 Images are potentially the same (SSIM = 0.933328):
     1599×899       /sdcard/IMG-20220827-WA0002.jpg
     3840×2160      /disk/photos/IMG_20220827_164936.JPG

 Images are potentially the same (SSIM = 0.917179):
     3840×2160      /disk/photos/IMG_20220829_135823.JPG
     899×1599       /sdcard/IMG-20220829-WA0006.jpg

 Images are potentially the same (SSIM = 0.963341):
     1599×899       /sdcard/IMG-20220829-WA0004.jpg
     3840×2160      /disk/photos/IMG_20220828_104638.JPG

 Images are potentially the same (SSIM = 0.947052):
     3840×2160      /disk/photos/IMG_20220828_222329.JPG
     899×1599       /sdcard/IMG-20220829-WA0007.jpg

 Images are potentially the same (SSIM = 0.934125):
     1599×899       /sdcard/IMG-20220827-WA0003.jpg
     3840×2160      /disk/photos/IMG_20220827_165006.JPG

.. code:: shell

 $ ./find-duplicate-images.py --manual-validation /sdcard /disk
 Images are potentially the same (SSIM = 0.955253):
 # Here a window shows to 2 images side by side
 Are these the same images? [y/n] y
 You confirmed that images ARE the same:
     1599×899       /sdcard/IMG-20220813-WA0012.jpg
     3840×2160      /disk/photos/IMG_20220813_141753.JPG

License
-------

`GPL version 3 <LICENSE>`_
