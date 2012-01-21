#!/bin/env python

import os
from distutils.core import setup

name = 'sphinx-haystack'
version = '0.1beta'
release = '1'
versrel = version + '-' + release
download_url = 'https://github.com/downloads/btimby/' + name + \
                           '/' + name + '-' + versrel + '.tar.gz'

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = 'sphinx-haystack',
    version = versrel,
    description = "A Sphinx backend for Haystack",
    long_description = read('README.md'),
    classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Topic :: Internet :: WWW/HTTP :: Indexing/Search',
        'Framework :: Django',
    ],
    author = 'Ben Timby',
    author_email = 'btimby@gmail.com',
    url = 'http://github.com/btimby/haystack-sphinx/',
    download_url = download_url,
    license = 'GPLv3',
    py_modules = ['sphinx_backend'],
)