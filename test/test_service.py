#!/usr/bin/env python

"""
Tests for the ``service`` module.
"""

import threading
import time

from nose.tools import ok_ as ok
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
    def __init__(self, run=0, on_terminate=0):
        super(TimedService, self).__init__()
        self.run_duration = run
        self.on_terminate_duration = on_terminate

    def run(self):
        time.sleep(self.run_duration)

    def on_terminate(self):
        time.sleep(self.on_terminate_duration)


class WaitingService(BasicService):
    """
    Test service that waits until shutdown via SIGTERM.
    """
    def __init__(self):
        super(WaitingService, self).__init__()
        self.event = threading.Event()

    def run(self):
        self.event.wait()

    def on_terminate(self):
        self.event.set()


class ForeverService(BasicService):
    """
    A service that runs forever.
    """
    def run(self):
        while True:
            time.sleep(1)

    on_terminate = run


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
        Test ``service.kill``.
        """
        start(ForeverService()).kill()
        assert_not_running()

    def test_long_on_terminate(self):
        """
        Test a long duration of ``on_terminate``.
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

