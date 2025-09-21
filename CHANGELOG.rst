=========================
o0\_o.posix Release Notes
=========================

.. contents:: Topics

v1.4.0
======

Major Changes
-------------

- Centralized linter configuration with 79-character line limits.
- Detects POSIX.1 (XSH), POSIX.2 (XCU), XSI, and SUS compliance using getconf commands.
- Full transparency with actual getconf values in output.
- Intelligent fallback when _POSIX2_VERSION is undefined but _XOPEN_XCU_VERSION indicates POSIX.2 exists.
- New `compliance` module for detecting POSIX and UNIX standards compliance on target systems.
- New `df` filter for parsing df command output into structured data.
- New `jc` filter plugin for parsing command outputs into structured data using the jc library.
- New `mount` filter for parsing mount command output into structured data.
- New `mounts` module for gathering mount point information with raw fallback support.
- New `uname` filter for parsing uname output with hostname support.
- Support for both current and anticipated future standards (POSIX.1-2024, SUSv5).

Minor Changes
-------------

- Consolidated linter configuration into pyproject.toml and .yamllint.

Bugfixes
--------

- Applied consistent formatting across all action plugins and modules.
- Fixed line length issues to comply with 79-character limit.

v1.3.4
======

Minor Changes
-------------

- Improved code formatting for better readability.
- Removed unnecessary readline dependencies from CI scripts.

Bugfixes
--------

- Formatting consistency across action plugins and modules.
- Line length issues in command.py, template.py, and posix_base.py to comply with 79 character limit.

v1.3.3
======

Bugfixes
--------

- Added retry logic with exponential backoff for package manager operations.
- Fixed package installation failures due to transient repository issues.

v1.3.2
======

Minor Changes
-------------

- Implemented comprehensive CI testing across Linux and macOS platforms.
- Various bug fixes and improvements identified through CI testing.

v1.3.1
======

Minor Changes
-------------

- Fixed module import ordering to comply with Ansible sanity tests.
- Improved code quality with consistent string quoting and formatting.
- Standardized code formatting and PEP 8 compliance across collection.

v1.3.0
======

Major Changes
-------------

- `facts` module, action plugin and tests

v1.2.2
======

Bugfixes
--------

- Fallback logic and error handling improvements to the command action plugin
- Missing failures integration tests for the command module

v1.2.1
======

Bugfixes
--------

- Fix missing interpreter detection

v1.2.0
======

Major Changes
-------------

- Integration tests for template edge cases (force, validation, vars).
- `force=false` behavior for raw-mode file writes.
- `template` plugin with full feature parity and fallback logic.

Bugfixes
--------

- Check mode propagation and return code handling in `_cmd`.

v1.1.1
======

Major Changes
-------------

- Add missing `lineinfile_dedupe` entry in the module stub section of the README.

v1.1.0
======

Major Changes
-------------

- New `content_lines` field added to `slurp64` for line-by-line access to decoded content.
- New `lineinfile_dedupe` module with deduplication and raw fallback support.
- Shared documentation fragment `o0_o.posix.file` for file-related parameters and SELinux options.
- Structured debug logging in raw fallback code paths for easier troubleshooting.

Minor Changes
-------------

- Improved handling of `check_mode` and `diff` in all raw-compatible modules.
- README updated with examples for `lineinfile_dedupe` and Galaxy badge.

Bugfixes
--------

- Argument validation for raw-mode execution and fallback consistency.
- Edge case bugs in `command` fallback when using `_uses_shell` and `argv`.

v1.0.0
======

Major Changes
-------------

- Initial test coverage (unit + integration) for raw fallback compatibility.
- New `command` module with fallback to raw execution when Python is unavailable.
- New `slurp64` module for reading and decoding remote files, with fallback to `cat`.
