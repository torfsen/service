#!/usr/bin/env python

# Copyright (c) 2014 Florian Brucker
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

"""
Test runner for ``service`` tests.
"""

import os.path
import sys

import nose


_ROOT_DIR = os.path.dirname(__file__)
_SRC_DIR = os.path.join(_ROOT_DIR, 'src')
sys.path.insert(0, _SRC_DIR)

_HTML_DIR = os.path.join(_ROOT_DIR, 'coverage')

args = [
        '--nocapture',  # Messing with STDIN and STDOUT causes problems
                        # with the ``daemon`` module.
        '--with-coverage',
        '--cover-branches',
        '--cover-erase',
        '--cover-package', 'service',
        '--cover-html',
        '--cover-html-dir', _HTML_DIR,
       ]
args = [sys.argv[0]] + args + sys.argv[1:]
nose.main(argv=args)
