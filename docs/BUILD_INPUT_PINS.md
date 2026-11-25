# RC1 build input pinning (E02, E37, E39, E40; H06/H07)

Base: PR #75 206d6b24bd792834871a7ae88f8743007afc0f31.
Observed Python 3.10/3.13 CI 45564173366 succeeded; Python 3.13
log: 663 tests passed. Windows workflow 45564173107 completed successfully,
including source and frozen smoke and upload. No main gate accepted.

RC1 #74 Windows job 139033029620 recorded CPython 3.12.10, packaging
26.3 already installed, and installation of the six other versions listed
in requirements-windows-build.txt. Pin these observed versions and use a
fresh virtual environment, wheel-only install without implicit dependency
resolution, pip check and installed-distribution inventory in the log.
No new runtime packages. Pin existing workflow actions to their exact
observed checkout, setup-python and upload-artifact SHAs; avoid retaining
checkout credentials. Preserve all prior unit/source/frozen smoke and
manifest validation. No dependency upgrades or paid infrastructure.

This is an input-version lock, NOT a hash lock, signed SBOM, vulnerability
audit or reproducible binary guarantee. The runner image, CPython
distribution bytes, bootstrap pip, wheel bytes and bundled runtime still
need attestation. No external package code copied. Existing preview
metadata remains unsigned. Package and runner availability must be
verified in the actual Windows job before promotion.

Upstream reconnaissance: PyInstaller v6.12.0 at
https://github.com/pyinstaller/pyinstaller/tree/31dbe9ff477716e4790aa317bc9da68766d20659
reviewed COPYING.txt, setup.py and pyproject.toml. GPL-2.0-or-later with
bootloader exception, runtime hooks Apache-2.0 and isolated submodule
dual-license option. Exception permits distributing linked bootloader
combinations but does not waive other redistribution obligations.
Do not infer that transitive packages, CPython, Tcl/Tk or the Windows
executable as a whole have passed distribution-license review.
Full wheel hashes, dependency advisory and bundled-license inventory,
secret scanning, independent QA and release acceptance remain outstanding.
The seven agent references remain design-only per AGENT_ENGINEERING_ADOPTION.
Operative PR #116 inspected read-only; no trading code imported.

Two focused lock-format/inventory tests exercised locally in an isolated
Linux fixture (one expected missing-file error before adding lock,
then both passed); full checkout unavailable due to GitHub DNS.
Hosted full regression and Windows packaging are required.
Formal main acceptance remains 0/42. No change to live-action permissions.
