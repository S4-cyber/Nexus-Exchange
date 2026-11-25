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


## RC3 security evidence binding — 2026-11-25

Verified #95 predecessor e2abf03adb7127c3da46595fd745ecb12b2ec33b:
both Python 3.10 and 3.13 logs report 806 tests OK
(45652532839); full Windows source, native receipt GUI, fixture process,
Genesis, security and frozen executable verification succeeded (45652532806,
artifact 15041332928). Development checks authorized by owner; independent
release approval is separate.

E02/E37/E38/E39/E40, H06/H07: bind both existing security review reports to
a v2 preview manifest by exact file SHA-256, byte count and internal report
digest. Strict canonical bounded schemas, pinned distributions, no findings,
false authority flags. Existing v1 bundles remain verifiable as legacy
only. CI explicitly requires v2 with --require-security-reports on write
and verify; v1 cannot meet that policy. No signature, independent
attestation, full SBOM, advisory/license clearance or authentication.
Five isolated helper tests passed locally after expected missing-module
failure (matching blob hashes); four integration tests added; exact full
checkout DNS blocked and hosted candidate checks pending. No new runtime
dependencies, external actions, cost, Operative changes or formal main
acceptance (0/42).


## RC3 source review integrity — 2026-11-25

E02/E37/E38/E39/E40; H06/H07. Exact RC3 head
2e6aab4279be679ad18167cd23a36e74408155d4 passed 815 tests on both
Python versions and Windows 45653537383 (artifact 15041778609).
Follow-up PR #96 head a8dcf3d760a8d611e33326e6c49cfbf0791aed12 also
passed 815 tests on each Python version (45658974764), plus full Windows
45658974941 (artifact 15042814943). Its workflow now covers RC3-targeting
PRs, including new application and test modules.

This increment rejects wildcard imports in source tripwires (including
relative imports) rather than silently missing their imported names.
Bounded source reads compare descriptor and path identity before/after
the read, reject symlinks/nonregular files and normalize unavailable
files to ValueError. Two regression methods cover wildcard imports and
same-size atomic replacement between initial lstat and open. These
are narrow defensive controls, not a complete filesystem sandbox,
taint analysis, independent audit or security clearance. No change to
provider access, runtime permissions or build packages. Full local
checkout remains blocked by GitHub DNS; local full red/green not run.
Coherent implementation and tests submitted together for hosted CI.

Reuse: pinned agency-agents security auditor
8ae6164602c95ca78828b148b9052460ee426885 (MIT) reviewed as a defensive
design reference only. Operative risk_gate.py blob
ab737fdd8fae557ef456e3240d6580fc35d9e459 inspected for exact-type
default-deny design; no code copied and no Operative changes. Formal
main acceptance remains 0/42. No spending, cloud provisioning or
external commercial actions. Independent security/license review,
source permissions, signing and role authorization remain outstanding.
