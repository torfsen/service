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

"""
Tests for the ``service`` module.
"""

import errno
import logging
import os
import os.path
import sys
import tempfile
import threading
import time

import lockfile
from nose.tools import eq_ as eq, ok_ as ok, raises
import psutil

import service


_NAME = 'python-service-test-daemon'


_LOG_FILE = os.path.join(os.path.dirname(__file__),
                         'test-%d.%d.log' % sys.version_info[:2])
try:
    os.unlink(_LOG_FILE)
except OSError as e:
    if e.errno != errno.ENOENT:
        raise


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


class BasicService(service.Service):
    """
    Service base class.

    Sets the service name and uses a temporary directory for PID files
    to avoid the necessity of root privileges.
    """
    def __init__(self):
        super(BasicService, self).__init__(_NAME, pid_dir='/tmp')
        handler = logging.FileHandler(_LOG_FILE)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)


class TimedService(BasicService):
    """
    Test service that runs for a certain amount of time.
    """
    def __init__(self, duration=0):
        super(TimedService, self).__init__()
        self.duration = duration

    def run(self):
        time.sleep(self.duration)


class WaitingService(BasicService):
    """
    Test service that waits until shutdown via SIGTERM.
    """
    def run(self):
        self.wait_for_sigterm()


class ForeverService(BasicService):
    """
    A service that runs forever.
    """
    def run(self):
        while True:
            time.sleep(1)


class OneTimeLock(object):
    """
    Pseudo-lock that can only be acquired once.

    See ``FailingService``.
    """
    def __init__(self, *args, **kwargs):
        self._acquired = False

    def acquire(self, *args, **kwargs):
        if self._acquired:
            raise RuntimeError('Oops')
        self._acquired = True

    def release(self, *args, **kwargs):
        pass

    def read_pid(self, *args, **kwargs):
        return None


class FailingService(BasicService):
    """
    A service that fails to start.

    This is a hack that works by using a PID lock file object which can
    only be acquired once. This is necessary to create a daemon that
    fails reliably before the daemon process exists.
    """
    def __init__(self, *args, **kwargs):
        super(FailingService, self).__init__(*args, **kwargs)
        self.pid_file = OneTimeLock()


class CallbackService(BasicService):
    """
    A service that calls callbacks in ``run`` and ``on_stop``.
    """
    def __init__(self, run=None, on_stop=None, *args, **kwargs):
        super(CallbackService, self).__init__(*args, **kwargs)
        self._run_callback = run
        self._on_stop_callback = on_stop

    def run(self):
        if self._run_callback:
            self._run_callback(self)

    def on_stop(self):
        if self._on_stop_callback:
            self._on_stop_callback(self)


def start(service):
    """
    Start a service and wait until it's running.
    """
    service.start()
    time.sleep(0.5)
    assert_running()
    return service


class TestService(object):
    """
    Tests for ``service.Service``.
    """
    def get_log(self):
        with open(self.logfile.name) as f:
            return f.read()

    def assert_log_contains(self, text, msg=None):
        if not msg:
            msg = 'Log does not contain "%s":\n\n%s' % (text, self.get_log())
        ok(text in self.get_log(), msg)

    def setup(self):
        service = BasicService()
        try:
            service.kill()
        except ValueError:
            pass
        self.logfile = tempfile.NamedTemporaryFile(delete=False)
        self.logfile.close()
        self.handler = logging.FileHandler(self.logfile.name)

    def teardown(self):
        service = BasicService()
        try:
            service.kill()
        except ValueError:
            pass
        try:
            os.unlink(self.logfile.name)
        except OSError:
            pass

    def test_start(self):
        """
        Test ``Service.start``.
        """
        start(TimedService(1))

    def test_start_timeout_ok(self):
        """
        Test ``Service.start`` with a timeout.
        """
        ok(TimedService(1).start(block=1))

    def test_start_timeout_fail(self):
        """
        Test ``Service.start`` with a timeout and a failing daemon.
        """
        ok(not FailingService().start(block=1))

    def test_stop(self):
        """
        Test ``Service.stop``.
        """
        start(WaitingService()).stop()
        time.sleep(1)
        assert_not_running()

    def test_stop_timeout_ok(self):
        """
        Test ``Service.stop`` with a timeout.
        """
        ok(start(WaitingService()).stop(block=1))

    def test_stop_timeout_fail(self):
        """
        Test ``Service.stop`` with a timeout and stuck daemon.
        """
        ok(not start(ForeverService()).stop(block=1))

    def test_kill(self):
        """
        Test ``Service.kill``.
        """
        start(ForeverService()).kill()
        time.sleep(1)
        assert_not_running()

    def test_kill_removes_pid_file(self):
        """
        Test that ``kill`` removes the PID file.
        """
        start(ForeverService()).kill()
        time.sleep(1)
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

    @raises(lockfile.LockFailed)
    def test_no_lock_permissions(self):
        """
        Test starting a service without necessary permissions.
        """
        service.Service(_NAME).start()

    def test_log_exception_in_run(self):
        """
        Test exception logging for errors in ``run``.
        """
        def run(service):
            service.logger.addHandler(logging.FileHandler(self.logfile.name))
            raise Exception('FOOBAR')
        CallbackService(run).start()
        time.sleep(1)
        self.assert_log_contains('FOOBAR')

    def test_exception_in_run_removes_pid_file(self):
        """
        Test that the PID file is removed if there's an exception in ``run``.
        """
        def run(service):
            raise Exception('FOOBAR')
        CallbackService(run).start()
        time.sleep(1)
        start(ForeverService())

    def test_files_preserve(self):
        """
        Test file handle preservation.
        """
        class FileHandleService(BasicService):
            def __init__(self):
                super(FileHandleService, self).__init__()
                self.f = tempfile.NamedTemporaryFile(mode='wt', delete=False)
                self.files_preserve = [self.f]
            def run(self):
                self.f.write('foobar')
                self.f.close()
                self.wait_for_sigterm()

        service = FileHandleService()
        start(service)
        service.stop(block=1)
        ok(os.path.isfile(service.f.name))
        with open(service.f.name, 'r') as f:
            eq(f.read(), 'foobar')
        os.unlink(f.name)

    def test_builtin_log_handlers_file_handles_are_preserved(self):
        """
        Test that file handles of built-in log handlers are preserved.
        """
        class LoggingService(BasicService):
            def __init__(self):
                super(LoggingService, self).__init__()
                self.f = tempfile.NamedTemporaryFile(delete=False)
                self.f.close()
                self.logger.addHandler(logging.FileHandler(self.f.name))
            def run(self):
                self.logger.warn('foobar')
                self.wait_for_sigterm()

        service = LoggingService()
        start(service)
        service.stop(block=1)
        ok(os.path.isfile(service.f.name))
        with open(service.f.name, 'r') as f:
            ok('foobar' in f.read())
        os.unlink(f.name)

