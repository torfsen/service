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
Tests for the ``service`` module.
"""

import threading
import time

from nose.tools import ok_ as ok, raises
import psutil

from service import Service


_NAME = 'python-service-test-daemon'


def is_running():
    """
    Check if the test daemon is running.
    """
    for process in psutil.process_iter():
        if process.name() == _NAME:
            return True
    return False


def assert_running():
    """
    Assert that the test daemon is running.
    """
    ok(is_running(), 'Process is not running.')


def assert_not_running():
    """
    Assert that the test daemon is not running.
    """
    ok(not is_running(), 'Process is running.')


class BasicService(Service):
    """
    Service base class.

    Sets the service name and uses a temporary directory for PID files
    to avoid the necessity of root privileges.
    """
    def __init__(self):
        super(BasicService, self).__init__(_NAME, pid_dir='/tmp')


class TimedService(BasicService):
    """
    Test service that runs for a certain amount of time.
    """
    def __init__(self, run=0, on_stop=0):
        super(TimedService, self).__init__()
        self.run_duration = run
        self.on_stop_duration = on_stop

    def run(self):
        time.sleep(self.run_duration)

    def on_stop(self):
        time.sleep(self.on_stop_duration)


class WaitingService(BasicService):
    """
    Test service that waits until shutdown via SIGTERM.
    """
    def __init__(self):
        super(WaitingService, self).__init__()
        self.event = threading.Event()

    def run(self):
        self.event.wait()

    def on_stop(self):
        self.event.set()


class ForeverService(BasicService):
    """
    A service that runs forever.
    """
    def run(self):
        while True:
            time.sleep(1)

    on_stop = run


def start(service):
    """
    Start a service and wait until it's running.
    """
    service.start()
    time.sleep(0.1)
    assert_running()
    return service


class TestService(object):
    """
    Tests for ``service.Service``.
    """

    def setup(self):
        service = BasicService()
        try:
            service.kill()
        except ValueError:
            pass

    teardown = setup

    def test_start(self):
        """
        Test ``Service.start``.
        """
        start(TimedService(0.2))

    def test_stop(self):
        """
        Test ``Service.stop``.
        """
        start(WaitingService()).stop()
        time.sleep(0.1)
        assert_not_running()

    def test_kill(self):
        """
        Test ``Service.kill``.
        """
        start(ForeverService()).kill()
        assert_not_running()

    def test_long_on_stop(self):
        """
        Test a long duration of ``on_stop``.
        """
        start(TimedService(0.2, 1)).stop()
        time.sleep(0.3)
        assert_running()

    def test_kill_removes_pid_file(self):
        """
        Test that ``kill`` removes the PID file.
        """
        start(ForeverService()).kill()
        start(ForeverService())

    @raises(ValueError)
    def test_stop_not_running(self):
        """
        Test stopping a service that is not running.
        """
        TimedService().stop()

    @raises(ValueError)
    def test_kill_not_running(self):
        """
        Test killing a service that is not running.
        """
        TimedService().kill()

    @raises(ValueError)
    def test_start_already_running(self):
        """
        Test starting a service that is already running.
        """
        start(TimedService(1)).start()

    def test_is_running(self):
        """
        Test ``Service.is_running``.
        """
        service = TimedService(1)
        ok(not service.is_running())
        start(service)
        ok(service.is_running())
