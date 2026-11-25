"""Read-only account operations, using fixed provider origins and bounded responses."""
import base64
from decimal import Decimal
import hashlib
import http.client
import json
import re
import secrets
from time import time
from urllib.parse import urlencode, urlsplit, unquote

BRIDGE = "bridge.simplefin.org"
BANK_HOSTS = (BRIDGE, "beta-bridge.simplefin.org")
DOC = "account.docusign.com"
REDIRECT = "http://127.0.0.1:54381/callback"
BANK_SIGNUP = "https://bridge.simplefin.org/simplefin/create"


def request(host, method, path, *, headers=None, body=None):
    if host not in (*BANK_HOSTS, DOC):
        raise ValueError("Unsupported provider.")
    conn = http.client.HTTPSConnection(host, timeout=12)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("Provider declined the request.")
        data = response.read(262145)
        if len(data) > 262144:
            raise ValueError("Provider response exceeds limit.")
        return data
    finally:
        conn.close()


def bank_url(value, *, claim):
    if not isinstance(value, str) or len(value) > 2048 or not value.isascii() or not value.isprintable():
        raise ValueError("Invalid SimpleFIN link.")
    url = urlsplit(value)
    if (url.scheme != "https" or url.hostname not in BANK_HOSTS or url.port is not None
            or url.query or url.fragment or "\\" in value):
        raise ValueError("Expected an official SimpleFIN Bridge link.")
    if claim:
        if url.username is not None or not re.fullmatch(r"/simplefin/claim/[a-zA-Z0-9._~-]+", url.path):
            raise ValueError("Invalid setup token.")
    elif (url.path.rstrip("/") != "/simplefin" or not url.username or not url.password
          or not all(re.fullmatch(r"[!-~]{1,500}", unquote(part)) for part in (url.username, url.password))
          or ":" in unquote(url.username)):
        raise ValueError("Invalid balance access link.")
    return url


def claim_bank(token):
    if not token or len(token) > 4096:
        raise ValueError("Invalid setup token.")
    url = bank_url(base64.b64decode(token, validate=True).decode("ascii"), claim=True)
    access = request(url.hostname, "POST", url.path, body=b"").decode("ascii").strip()
    bank_url(access, claim=False)
    return {"access": access}


def balances(access):
    url = bank_url(access, claim=False)
    auth = base64.b64encode((unquote(url.username) + ":" + unquote(url.password)).encode()).decode()
    report = json.loads(request(url.hostname, "GET", "/simplefin/accounts?version=2&balances-only=1",
                                headers={"Authorization": "Basic " + auth}))
    if report.get("errlist") != [] or report.get("errors"):
        raise ValueError("Bank reports a connection issue. Review your connection at SimpleFIN.")
    rows = report["accounts"]
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Invalid balance response.")
    valid = []
    for row in rows:
        amount = row.get("available-balance")
        stamp = row.get("balance-date")
        if (row.get("currency") == "USD" and isinstance(amount, str)
                and re.fullmatch(r"-?[0-9]{1,12}(?:\.[0-9]{1,2})?", amount)
                and type(stamp) is int and 0 <= time() - stamp <= 86400):
            valid.append((amount, stamp))
    # Other accounts may be loans, personal accounts, or share the same owner.
    if len(rows) == len(valid) == 1:
        return dict(available=valid[0][0], as_of=valid[0][1])
    return dict(available=None, as_of=None)


def planning_limit(profile, bank, timestamp):
    if not bank or bank.get("available") is None or not 0 <= timestamp - bank["as_of"] <= 86400:
        return Decimal(0)
    return max(Decimal(0), min(Decimal(profile["budget"]), Decimal(bank["available"])))


def consent(client):
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", client):
        raise ValueError("Enter a registered DocuSign integration key.")
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = dict(response_type="code", scope="signature", client_id=client, redirect_uri=REDIRECT,
                  state=state, code_challenge_method="S256", code_challenge=challenge)
    return "https://" + DOC + "/oauth/auth?" + urlencode(params), state, verifier


def authorize_document(client, verifier, code):
    body = urlencode(dict(grant_type="authorization_code", client_id=client, code=code,
                          code_verifier=verifier, redirect_uri=REDIRECT))
    return _verified_grant(client, body)


def renew_document(record):
    body = urlencode(dict(grant_type="refresh_token", refresh_token=record["refresh"], client_id=record["client"]))
    grant = _verified_grant(record["client"], body)
    if not grant.get("refresh"):
        grant["refresh"] = record["refresh"]
    return grant


def _verified_grant(client, body):
    grant = json.loads(request(DOC, "POST", "/oauth/token", body=body,
                               headers={"Content-Type": "application/x-www-form-urlencoded"}))
    token = grant.get("access_token")
    if (not isinstance(token, str) or not re.fullmatch("[!-~]{1,16000}", token)
            or str(grant.get("token_type")).lower() != "bearer"
            or type(grant.get("expires_in")) is not int or grant["expires_in"] <= 0):
        raise ValueError("Invalid consent response.")
    info = json.loads(request(DOC, "GET", "/oauth/userinfo", headers={"Authorization": "Bearer " + token}))
    if not info.get("sub") or not info.get("accounts"):
        raise ValueError("DocuSign could not confirm an account.")
    refresh = grant.get("refresh_token")
    if refresh is not None and (not isinstance(refresh, str) or not re.fullmatch("[!-~]{1,16000}", refresh)):
        raise ValueError("Invalid renewal response.")
    return dict(client=client, token=token, refresh=refresh, expires=int(time()) + grant["expires_in"])
