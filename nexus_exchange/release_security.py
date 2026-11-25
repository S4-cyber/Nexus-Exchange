"""Bounded source tripwires and build-environment inventory for release review.

Not a vulnerability scanner, sandbox, SBOM of the frozen executable, secret
history scan, independent audit or legal/license approval.
"""
import argparse
import ast
from hashlib import sha256
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import stat
import sys
import unicodedata

FORMAT="nexus-release-security-inventory-v1"
MAX_SOURCE_BYTES=512*1024
MAX_SOURCE_FILES=256
MAX_DIST=128
MAX_REPORT_BYTES=256*1024
ADAPTERS={"sam_search","ted_search","fts_search","canada_search","usaspending_search",
          "fx_reference","sec_company","cf_search"}
PACKAGER={"altgraph":"0.17.5","packaging":"26.3","pefile":"2023.2.7",
          "pyinstaller":"6.12.0","pyinstaller-hooks-contrib":"2026.10",
          "pywin32-ctypes":"0.2.3","setuptools":"84.2.1"}
_FLAGS=("independently_verified","vulnerabilities_cleared","license_compliance_verified",
        "secrets_history_scanned","frozen_binary_sbom_complete","publisher_authenticated",
        "release_eligible","external_authority")
# Narrow high-confidence credential formats only; never print the matched
# value. This is not entropy-based discovery or a full Git history scan.
_SECRET_PATTERNS=(
    ("PRIVATE_KEY_HEADER",r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    ("GITHUB_TOKEN_SHAPE",r"(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{50,255})(?![A-Za-z0-9_])"),
    ("AWS_ACCESS_KEY_SHAPE",r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
)
_NETWORK_ROOTS={"socket","http","urllib.request","urllib3","requests","httpx","ftplib","smtplib",
                "imaplib","poplib","telnetlib","asyncio","websocket","websockets","webbrowser"}
_UNSAFE_IMPORTS={"pickle","dill","marshal","shelve","subprocess","ctypes"}
_UNSAFE_CALLS={"eval","exec","__import__","builtins.eval","builtins.exec","builtins.__import__",
    "importlib.import_module","os.system","os.popen","os.startfile","os.execv","os.execve",
    "os.spawnv","os.spawnve","pickle.loads","pickle.load","marshal.loads","marshal.load",
    "sqlite3.Connection.enable_load_extension","sqlite3.Connection.load_extension"}
_VERSION=re.compile(r"[A-Za-z0-9][A-Za-z0-9.!+_-]{0,79}")
_NAME=re.compile(r"[a-z0-9][a-z0-9-]{0,79}")


def _json(value):
    return json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)


def _hash(raw):
    return sha256(raw).hexdigest()


def _module(path):
    return Path(path).stem


def _within(module,root):
    return module==root or module.startswith(root+".")


def _source(path):
    initial=path.lstat()
    if not stat.S_ISREG(initial.st_mode) or not 1<=initial.st_size<=MAX_SOURCE_BYTES:
        raise ValueError("source outside audit bounds")
    with path.open("rb") as handle:
        raw=handle.read(MAX_SOURCE_BYTES+1)
    if len(raw)!=initial.st_size or len(raw)>MAX_SOURCE_BYTES:
        raise ValueError("source changed or exceeds audit bound")
    return raw


def scan_source(path,raw):
    """One source module, bounded AST/import/call checks; no execution."""
    if (type(path) is not str or not (path=="desktop.py" or
            re.fullmatch(r"nexus_exchange/[a-z_][a-z0-9_]*\.py",path))):
        raise ValueError("unsupported audit source path")
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_SOURCE_BYTES:
        raise ValueError("source outside audit bounds")
    module=_module(path)
    try:
        source=raw.decode("utf-8")
        tree=ast.parse(source,filename=path)
    except (SyntaxError,UnicodeError,RecursionError):
        raise ValueError("unparseable application source") from None
    imports=set()
    findings=set()
    aliases={}
    network=set()

    def finding(code,line):
        findings.add((code,line))

    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            declarations=[(alias.name,alias.asname or alias.name.split(".")[0],
                           alias.name if alias.asname else alias.name.split(".")[0]) for alias in node.names]
        elif isinstance(node,ast.ImportFrom) and not node.level:
            base=node.module or ""
            declarations=[(base,alias.asname or alias.name,base+"."+alias.name) for alias in node.names]
        else:
            continue
        for imported,local,resolved in declarations:
            root=imported.split(".")[0]
            imports.add(imported)
            aliases[local]=resolved
            if root not in sys.stdlib_module_names and root not in ("nexus_exchange","desktop"):
                finding("NON_STDLIB_APPLICATION_IMPORT",node.lineno)
            if root in _UNSAFE_IMPORTS and not (path == "nexus_exchange/account_vault.py" and root == "ctypes"):
                finding("RESTRICTED_IMPORT",node.lineno)
            # urllib.parse is local URL manipulation and is not itself a network call.
            if any(_within(imported,n) or _within(resolved,n) for n in _NETWORK_ROOTS):
                network.add(imported)
                allowed=imported=="http.client" and module in ADAPTERS
                allowed=allowed or (imported=="webbrowser" and path=="desktop.py")
                allowed = allowed or (imported == "http.client" and path == "nexus_exchange/account_providers.py")
                allowed = allowed or (imported == "urllib.request" and path == "nexus_exchange/public_feeds.py")
                allowed = allowed or (imported == "http.server" and path == "nexus_exchange/consent_callback.py")
                if not allowed:
                    finding("NETWORK_IMPORT_OUTSIDE_REVIEWED_SURFACE",node.lineno)

    def name(node):
        if isinstance(node,ast.Name):
            return aliases.get(node.id,node.id)
        if isinstance(node,ast.Attribute):
            return name(node.value)+"."+node.attr
        return ""

    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):
            continue
        call=name(node.func)
        if call in _UNSAFE_CALLS or call.startswith(("subprocess.","os.exec","os.spawn")):
            finding("RESTRICTED_DYNAMIC_OR_PROCESS_CALL",node.lineno)
        if isinstance(node.func,ast.Attribute) and node.func.attr in ("enable_load_extension","load_extension","executescript"):
            finding("RESTRICTED_SQLITE_CALL",node.lineno)
        if any(kw.arg=="shell" and isinstance(kw.value,ast.Constant) and kw.value.value is True
               for kw in node.keywords):
            finding("SHELL_TRUE",node.lineno)
        if call in ("http.client.HTTPConnection","ssl._create_unverified_context"):
            finding("INSECURE_TRANSPORT_CALL",node.lineno)
        if call=="http.client.HTTPSConnection":
            host_name = node.args[0].id if node.args and isinstance(node.args[0], ast.Name) else None
            approved_origin = (module in ADAPTERS and host_name == "HOST") or (
                path == "nexus_exchange/account_providers.py" and host_name == "host")
            if not approved_origin:
                finding("HTTPS_ORIGIN_REVIEW_REQUIRED",node.lineno)
        if call.startswith("webbrowser.") and path!="desktop.py":
            finding("BROWSER_OUTSIDE_DESKTOP",node.lineno)
    for code,pattern in _SECRET_PATTERNS:
        for hit in re.finditer(pattern,source):
            finding(code,source.count("\n",0,hit.start())+1)
    return dict(path=path,sha256=_hash(raw),bytes=len(raw),imports=sorted(imports),
                network_imports=sorted(network),
                findings=[dict(code=code,line=line) for code,line in sorted(findings)])


