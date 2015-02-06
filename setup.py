#!/usr/bin/env python

# Copyright (c) 2014, 2015 Florian Brucker
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import codecs
import os.path
import pydoc
import re
import sys

from setuptools import find_packages, setup

HERE = os.path.dirname(__file__)
SOURCE_FILE = os.path.join(HERE, 'src', 'service', '__init__.py')

version = None
in_doc_str = False
doc_lines = []
with codecs.open(SOURCE_FILE, encoding='utf8') as f:
    for line in f:
        s = line.strip()
        m = re.match(r"""__version__\s*=\s*['"](.*)['"]""", line)
        if m:
            version = m.groups()[0]
        elif s in ['"""', "'''"]:
            if in_doc_str:
                in_doc_str = False
            elif not doc_lines:
                in_doc_str = True
        elif in_doc_str:
            doc_lines.append(line)

if not version:
    raise RuntimeError('Could not extract version from "%s".' % SOURCE_FILE)
if not doc_lines:
    raise RuntimeError('Could not extract doc string from "%s".' % SOURCE_FILE)

description = doc_lines[0].strip()
long_description = ''.join(doc_lines[1:]).strip()

print "*" * 40
print "Version = %s" % version
print ""
print "Description = ",
print description
print ""
print "Long description = ",
print long_description
print "*" * 40

setup(
    name='service',
    description=description,
    long_description=long_description,
    url='https://github.com/torfuspolymorphus/service',
    version=version,
    license='MIT',
    keywords='service daemon'.split(),
    classifiers=[
        # Reference: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 2.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],

    author='Florian Brucker',
    author_email='mail@florianbrucker.de',

    packages=find_packages('src'),
    package_dir={'': 'src'},
    install_requires='python-daemon lockfile setproctitle'.split(),
)
