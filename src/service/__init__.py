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
Easy implementation of Unix background services.

This module makes it easy to write Unix services, i.e. background
processes ("daemons") that are controlled by a foreground application
(e.g. a console script).

The package is built around the python-daemon_ module, which provides
the means for creating well-behaved daemon processes. The ``service``
package adds a control infrastructure for easily starting, stopping,
querying and killing the background process from a foreground
application.

.. _python-daemon: https://pypi.python.org/pypi/python-daemon
"""

import errno
import logging
from logging.handlers import SysLogHandler
import os
import signal
import socket
import sys
import threading
import time

from daemon import DaemonContext
import lockfile.pidlockfile
import setproctitle


__version__ = '0.1.1'

__all__ = ['Service']


def _detach_process():
    """
    Detach daemon process.

    Forks the current process into a parent and a detached child. The
    child process resides in its own process group, has no controlling
    terminal attached and is cleaned up by the init process.

    Returns ``True`` for the parent and ``False`` for the child.
    """
    # To detach from our process group we need to call ``setsid``. We
    # can only do that if we aren't a process group leader. Therefore
    # we fork once, which makes sure that the new child process is not
    # a process group leader.
    pid = os.fork()
    if pid > 0:
        # Parent process
        return True
    os.setsid()
    # We now fork a second time and let the second's fork parent exit.
    # This makes the second fork's child process an orphan. Orphans are
    # cleaned up by the init process, so we won't end up with a zombie.
    # In addition, the second fork's child is no longer a session
    # leader and can therefore never acquire a controlling terminal.
    pid = os.fork()
    if pid > 0:
        os._exit(os.EX_OK)
    return False


class _PIDFile(lockfile.pidlockfile.PIDLockFile):
    """
    A locked PID file.

    This is basically ``lockfile.pidlockfile.PIDLockfile``, with the
    small modification that the PID is obtained only when the lock is
    acquired. This makes sure that the PID in the PID file is always
    that of the process that actually acquired the lock (even if the
    instance was created in another process, for example before
    forking).
    """
    def __init__(self, *args, **kwargs):
        lockfile.pidlockfile.PIDLockFile.__init__(self, *args, **kwargs)
        self.pid = None

    def acquire(self, *args, **kwargs):
        self.pid = os.getpid()
        return lockfile.pidlockfile.PIDLockFile.acquire(self, *args, **kwargs)



class Service(object):
    """
    A background service.

    This class provides the basic framework for running and controlling
    a background daemon. This includes methods for starting the daemon
    (including things like proper setup of a detached deamon process),
    checking whether the daemon is running, asking the daemon to
    terminate and for killing the daemon should that become necessary.

    The class has a dual interface: Some of the methods are intended to
    be called from the controlling process while others run in the
    daemon process. The control methods are:

    * ``start`` to start the daemon
    * ``stop`` to ask the daemon to stop
    * ``kill`` to kill the daemon
    * ``is_running`` to check whether the daemon is running
    * ``get_pid`` to get the daemon's process ID

    Subclasses usually do not need to override any of these.

    The daemon methods are ``run`` and ``on_stop``. Subclasses should
    at least override the ``run`` method to provide the major daemon
    functionality. You may also want to provide a custom implementation
    of ``on_stop`` which is called when the daemon receives a SIGTERM
    signal (for example after ``stop`` was called).

    The daemon can use its ``logger`` attribute to log messages to
    syslog. Uncaught exceptions that occur while the daemon is running
    are automatically logged that way.
    """

    def __init__(self, name, pid_dir='/var/run'):
        """
        Constructor.

        ``name`` is a string that identifies the daemon. The name is
        used for the name of the daemon process, the PID file and for
        the messages to syslog.

        ``pid_dir`` is the directory in which the PID file is stored.
        """
        self.name = name
        self.pid_file = _PIDFile(os.path.join(pid_dir, name + '.pid'))

        self.logger = logging.getLogger(name)
        # When a service with the same name is created multiple times
        # during the same run of the host program then ``getLogger``
        # always returns the same instance. We therefore only add a
        # handler if the logger doesn't already have one.
        for handler in self.logger.handlers:
            if isinstance(handler, SysLogHandler):
                self._handler = handler
                break
        else:
            self._handler = SysLogHandler(address='/dev/log',
                                          facility=SysLogHandler.LOG_DAEMON)
            format_str = '%(name)s: <%(levelname)s> %(message)s'
            self._handler.setFormatter(logging.Formatter(format_str))
            self.logger.addHandler(self._handler)
        self.logger.setLevel(logging.DEBUG)

    def is_running(self):
        """
        Check if the daemon is running.
        """
        return self.get_pid() is not None

    def get_pid(self):
        """
        Get PID of daemon process or ``None`` if daemon is not running.
        """
        return self.pid_file.read_pid()

    def stop(self):
        """
        Tell the daemon process to stop.

        Sends the SIGTERM signal to the daemon process, requesting it
        to terminate. A
        """
        pid = self.get_pid()
        if not pid:
            raise ValueError('Daemon is not running.')
        os.kill(pid, signal.SIGTERM)

    def kill(self):
        """
        Kill the daemon process.

        Sends the SIGKILL signal to the daemon process, killing it. You
        probably want to try ``stop`` first.

        After the process is killed its PID file is removed.
        """
        pid = self.get_pid()
        if not pid:
            raise ValueError('Daemon is not running.')
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as e:
            if e.errno == errno.ESRCH:
                raise ValueError('Daemon is not running.')
        finally:
            self.pid_file.break_lock()

    def start(self):
        """
        Start the daemon process.

        The daemon process is started in the background and the calling
        process returns.

        Once the daemon process is initialized it calls the ``run``
        method.
        """
        pid = self.get_pid()
        if pid:
            raise ValueError('Daemon is already running at PID %d.' % pid)

        # The default is to place the PID file into ``/var/run``. This
        # requires root privileges. Since not having these is a common
        # problem we check a priori whether we can create the lock file.
        try:
            self.pid_file.acquire(timeout=0)
        finally:
            try:
                self.pid_file.release()
            except lockfile.NotLocked:
                pass

        if _detach_process():
            # Calling process returns
            return
        # Daemon process continues here

        setproctitle.setproctitle(self.name)

        def delegator(target):
            try:
                target()
            except Exception as e:
                self.logger.exception(e)
            try:
                self.pid_file.release()
            except Exception as e:
                self.logger.exception(e)
            os._exit(os.EX_OK)

        terminator = lambda signum, frame: delegator(self.on_stop)
        runner = lambda: delegator(self.run)

        try:
            self.pid_file.acquire(timeout=0)
            with DaemonContext(
                    detach_process=False,
                    signal_map={
                        signal.SIGTTIN: None,
                        signal.SIGTTOU: None,
                        signal.SIGTSTP: None,
                        signal.SIGTERM: terminator,
                    },
                    files_preserve=[self._handler.socket.fileno()]):
                # Python's signal handling mechanism only forwards signals to
                # the main thread and only when that thread is doing something
                # (e.g. not when it's waiting for a lock, etc.). If we use the
                # main thread for the ``run`` method this means that we cannot
                # use the synchronization devices from ``threading`` for the
                # communication between ``run`` and ``on_stop``. Hence we use
                # a separate thread for ``run`` and make sure that the main
                # loop receives signals.
                thread = threading.Thread(target=runner)
                thread.start()
                while thread.is_alive():
                    time.sleep(1)
        except Exception as e:
            self.logger.exception(e)

        # We need to shutdown the daemon process at this point, because
        # otherwise it will continue executing from after the original
        # call to ``start``.
        os._exit(os.EX_OK)

    def run(self):
        """
        Main daemon method.

        This method is called once the daemon is initialized and
        running. Subclasses should override this method and provide the
        implementation of the daemon's functionality. The default
        implementation does nothing and immediately returns.

        Once this method returns the daemon process automatically exits.
        Typical implementations therefore contain some kind of loop.

        The daemon may also be terminated by sending it the SIGTERM
        signal. In that case ``on_stop`` will be called and should make
        the loop in ``run`` terminate.
        """
        pass

    def on_stop(self):
        """
        Called when daemon receives signal to terminate.

        This method is automatically called when the daemon receives
        the SIGTERM signal, telling it to terminate. The call is done
        via Python's signalling mechanisms, see the ``signal`` module
        for details. Most importantly, the call is asynchronous.

        A subclass's implementation should stop the daemon's work and
        perform the necessary cleanup. The actual shutdown of the
        daemon process is done automatically once this method exits.

        The default implementation does nothing and returns immediately.

        Note that this method is not automatically called when the
        daemon's ``run`` method exits.
        """
        pass

