# RC1 source security tripwires and build inventory (E02/E37/E38/E40)

Base PR #75 corrected head 206d6b24bd792834871a7ae88f8743007afc0f31:
both Python suites passed (663 tests); Windows source and Genesis recovery
smoke passed, packaged status pending at preflight. Previous #74 full
Windows run 45563633231 succeeded.

## Build dependency evidence

Observed in #74 Windows logs, Python 3.12.10, PyInstaller 6.12.0:
altgraph 0.17.5, packaging 26.3 (already installed), pefile 2023.2.7,
pyinstaller-hooks-contrib 2026.10, pywin32-ctypes 0.2.3, setuptools 84.2.1.
Pin these exact observed versions for the next isolated Windows build
in requirements-build-windows.txt; no unreviewed upgrade or paid service.
Use clean venv, binary wheels only and pip check. Inventory checks actual
installed versions and denies extra distributions except pip bootstrap.
Collect normalized package names, versions, bounded license metadata hints,
Python, SQLite, OpenSSL and Unicode database versions. No package paths,
environment secrets, registry credentials or real customer data.
Record source file fingerprints and review findings without matched content.

Two additional artifact files: BUILD-INVENTORY.json and SOURCE-REVIEW.json.
They are separate unsigned review reports, not included in the existing
PREVIEW.json hash binding or a cryptographic attestation. Package versions
alone are not artifact hashes, dependency vulnerability clearance or
reproducibility; package metadata license hints are not licenses. The
installed build environment is not the set of modules or DLLs actually
bundled by PyInstaller. Frozen binary SBOM, license notices, build hash
lock, action pinning, advisory database queries, independent source review
and history secret scans are outstanding. No actual vulnerability database
queries or independent audit claimed. No changes to runtime dependencies.

## Source tripwires

Scan desktop.py and flat nexus_exchange/*.py UTF-8 sources only with bounded
AST and selected narrow credential formats. Reject new non-stdlib imports,
selected dynamic evaluation/process/deserialization imports/calls,
unsafe SQLite extension/script calls, shell=True and insecure transport,
network imports outside current reviewed adapters and desktop browser,
non-HOST HTTPS constructor. Existing fixed host read-only adapters and
explicit desktop browser launch remain review surfaces, not an automatic
permission grant. Local urllib.parse is not a network request. No source
execution, network, test/document/history scan, full data-flow/taint tracking,
dynamic alias resolution or general secret detection. This is a small
fail-closed regression tripwire, not a sandbox or comprehensive scanner.
Report paths, line numbers, reason codes, imports and hashes; do not emit
matched source/credential content. Both Python CI suites run it before tests.

Eight regression methods test actual source tree, synthetic unsafe imports,
aliases, credential redaction, bounds, version drift, duplicate distributions
and explicit limitations. Exact-head hosted verification required. The
Windows package remains unsigned. Formal main acceptance remains 0/42.
Next: independent dependency advisory/license review, stronger packaged
SBOM and source/authority audit, further Operator capability work. No new
runtime package or new paid resource.
