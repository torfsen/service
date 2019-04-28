#!/usr/bin/env python

# Copyright (c) 2014-2018 Florian Brucker (www.florianbrucker.de)
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

import errno
import logging
from logging.handlers import SysLogHandler
import os
import os.path
import signal
import socket
import sys
import threading
import time

from daemon import DaemonContext
from pid import PidFile
import setproctitle


__version__ = '0.6.0'

__all__ = ['find_syslog', 'Service']


# Custom log level below logging.DEBUG for logging internal debug
# messages.
SERVICE_DEBUG = logging.DEBUG - 1


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
        # Use waitpid to "collect" the child process and avoid Zombies
        os.waitpid(pid, 0)
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


class _PIDFile(object):
    """
    A lock file that stores the PID of the owning process.

    The PID is stored when the lock is acquired, not when it is created.
    """
    def __init__(self, path):
        self._path = path
        self._lock = None

    def _make_lock(self):
        directory, filename = os.path.split(self._path)
        return PidFile(filename,
                       directory,
                       register_term_signal_handler=False,
                       register_atexit=False)

    def acquire(self):
        self._make_lock().create()

    def release(self):
        self._make_lock().close()
        try:
            os.remove(self._path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

    def read_pid(self):
        """
        Return the PID of the process owning the lock.

        Returns ``None`` if no lock is present.
        """
        try:
            with open(self._path, 'r') as f:
                s = f.read().strip()
                if not s:
                    return None
                return int(s)
        except IOError as e:
            if e.errno == errno.ENOENT:
                return None
            raise


def find_syslog():
    """
    Find Syslog.

    Returns Syslog's location on the current system in a form that can
    be passed on to :py:class:`logging.handlers.SysLogHandler`::

        handler = SysLogHandler(address=find_syslog(),
                                facility=SysLogHandler.LOG_DAEMON)
    """
    for path in ['/dev/log', '/var/run/syslog']:
        if os.path.exists(path):
            return path
    return ('127.0.0.1', 514)


def _block(predicate, timeout):
    """
    Block until a predicate becomes true.

    ``predicate`` is a function taking no arguments. The call to
    ``_block`` blocks until ``predicate`` returns a true value. This
    is done by polling ``predicate``.

    ``timeout`` is either ``True`` (block indefinitely) or a timeout
    in seconds.

    The return value is the value of the predicate after the
    timeout.
    """
    if timeout:
        if timeout is True:
            timeout = float('Inf')
        timeout = time.time() + timeout
        while not predicate() and time.time() < timeout:
            time.sleep(0.1)
    return predicate()


class Service(object):
    """
    A background service.

    This class provides the basic framework for running and controlling
    a background daemon. This includes methods for starting the daemon
    (including things like proper setup of a detached deamon process),
    checking whether the daemon is running, asking the daemon to
    terminate and for killing the daemon should that become necessary.

    .. py:attribute:: logger

        A :py:class:`logging.Logger` instance.

    .. py:attribute:: files_preserve

        A list of file handles that should be preserved by the daemon
        process. File handles of built-in Python logging handlers
        attached to :py:attr:`logger` are automatically preserved.
    """

    def __init__(self, name, pid_dir='/var/run', signals=None):
        """
        Constructor.

        ``name`` is a string that identifies the daemon. The name is
        used for the name of the daemon process, the PID file and for
        the messages to syslog.

        ``pid_dir`` is the directory in which the PID file is stored.

        ``signals`` list of operating signals, that should be available
        for use with :py:meth:`.send_signal`, :py:meth:`.got_signal`,
        :py:meth:`.wait_for_signal`, and :py:meth:`.check_signal`. Note
        that SIGTERM is always supported, and that SIGTTIN, SIGTTOU, and
        SIGTSTP are never supported.
        """
        self.name = name
        self.pid_file = _PIDFile(os.path.join(pid_dir, name + '.pid'))
        self._signal_events = {int(s): threading.Event()
                               for s in ((signals or []) + [signal.SIGTERM])}
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            self.logger.addHandler(logging.NullHandler())
        self.files_preserve = []

    def _debug(self, msg):
        """
        Log an internal debug message.

        Logs a debug message with the :py:data:SERVICE_DEBUG logging
        level.
        """
        self.logger.log(SERVICE_DEBUG, msg)

    def _get_logger_file_handles(self):
        """
        Find the file handles used by our logger's handlers.
        """
        handles = []
        for handler in self.logger.handlers:
            # The following code works for logging's SysLogHandler,
            # StreamHandler, SocketHandler, and their subclasses.
            for attr in ['sock', 'socket', 'stream']:
                try:
                    handle = getattr(handler, attr)
                    if handle:
                        handles.append(handle)
                    break
                except AttributeError:
                    continue
        return handles

    def is_running(self):
        """
        Check if the daemon is running.
        """
        pid = self.get_pid()
        if pid is None:
            return False
        # The PID file may still exist even if the daemon isn't running,
        # for example if it has crashed.
        try:
            os.kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:
                # In this case the PID file shouldn't have existed in
                # the first place, so we remove it
                self.pid_file.release()
                return False
            # We may also get an exception if we're not allowed to use
            # kill on the process, but that means that the process does
            # exist, which is all we care about here.
        return True

    def get_pid(self):
        """
        Get PID of daemon process or ``None`` if daemon is not running.
        """
        return self.pid_file.read_pid()

    def _get_signal_event(self, s):
        '''
        Get the event for a signal.

        Checks if the signal has been enabled and raises a
        ``ValueError`` if not.
        '''
        try:
            return self._signal_events[int(s)]
        except KeyError:
            raise ValueError('Signal {} has not been enabled'.format(s))

    def send_signal(self, s):
        """
        Send a signal to the daemon process.

        The signal must have been enabled using the ``signals``
        parameter of :py:meth:`Service.__init__`. Otherwise, a
        ``ValueError`` is raised.
        """
        self._get_signal_event(s)  # Check if signal has been enabled
        pid = self.get_pid()
        if not pid:
            raise ValueError('Daemon is not running.')
        os.kill(pid, s)

    def got_signal(self, s):
        """
        Check if a signal was received.

        The signal must have been enabled using the ``signals``
        parameter of :py:meth:`Service.__init__`. Otherwise, a
        ``ValueError`` is raised.

        Returns ``True`` if the daemon process has received the signal
        (for example because :py:meth:`stop` was called in case of
        SIGTERM, or because :py:meth:`send_signal` was used) and
        ``False`` otherwise.

        .. note::
            This function always returns ``False`` for enabled signals
            when it is not called from the daemon process.
        """
        return self._get_signal_event(s).is_set()

    def clear_signal(self, s):
        """
        Clears the state of a signal.

        The signal must have been enabled using the ``signals``
        parameter of :py:meth:`Service.__init__`. Otherwise, a
        ``ValueError`` is raised.
        """
        self._get_signal_event(s).clear()

    def wait_for_signal(self, s, timeout=None):
        """
        Wait until a signal has been received.

        The signal must have been enabled using the ``signals``
        parameter of :py:meth:`Service.__init__`. Otherwise, a
        ``ValueError`` is raised.

        This function blocks until the daemon process has received the
        signal (for example because :py:meth:`stop` was called in case
        of SIGTERM, or because :py:meth:`send_signal` was used).

        If ``timeout`` is given and not ``None`` it specifies a timeout
        for the block.

        The return value is ``True`` if the signal was received and
        ``False`` otherwise (the latter occurs if a timeout was given
        and the signal was not received).

        .. warning::
            This function blocks indefinitely (or until the given
            timeout) for enabled signals when it is not called from the
            daemon process.
        """
        return self._get_signal_event(s).wait(timeout)

    def got_sigterm(self):
        """
        Check if SIGTERM signal was received.

        Returns ``True`` if the daemon process has received the SIGTERM
        signal (for example because :py:meth:`stop` was called).

        .. note::
            This function always returns ``False`` when it is not called
            from the daemon process.
        """
        return self.got_signal(signal.SIGTERM)

    def wait_for_sigterm(self, timeout=None):
        """
        Wait until a SIGTERM signal has been received.

        This function blocks until the daemon process has received the
        SIGTERM signal (for example because :py:meth:`stop` was called).

        If ``timeout`` is given and not ``None`` it specifies a timeout
        for the block.

        The return value is ``True`` if SIGTERM was received and
        ``False`` otherwise (the latter only occurs if a timeout was
        given and the signal was not received).

        .. warning::
            This function blocks indefinitely (or until the given
            timeout) when it is not called from the daemon process.
        """
        return self.wait_for_signal(signal.SIGTERM, timeout)

    def stop(self, block=False):
        """
        Tell the daemon process to stop.

        Sends the SIGTERM signal to the daemon process, requesting it
        to terminate.

        If ``block`` is true then the call blocks until the daemon
        process has exited. This may take some time since the daemon
        process will complete its on-going backup activities before
        shutting down. ``block`` can either be ``True`` (in which case
        it blocks indefinitely) or a timeout in seconds.

        The return value is ``True`` if the daemon process has been
        stopped and ``False`` otherwise.

        .. versionadded:: 0.3
            The ``block`` parameter
        """
        self.send_signal(signal.SIGTERM)
        return _block(lambda: not self.is_running(), block)

    def kill(self, block=False):
        """
        Kill the daemon process.

        Sends the SIGKILL signal to the daemon process, killing it. You
        probably want to try :py:meth:`stop` first.

        If ``block`` is true then the call blocks until the daemon
        process has exited. ``block`` can either be ``True`` (in which
        case it blocks indefinitely) or a timeout in seconds.

        Returns ``True`` if the daemon process has (already) exited and
        ``False`` otherwise.

        The PID file is always removed, whether the process has already
        exited or not. Note that this means that subsequent calls to
        :py:meth:`is_running` and :py:meth:`get_pid` will behave as if
        the process has exited. If you need to be sure that the process
        has already exited, set ``block`` to ``True``.

        .. versionadded:: 0.5.1
            The ``block`` parameter
        """
        pid = self.get_pid()
        if not pid:
            raise ValueError('Daemon is not running.')
        try:
            os.kill(pid, signal.SIGKILL)
            return _block(lambda: not self.is_running(), block)
        except OSError as e:
            if e.errno == errno.ESRCH:
                raise ValueError('Daemon is not running.')
            raise
        finally:
            self.pid_file.release()

    def start(self, block=False):
        """
        Start the daemon process.

        The daemon process is started in the background and the calling
        process returns.

        Once the daemon process is initialized it calls the
        :py:meth:`run` method.

        If ``block`` is true then the call blocks until the daemon
        process has started. ``block`` can either be ``True`` (in which
        case it blocks indefinitely) or a timeout in seconds.

        The return value is ``True`` if the daemon process has been
        started and ``False`` otherwise.

        .. versionadded:: 0.3
            The ``block`` parameter
        """
        pid = self.get_pid()
        if pid:
            raise ValueError('Daemon is already running at PID %d.' % pid)

        # The default is to place the PID file into ``/var/run``. This
        # requires root privileges. Since not having these is a common
        # problem we check a priori whether we can create the lock file.
        try:
            self.pid_file.acquire()
        finally:
            self.pid_file.release()

        # Clear previously received SIGTERMs. This must be done before
        # the calling process returns so that the calling process can
        # call ``stop`` directly after ``start`` returns without the
        # signal being lost.
        self.clear_signal(signal.SIGTERM)

        if _detach_process():
            # Calling process returns
            return _block(lambda: self.is_running(), block)
        # Daemon process continues here
        self._debug('Daemon has detached')

        def on_signal(s, frame):
            self._debug('Received signal {}'.format(s))
            self._signal_events[int(s)].set()

        def runner():
            try:
                # We acquire the PID as late as possible, since its
                # existence is used to verify whether the service
                # is running.
                self.pid_file.acquire()
                self._debug('PID file has been acquired')
                self._debug('Calling `run`')
                self.run()
                self._debug('`run` returned without exception')
            except Exception as e:
                self.logger.exception(e)
            except SystemExit:
                self._debug('`run` called `sys.exit`')
            try:
                self.pid_file.release()
                self._debug('PID file has been released')
            except Exception as e:
                self.logger.exception(e)
            os._exit(os.EX_OK)  # FIXME: This seems redundant

        try:
            setproctitle.setproctitle(self.name)
            self._debug('Process title has been set')
            files_preserve = (self.files_preserve +
                              self._get_logger_file_handles())
            signal_map = {s: on_signal for s in self._signal_events}
            signal_map.update({
                    signal.SIGTTIN: None,
                    signal.SIGTTOU: None,
                    signal.SIGTSTP: None,
            })
            with DaemonContext(
                    detach_process=False,
                    signal_map=signal_map,
                    files_preserve=files_preserve):
                self._debug('Daemon context has been established')

                # Python's signal handling mechanism only forwards signals to
                # the main thread and only when that thread is doing something
                # (e.g. not when it's waiting for a lock, etc.). If we use the
                # main thread for the ``run`` method this means that we cannot
                # use the synchronization devices from ``threading`` for
                # communicating the reception of SIGTERM to ``run``. Hence we
                # use  a separate thread for ``run`` and make sure that the
                # main loop receives signals. See
                # https://bugs.python.org/issue1167930
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
        signal, in which case :py:meth:`run` should terminate after
        performing any necessary clean up routines. You can use
        :py:meth:`got_sigterm` and :py:meth:`wait_for_sigterm` to
        check whether SIGTERM has been received.
        """
        pass

