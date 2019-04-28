#!/usr/bin/env python

# Copyright (c) 2014-2019 Florian Brucker (www.florianbrucker.de)
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

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import errno
import io
import json
import logging
import os
import os.path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

try:
    import unittest.mock as mock
except ImportError:
    import mock

from nose.tools import eq_ as eq, ok_ as ok, raises
import psutil

import service

from .helpers import get_current_case


NAME = 'python-service-test-daemon'

LOG_FILE = os.path.join(os.path.dirname(__file__),
                        'test-%d.%d.log' % sys.version_info[:2])
try:
    os.unlink(LOG_FILE)
except OSError as e:
    if e.errno != errno.ENOENT:
        raise

PID_DIR = '/tmp'

DELAY = 5

# Timeout for waiting for a service to start/stop. Rather high because
# on Travis services sometimes take ages to start.
TIMEOUT = 20

TEMP_DIR = tempfile.mkdtemp()


def teardown():
    shutil.rmtree(TEMP_DIR, ignore_errors=True)


def _is_test_deamon_process(process):
    """
    Test if a process is the started daemon process

    On MacOS X "Mojave" (and propably some other versions), setproctitle only
    changes the set command line argument, but not the process title itself.
    """
    if process.name() == NAME:
        return True
    elif process.name().lower().startswith("python"):
        # MacOS X "Mojave" (and propably some other versions):
        # Accessing the command line arguments of the process will fail
        # drastically (segfaults) on some circumstances / processes, therefore
        # it is first checked, if the process is a python process
        cmd_line = process.cmdline()
        return cmd_line and cmd_line[0] == NAME
    else:
        return False


def get_processes():
    """
    Return a list of all processes of the test service.
    """
    return [p for p in psutil.process_iter() if _is_test_deamon_process(p)]


def kill_processes():
    """
    Kill all test service processes and remove the PID file.
    """
    for process in get_processes():
        process.kill()
    try:
        os.remove(os.path.join(PID_DIR, NAME + '.pid'))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def is_running():
    """
    Check if the test daemon is running.
    """
    return bool(get_processes())


def pid_file_exists():
    """
    Check if the daemon's PID file exists.
    """
    return os.path.isfile(os.path.join(PID_DIR, NAME + '.pid'))


def assert_running():
    """
    Assert that the test daemon is running.
    """
    ok(is_running(), 'Process is not running but should.')
    ok(pid_file_exists(), "PID file doesn't exist but should.")


def assert_not_running():
    """
    Assert that the test daemon is not running.
    """
    ok(not is_running(), "Process is running but shouldn't.")
    ok(not pid_file_exists(), "PID file exists but shouldn't.")


class BasicService(service.Service):
    """
    Service base class.

    Sets the service name and uses a temporary directory for PID files
    to avoid the necessity of root privileges.
    """
    def __init__(self, signals=None):
        super(BasicService, self).__init__(
            NAME,
            pid_dir=PID_DIR,
            signals=signals
        )
        formatter = logging.Formatter('%(created)f: %(message)s')
        handler = logging.FileHandler(LOG_FILE)
        handler.setFormatter(formatter)
        self.logger.handlers[:] = [handler]
        self.logger.setLevel(service.SERVICE_DEBUG)
        dump_file = tempfile.NamedTemporaryFile(
            dir=TEMP_DIR,
            delete=False,
        )
        dump_file.close()
        self.dump_filename = dump_file.name

    def start(self, block=False):
        value = super(BasicService, self).start(block=block)
        self._debug('start(block={}) returns {}'.format(block, value))
        return value

    def stop(self, block=False):
        value = super(BasicService, self).stop(block=block)
        self._debug('stop(block={}) returns {}'.format(block, value))
        return value

    def load_dump(self):
        """
        Load previously dumped data.
        """
        with io.open(self.dump_filename, encoding='utf-8') as f:
            try:
                return json.load(f)
            except ValueError:
                return {}

    def assert_dump(self, **kwargs):
        """
        Assert that the dumped data matches the expectations.
        """
        data = self.load_dump()
        eq(data, kwargs)

    def dump(self, key, value):
        """
        Dump data.
        """
        self._debug('dumping {} = {}'.format(key, value))
        data = self.load_dump()
        data[key] = value
        with open(self.dump_filename, 'w') as f:
            json.dump(data, f)


class WaitingService(BasicService):
    """
    Test service that waits until shutdown via SIGTERM.
    """
    def run(self):
        self.logger.info('start')
        self.wait_for_sigterm()
        self.logger.info('end')


