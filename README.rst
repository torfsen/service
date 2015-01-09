Python background services made easy
####################################
The Python ``service`` package makes it easy to write Unix *services*, i.e.
background processes ("daemons") that are controlled by a foreground
application (e.g. a console script)::

    from service import Service

    class MyService(Service):
        def run(self):
            while True:
                do_work()

    if __name__ == '__main__':
        import sys

        if len(sys.argv) != 2:
            sys.exit('Syntax: %s COMMAND\n' % sys.argv[0])

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

The package is built around the python-daemon_ package, which provides the
means for creating well-behaved daemon processes. The ``service`` package adds
a control infrastructure for easily starting, stopping, querying and killing
the background process from a foreground application.

.. _python-daemon: https://pypi.python.org/pypi/python-daemon