def scan_tree(root):
    """Current application source, not tests/docs/workflow history or generated code."""
    root=Path(root)
    package=root/"nexus_exchange"
    if not root.is_dir() or not package.is_dir() or package.is_symlink():
        raise ValueError("application source checkout required")
    # Reject additional Python subpackages until the review inventory expands.
    if any(p.is_dir() and p.name!="__pycache__" for p in package.iterdir()):
        raise ValueError("new package directory requires source review")
    paths=[root/"desktop.py"]+sorted(package.glob("*.py"))
    if not 2<=len(paths)<=MAX_SOURCE_FILES:
        raise ValueError("application source inventory outside bounds")
    rows=[scan_source(p.relative_to(root).as_posix(),_source(p)) for p in paths]
    payload=dict(format="nexus-source-tripwires-v1",source_files=len(rows),
        files=rows,findings_count=sum(len(row["findings"]) for row in rows),
        scope="APPLICATION_PYTHON_SOURCE_ONLY",**dict.fromkeys(_FLAGS,False))
    return dict(payload,report_sha256=_hash(_json(payload).encode("ascii")))


def _distribution_name(value):
    if type(value) is not str:
        raise ValueError("invalid installed distribution name")
    canonical=re.sub(r"[-_.]+","-",value).lower()
    if not _NAME.fullmatch(canonical):
        raise ValueError("invalid installed distribution name")
    return canonical


