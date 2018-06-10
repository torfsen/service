# Change Log for the `service` Python Package

The format of this file is based on [Keep a Changelog] and this project adheres to [Semantic Versioning].


## [0.5.1] (2018-06-10)

### Fixed

- Unpinned the dependency versions. They were accidentally pinned in version
  0.5.0. Their minimum versions are still pinned, as intended.

### Added

- Support for blocking until the daemon process has exited after calling
  `Service.kill`


## [0.5.0] (2018-06-09)

### Fixed

- Avoid zombie processes (contributed by [@nicoxxl])
- Fix a race condition regarding the reception of SIGTERM
- Reduce time between lock file acquisition and call of `run`
- Handle `sys.exit` calls in `run`

### Changed

- Use the `pid` module instead of the the deprecated `lockfile` module. As a
  result, `Service.start` now raises `IOError` when it has insufficient
  permissions to write to `pid_dir`.
- The minimum versions of the package's dependencies are now pinned

### Removed

- Support for Python 3.3


## [0.4.1] (2015-06-16)

### Added

- Support for Python 3


## [0.4.0] (2015-05-27)

### Added

- Support for other logging handlers aside from Syslog


## [0.3.0] (2015-04-30)

### Added

- Support for blocking until daemon is ready/shutdown
- Support for other Syslog locations


## [0.2.0] (2015-04-19)

### Added

- Methods `Service.got_sigterm` and `Service.wait_for_sigterm` for improved
  SIGTERM handling

### Removed

- The `on_stop` callback was removed in favour of the newly introduced
 `Service.got_sigterm` and `Service.wait_for_sigterm` methods


## [0.1.1] (2015-02-06)

### Fixed

- Exceptions in `run` and `on_stop` are now logged and cause the PID lock file
  to be removed

### Changed

- Check lockfile permissions before forking to exit early in case of a
  misconfiguration


## 0.1.0 (2015-01-09)

First public release.

[Keep a Changelog]: http://keepachangelog.com/
[Semantic Versioning]: http://semver.org/

[Unreleased]: https://github.com/torfsen/service/compare/v0.5.1...master
[0.5.1]: https://github.com/torfsen/service/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/torfsen/service/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/torfsen/service/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/torfsen/service/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/torfsen/service/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/torfsen/service/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/torfsen/service/compare/v0.1.0...v0.1.1

[@nicoxxl]: https://github.com/nicoxxl

