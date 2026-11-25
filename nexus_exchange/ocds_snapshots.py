"""Select latest complete snapshots, never merge incremental OCDS releases."""
from .ocds_identity import release_identity
from .scout import _timestamp, _text

def select_snapshots(publisher, releases):
    latest = {}
    seen = {}
    for release in releases:
        key = release_identity(publisher, release)
        ocid = _text(release["ocid"], 256)
        if ocid != release["ocid"] or publisher != publisher.strip():
            raise ValueError("noncanonical identity")
        date = _timestamp(release.get("date"))
        if key in seen and seen[key] != release:
            raise ValueError("conflicting release identity")
        seen[key] = release
        previous = latest.get(ocid)
        if previous is not None and previous[0] == date and previous[1] != release:
            raise ValueError("ambiguous latest release")
        if previous is None or date > previous[0]:
            latest[ocid] = (date, release)
    return tuple(latest[k][1] for k in sorted(latest))