def _version(value):
    if type(value) is not str or not _VERSION.fullmatch(value):
        raise ValueError("invalid installed distribution version")
    return value


def _license_hint(value):
    # Only bounded short printable metadata; a long license body is not
    # necessary in this inventory, and absence is explicitly unknown.
    if type(value) is not str:
        return None
    value=" ".join(value.split())
    if not 1<=len(value)<=200 or not value.isascii() or not value.isprintable():
        return None
    return value


def inventory(distributions,*,expect_packager=False):
    if type(expect_packager) is not bool:
        raise ValueError("explicit packager check required")
    rows=[]
    names=set()
    for dist in distributions:
        if len(rows)>=MAX_DIST:
            raise ValueError("build distribution inventory capacity exceeded")
        data=dist.metadata
        name=_distribution_name(data.get("Name"))
        version=_version(dist.version)
        if name in names:
            raise ValueError("duplicate installed distribution")
        names.add(name)
        rows.append(dict(name=name,version=version,
            license_expression_hint=_license_hint(data.get("License-Expression")),
            license_metadata_hint=_license_hint(data.get("License"))))
    rows.sort(key=lambda row:row["name"])
    actual={row["name"]:row["version"] for row in rows}
    if expect_packager:
        if any(actual.get(k)!=v for k,v in PACKAGER.items()):
            raise ValueError("Windows build package version drift")
        if not set(actual)<=set(PACKAGER)|{"pip"}:
            raise ValueError("unexpected distribution in isolated build environment")
    payload=dict(format=FORMAT,scope="INSTALLED_BUILD_ENVIRONMENT_NOT_FROZEN_CONTENTS",
        python=".".join(str(x) for x in sys.version_info[:3]),
        sqlite=sqlite3.sqlite_version,openssl=ssl.OPENSSL_VERSION,
        unicode_database=unicodedata.unidata_version,
        pinned_packager_versions_checked=expect_packager,distributions=rows,
        **dict.fromkeys(_FLAGS,False))
    return dict(payload,report_sha256=_hash(_json(payload).encode("ascii")))


def _write(path,report):
    raw=(_json(report)+"\n").encode("ascii")
    if len(raw)>MAX_REPORT_BYTES:
        raise ValueError("security inventory report size exceeded")
    with Path(path).open("xb") as handle:
        handle.write(raw)


def main():
    parser=argparse.ArgumentParser(description="Narrow local release-review tripwires; not security clearance")
    sub=parser.add_subparsers(dest="operation",required=True)
    source=sub.add_parser("source")
    source.add_argument("root")
    source.add_argument("--output")
    build=sub.add_parser("build")
    build.add_argument("--output",required=True)
    build.add_argument("--expect-packager",action="store_true")
    args=parser.parse_args()
    if args.operation=="source":
        report=scan_tree(args.root)
        if args.output:
            _write(args.output,report)
        print(_json(dict(source_files=report["source_files"],findings_count=report["findings_count"],
                         findings=[dict(path=row["path"],**f) for row in report["files"] for f in row["findings"]])))
        return 1 if report["findings_count"] else 0
    report=inventory(metadata.distributions(),expect_packager=args.expect_packager)
    _write(args.output,report)
    print(_json(report))
    return 0


if __name__=="__main__":
    sys.exit(main())
