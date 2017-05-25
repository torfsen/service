#!/usr/bin/env python
# encoding: utf-8

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import inspect


def get_current_case():
    '''
    Get information about the currently running test case.

    Returns the fully qualified name of the current test function
    when called from within a test method, test function, setup or
    teardown.

    Raises ``RuntimeError`` if the current test case could not be
    determined.

    Tested on Python 2.7 and 3.3 - 3.6 with nose 1.3.7.
    '''
    for frame_info in inspect.stack():
        if frame_info[1].endswith('unittest/case.py'):
            return frame_info[0].f_locals['self'].id()
    raise RuntimeError('Could not determine test case')