class ForeverService(BasicService):
    """
    A service that runs forever.
    """
    def run(self):
        self.logger.info('start')
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
    A service that calls a callback in ``run``.
    """
    def __init__(self, run=None, *args, **kwargs):
        super(CallbackService, self).__init__(*args, **kwargs)
        self._run_callback = run

    def run(self):
        self.logger.info('start')
        if self._run_callback:
            self._run_callback(self)
        self.logger.info('end')


def start(service):
    """
    Start a service and wait until it's running.
    """
    ok(service.start(block=TIMEOUT), 'Service failed to start')
    assert_running()
    return service


class TestService(object):
    """
    Tests for ``service.Service``.
    """
    def setup(self):
        with open(LOG_FILE, 'a') as f:
            f.write('\n\n{}\n'.format(get_current_case()))
        kill_processes()

    def teardown(self):
        kill_processes()

    def test_start(self):
        """
        Test ``Service.start``.
        """
        start(WaitingService())

    def test_start_timeout_ok(self):
        """
        Test ``Service.start`` with a timeout.
        """
        ok(WaitingService().start(block=TIMEOUT))

    def test_start_timeout_fail(self):
        """
        Test ``Service.start`` with a timeout and a failing daemon.
        """
        ok(not FailingService().start(block=0.1))

    def test_stop(self):
        """
        Test ``Service.stop``.
        """
        start(WaitingService()).stop()
        time.sleep(DELAY)
        assert_not_running()

    def test_stop_timeout_ok(self):
        """
        Test ``Service.stop`` with a timeout.
        """
        ok(start(WaitingService()).stop(block=TIMEOUT))

    def test_stop_timeout_fail(self):
        """
        Test ``Service.stop`` with a timeout and stuck daemon.
        """
        ok(not start(ForeverService()).stop(block=0.1))

    def test_kill(self):
        """
        Test ``Service.kill``.
        """
        start(ForeverService()).kill()
        time.sleep(DELAY)
        assert_not_running()

    def test_kill_timeout_ok(self):
        """
        Test ``Service.kill`` with a timeout.
        """
        ok(start(ForeverService()).kill(block=TIMEOUT))
        assert_not_running()

    def test_kill_timeout_fail(self):
        """
        Test ``Service.kill`` with too short a timeout.
        """
        os_kill = os.kill

        def kill_mock(pid, sig):
            if sig != signal.SIGKILL:
                return os_kill(pid, sig)

        with mock.patch('os.kill', side_effect=kill_mock):
            ok(not start(ForeverService()).kill(block=0.1))

    @raises(ValueError)
    def test_stop_not_running(self):
        """
        Test stopping a service that is not running.
        """
        WaitingService().stop()

    @raises(ValueError)
    def test_kill_not_running(self):
        """
        Test killing a service that is not running.
        """
        WaitingService().kill()

    @raises(ValueError)
    def test_start_already_running(self):
        """
        Test starting a service that is already running.
        """
        start(WaitingService()).start()

    def test_is_running(self):
        """
        Test ``Service.is_running``.
        """
        service = WaitingService()
        ok(not service.is_running())
        start(service)
        ok(service.is_running())

    @raises(IOError)
    def test_no_lock_permissions(self):
        """
        Test starting a service without necessary permissions.
        """
        service.Service(NAME).start()

    def test_exception_in_run(self):
        """
        Test that exceptions in ``run`` are handled correctly.
        """
        log_file = tempfile.NamedTemporaryFile(dir=TEMP_DIR, delete=False)
        log_file.close()

        def run(service):
            time.sleep(DELAY)
            service.logger.addHandler(logging.FileHandler(log_file.name))
            raise Exception('FOOBAR')

        start(CallbackService(run))
        time.sleep(2 * DELAY)
        assert_not_running()
        ok(not pid_file_exists())
        with open(log_file.name) as f:
            ok('FOOBAR' in f.read())

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
        try:
            service.stop(block=TIMEOUT)
            ok(os.path.isfile(service.f.name))
            with open(service.f.name, 'r') as f:
                eq(f.read(), 'foobar')
        finally:
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
        try:
            service.stop(block=TIMEOUT)
            ok(os.path.isfile(service.f.name))
            with open(service.f.name, 'r') as f:
                ok('foobar' in f.read())
        finally:
            os.unlink(service.f.name)

    def test_sys_exit(self):
        """
        Test that sys.exit is handled correctly.
        """
        def run(service):
            time.sleep(DELAY)
            import sys
            sys.exit()

        start(CallbackService(run))
        time.sleep(2 * DELAY)
        # Check that the PID file has been removed correctly
        assert_not_running()

    def test_parent_does_not_remove_pid_file(self):
        """
        Test that the parent does not remote the PID file unintentionally.
        """
        # This could happen with older versions of the ``pid`` module,
        # which installed an ``atexit`` handler that automatically removed
        # the PID file. That mechanism could be triggered from within the
        # parent process under certain circumstances. See
        # https://github.com/torfsen/service/issues/10
        subprocess.check_call(['python', '-m', 'test.start_waiting_service'])
        ok(os.path.exists(WaitingService().pid_file._path),
           'PID file does not exist')

    def test_signals(self):
        """
        Test signal routines.
        """
        def run(service):
            service.dump('got_signal1', service.got_signal(signal.SIGHUP))
            service.wait_for_signal(signal.SIGHUP)
            service.dump('got_signal2', service.got_signal(signal.SIGHUP))
            service.clear_signal(signal.SIGHUP)
            service.dump('got_signal3', service.got_signal(signal.SIGHUP))

        service = start(CallbackService(run, signals=[signal.SIGHUP]))
        time.sleep(DELAY)
        service.send_signal(signal.SIGHUP)
        time.sleep(DELAY)
        service.assert_dump(
            got_signal1=False,
            got_signal2=True,
            got_signal3=False,
        )

    @raises(ValueError)
    def test_send_signal_not_enabled(self):
        """
        Test sending a signal that hasn't been enabled.
        """
        start(WaitingService()).send_signal(signal.SIGHUP)

    def test_use_signal_not_enabled(self):
        """
        Test using a signal that hasn't been enabled.
        """
        method_names = [
            'clear_signal',
            'got_signal',
            'wait_for_signal',
        ]

        def run(service):
            time.sleep(DELAY)
            for method_name in method_names:
                method = getattr(service, method_name)
                try:
                    method(signal.SIGHUP)
                except ValueError:
                    service.dump(method_name, True)

        service = start(CallbackService(run))
        time.sleep(2 * DELAY)
        service.assert_dump(**{name: True for name in method_names})

