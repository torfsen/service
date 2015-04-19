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

.. _PyPI: https://pypi.python.org/pypi
.. _pip: https://pip.pypa.io/


Quickstart
==========
::

    import time

    from service import Service

    class MyService(Service):
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


Development
===========
The code for this package can be found `on GitHub <https://github.com/torfuspolymorphus/service>`_.
It is available under the `MIT license <http://opensource.org/licenses/MIT>`_.


API Reference
=============

.. automodule:: service
    :members:
    :undoc-members:
    :special-members: __init__

