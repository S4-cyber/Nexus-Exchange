# Accessible cockpit follow-up

Base #78 (044256ed7232640482fb8c16d01d0dfe6e4e0963), verified Windows GUI/frozen and Genesis smoke run 45565710622.
The dashboard and 16 child-workspace entry points use a shared two-axis
viewport, preserving original local command callbacks. Emergency halt,
Resume offline, recovery and halt status are fixed above dashboard scrolling.
The help dock and animated rails remain fixed. Keyboard focus reveals clipped
controls without invoking them. No global hooks or runtime authority changes.

GUI smoke exercises deliberately overflowing child content, horizontal and
vertical scroll reach, fixed help and halt placement, and timer cleanup.
Pure tests cover focus reveal and Council context labels.

Consolidate the verified #76 action SHA pins, checkout credential retention
disablement, CPython 3.12.10 pin and wheel-only/no-deps install. Preserve the
canonical requirements-build-windows.txt and security inventory instead of
introducing a competing lock. Adapt #76 lock-format tests. #76 remains intact.
No signed SBOM or complete supply-chain audit claimed. No new dependencies
or provider calls. Manual unusual DPI/monitor visual review remains open.
No merge to main or commercial activation.
