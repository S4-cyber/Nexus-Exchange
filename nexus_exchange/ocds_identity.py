"""Offline OCDS release identity; no network or action authority."""
import hashlib
import json

def release_identity(publisher, release):
    if type(publisher) is not str or not publisher.strip() or len(publisher)>256:
        raise ValueError("invalid publisher")
    if type(release) is not dict:
        raise ValueError("invalid release")
    parts=[publisher,release.get("ocid"),release.get("id")]
    if any(type(x) is not str or not x.strip() or len(x)>256 or any(ord(c)<32 for c in x) for x in parts):
        raise ValueError("invalid identity")
    if "#" in parts[2]:
        raise ValueError("invalid release id")
    return hashlib.sha256(json.dumps(parts,ensure_ascii=True,separators=(",",":")).encode()).hexdigest()
