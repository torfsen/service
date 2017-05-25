Python ``service`` Package
##########################

Easy Implementation of Background Services
==========================================
This package makes it easy to write Unix services, i.e. background
processes ("daemons") that are controlled by a foreground application
(e.g. a console script).

The package is built around the python-daemon_ module, which provides
the means for creating well-behaved daemon processes. The ``service``
package adds a control infrastructure for easily starting, stopping,
querying and killing the background process from a foreground
application.

.. _python-daemon: https://pypi.python.org/pypi/python-daemon


Installation
============
The ``service`` package is available from PyPI_ and can be installed via
pip_::

    pip install service

Supported Python versions are 2.7 as well as 3.3 and later.

.. _PyPI: https://pypi.python.org/pypi/service
.. _pip: https://pip.pypa.io/


Quickstart
==========
::

    import logging
    from logging.handlers import SysLogHandler
    import time

    from service import find_syslog, Service

    class MyService(Service):
        def __init__(self, *args, **kwargs):
            super(MyService, self).__init__(*args, **kwargs)
            self.logger.addHandler(SysLogHandler(address=find_syslog(),
                                   facility=SysLogHandler.LOG_DAEMON))
            self.logger.setLevel(logging.INFO)

        def run(self):
            while not self.got_sigterm():
                self.logger.info("I'm working...")
                time.sleep(5)

    if __name__ == '__main__':
        import sys

        if len(sys.argv) != 2:
            sys.exit('Syntax: %s COMMAND' % sys.argv[0])

        cmd = sys.argv[1].lower()
        service = MyService('my_service', pid_dir='/tmp')

        if cmd == 'start':
            service.start()
        elif cmd == 'stop':
            service.stop()
        elif cmd == 'status':
            if service.is_running():
                print "Service is running."
            else:
                print "Service is not running."
        else:
            sys.exit('Unknown command "%s".' % cmd)


Control Interface
=================
The :py:class:`~service.Service` class has a dual interface: Some methods
control the daemon and are intended to be called from the controlling process
while others implement the actual daemon functionality or utilities for it.

The control methods are:

* :py:meth:`~service.Service.start` to start the daemon
* :py:meth:`~service.Service.stop` to ask the daemon to stop
* :py:meth:`~service.Service.kill` to kill the daemon
* :py:meth:`~service.Service.is_running` to check whether the daemon is running
* :py:meth:`~service.Service.get_pid` to get the daemon's process ID

Subclasses usually do not need to override any of these.


Daemon Functionality
====================
To provide the actual daemon functionality, subclasses override
:py:meth:`~service.Service.run`, which is executed in a separate daemon process
when :py:meth:`~service.Service.start` is called. Once
:py:meth:`~service.Service.run` exits, the daemon process stops.

When :py:meth:`~service.Service.stop` is called, the SIGTERM signal is sent to
the daemon process, which can check for its reception using
:py:meth:`~service.Service.got_sigterm` or wait for it using
:py:meth:`~service.Service.wait_for_sigterm`.


Logging
=======
Instances of :py:class:`~service.Service` provide a built-in logger via their
:py:attr:`~service.Service.logger` attribute. By default the logger only has a
:py:class:`logging.NullHandler` attached, so all messages are discarded. Attach
your own handler to output log messages to files or syslog (see the handlers
provided by the :py:mod:`logging` and :py:mod:`logging.handlers` modules).

Any uncaught exceptions from :py:meth:`~service.Service.run` are automatically
logged via that logger. To avoid error messages during startup being lost make
sure to attach your logging handlers before calling
:py:meth:`~service.Service.start`.

If you want use syslog for logging take a look at
:py:func:`~service.find_syslog`, which provides a portable way of locating
syslog.


Preserving File Handles
=======================
By default, all open file handles are released by the daemon process. If you
need to preserve some of them add them to the
:py:attr:`~service.Service.files_preserve` list attribute. Note that file
handles used by any built-in Python logging handlers attached to
:py:attr:`~service.Service.logger` are automatically preserved.


Exiting the Service
===================
From the outside, a service can be stopped gracefully by calling
:py:meth:`~service.Service.stop` or, as a last resort, by calling
:py:meth:`~service.Service.kill`.

From the inside, i.e. from within :py:meth:`~service.Service.run`, the easiest
way is to just ``return`` from the method. From version 0.5 on you can also
call ``sys.exit`` and it will be handled correctly (in earlier versions that
would prevent a correct clean up). Note that you should never use ``os._exit``,
since that skips all clean up.


API Reference
=============

.. automodule:: service
    :members:
    :undoc-members:
    :special-members: __init__


Development
===========
The code for this package can be found `on GitHub <https://github.com/torfuspolymorphus/service>`_.
It is available under the `MIT license <http://opensource.org/licenses/MIT>`_.


History
=======
:0.4.1:
    * Support for Python 3

:0.4.0:
    * More flexible logging interface

:0.3.0:
    * Support for additional Syslog variants
    * Optional ``block`` parameter for ``Service.start`` and ``Service.stop``

:0.2.0:
    * Easier mechanism for handling the stopping of the service

:0.1.1:
    * Improved error handling

:0.1.0:
    * Initial release

