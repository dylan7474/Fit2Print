"""Check that a request really came through Cloudflare Access, so the page needs no token on the internet path.

Cloudflare Access puts a signed login proof (a JWT, RS256) on every request it lets through, in the header Cf-Access-Jwt-Assertion. This verifies that proof
with Cloudflare's public keys for YOUR team (https://TEAM.cloudflareaccess.com/cdn-cgi/access/certs): the signature, that it was issued for THIS application
(the AUD tag), by YOUR team, has not expired, and (optionally) is for an allowed email. If Access is ever missing or misconfigured the proof is absent and
the request is refused: the page does not rely on Cloudflare's settings being right.
Standard library only (RSA verification is one modular exponentiation and a padding check)."""
import base64, hashlib, hmac, json, time, urllib.request

SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

def _b64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def rs256_verify(n, e, signed, sig):
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    m = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    t = SHA256_PREFIX + hashlib.sha256(signed).digest()
    expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return hmac.compare_digest(m, expected)

class Verifier:
    def __init__(self, team, aud, allowed_emails=None, fetch=None, now=time.time):
        self.team, self.aud, self.emails = team.strip().lower(), aud.strip(), [e.lower() for e in (allowed_emails or [])]
        self.iss = f"https://{self.team}.cloudflareaccess.com"
        self._fetch, self._now, self.keys, self.fetched = fetch or self._http, now, {}, 0
    def _http(self):
        with urllib.request.urlopen(f"{self.iss}/cdn-cgi/access/certs", timeout=8) as r:
            return json.loads(r.read())
    def _load(self):
        self.keys = {k["kid"]: (int.from_bytes(_b64(k["n"]), "big"), int.from_bytes(_b64(k["e"]), "big")) for k in self._fetch().get("keys", []) if k.get("kty") == "RSA"}
        self.fetched = self._now()
    def check(self, token):
        """-> (ok, who or reason). Never raises on a bad token."""
        try:
            h, p, s = token.split(".")
            head = json.loads(_b64(h))
            if head.get("alg") != "RS256":
                return False, "unsupported signature type"
            kid = head.get("kid")
            if kid not in self.keys or self._now() - self.fetched > 3600:
                self._load()                                         # new keys appear when Cloudflare rotates them
            if kid not in self.keys:
                return False, "unknown signing key"
            n, e = self.keys[kid]
            if not rs256_verify(n, e, f"{h}.{p}".encode(), _b64(s)):
                return False, "bad signature"
            c = json.loads(_b64(p))
            aud = c.get("aud")
            if self.aud not in (aud if isinstance(aud, list) else [aud]):
                return False, "issued for a different application"
            if c.get("iss") != self.iss:
                return False, "issued by a different team"
            if float(c.get("exp", 0)) < self._now():
                return False, "expired"
            if "nbf" in c and float(c["nbf"]) > self._now() + 60:
                return False, "not valid yet"
            who = str(c.get("email", ""))
            if self.emails and who.lower() not in self.emails:
                return False, "not an allowed email"
            return True, who
        except Exception as ex:
            return False, f"unreadable proof ({type(ex).__name__})"
