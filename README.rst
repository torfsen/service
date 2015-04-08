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

For details, please see the documentation_.

.. _documentation: http://python-service.readthedocs.org/


Installation
============
Installation is easy via pip_::

    pip install service

.. _pip: https://pip.pypa.io/en/latest/index.html
