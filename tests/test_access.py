import base64, hashlib, http.client, json, random, tempfile, threading, time, unittest
from fit2print import access, server

def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def is_prime(n, rnd):
    if n < 4: return n in (2, 3)
    if n % 2 == 0: return False
    d, r = n - 1, 0
    while d % 2 == 0: d //= 2; r += 1
    for _ in range(20):
        x = pow(rnd.randrange(2, n - 1), d, n)
        if x in (1, n - 1): continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1: break
        else: return False
    return True

def make_key(bits=1024, seed=7):
    rnd = random.Random(seed)
    def prime():
        while True:
            c = rnd.getrandbits(bits // 2) | (1 << (bits // 2 - 1)) | 1
            if is_prime(c, rnd) and (c - 1) % 65537: return c
    p, q = prime(), prime()
    n, e = p * q, 65537
    return n, e, pow(e, -1, (p - 1) * (q - 1))

N, E, D = make_key()
OTHER = make_key(seed=99)

def sign(payload, key=(N, E, D), kid="k1", alg="RS256", tamper=False):
    n, e, d = key
    head = b64(json.dumps(dict(alg=alg, kid=kid)).encode()); body = b64(json.dumps(payload).encode())
    k = (n.bit_length() + 7) // 8; t = access.SHA256_PREFIX + hashlib.sha256(f"{head}.{body}".encode()).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
    if tamper: body = b64(json.dumps(dict(payload, email="evil@example.com")).encode())
    return f"{head}.{body}.{b64(sig)}"

def jwks(n=N, e=E, kid="k1"):
    return dict(keys=[dict(kty="RSA", kid=kid, alg="RS256", n=b64(n.to_bytes((n.bit_length() + 7) // 8, "big")), e=b64(e.to_bytes(3, "big")))])

NOW = 1_800_000_000
def claims(**kw): return dict(dict(aud=["AUD1"], iss="https://myteam.cloudflareaccess.com", exp=NOW + 600, email="me@example.com"), **kw)

class Proof(unittest.TestCase):
    def v(self, **kw): return access.Verifier("myteam", "AUD1", fetch=lambda: jwks(), now=lambda: NOW, **kw)
    def test_a_good_proof_is_accepted_and_says_who(self):
        ok, who = self.v().check(sign(claims())); self.assertTrue(ok); self.assertEqual(who, "me@example.com")
    def test_a_tampered_proof_is_refused(self):                 # NEGATIVE CONTROLS: each way a proof can be wrong
        self.assertEqual(self.v().check(sign(claims(), tamper=True)), (False, "bad signature"))
    def test_signed_with_someone_elses_key_is_refused(self):
        self.assertEqual(self.v().check(sign(claims(), key=OTHER)), (False, "bad signature"))
    def test_a_different_application_is_refused(self):
        self.assertEqual(self.v().check(sign(claims(aud=["OTHER"]))), (False, "issued for a different application"))
    def test_a_different_team_is_refused(self):
        self.assertEqual(self.v().check(sign(claims(iss="https://evil.cloudflareaccess.com"))), (False, "issued by a different team"))
    def test_an_expired_proof_is_refused(self):
        self.assertEqual(self.v().check(sign(claims(exp=NOW - 1))), (False, "expired"))
    def test_an_unknown_key_is_refused(self):
        self.assertEqual(self.v().check(sign(claims(), kid="nope")), (False, "unknown signing key"))
    def test_alg_none_is_refused(self):
        h = b64(json.dumps(dict(alg="none", kid="k1")).encode()); p = b64(json.dumps(claims()).encode())
        self.assertFalse(self.v().check(f"{h}.{p}.")[0]); self.assertFalse(self.v().check(f"{h}.{p}.AAAA")[0])
    def test_garbage_never_raises(self):
        for g in ("", "a.b.c", "....", "x" * 5000, "a.b"): self.assertFalse(self.v().check(g)[0])
    def test_an_email_allow_list_can_narrow_it(self):
        self.assertFalse(self.v(allowed_emails=["someone@else.com"]).check(sign(claims()))[0]); self.assertTrue(self.v(allowed_emails=["ME@example.com"]).check(sign(claims()))[0])

class Doors(unittest.TestCase):
    """The page's rules, end to end: home network in; the Cloudflare path only with a valid proof; no token anywhere."""
    def serve(self, **kw):
        d = tempfile.mkdtemp(); acc = access.Verifier("myteam", "AUD1", fetch=lambda: jwks(), now=lambda: NOW)
        srv = server.make_server(dict(projects=[], new_projects_dir=d), "127.0.0.1", 0, access=acc if kw.pop("with_access", True) else None, **kw)
        threading.Thread(target=srv.serve_forever, daemon=True).start(); self.addCleanup(lambda: (srv.shutdown(), srv.server_close())); return srv.server_address[1]
    def status(self, port, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/", headers=headers or {}); r = c.getresponse(); r.read(); return r.status
    def test_the_home_network_is_in_without_a_token(self):
        self.assertEqual(self.status(self.serve(trust_lan=True)), 200)
    def test_a_cloudflare_request_with_a_valid_login_proof_is_in_without_a_token(self):
        port = self.serve(trust_lan=True); proof = sign(claims())            # (the verifier's clock is fixed at NOW in these tests)
        self.assertEqual(self.status(port, {"Cf-Ray": "x", "Cf-Access-Jwt-Assertion": proof}), 200)
    def test_a_cloudflare_request_with_no_proof_is_refused(self):      # the misconfiguration this protects against: a hostname with no Access in front of it
        self.assertEqual(self.status(self.serve(trust_lan=True), {"Cf-Ray": "x", "Cf-Connecting-Ip": "8.8.8.8"}), 401)
    def test_a_forged_proof_is_refused(self):
        self.assertEqual(self.status(self.serve(trust_lan=True), {"Cf-Ray": "x", "Cf-Access-Jwt-Assertion": sign(claims(), key=OTHER)}), 401)
    def test_a_proof_in_the_cookie_works_too(self):
        self.assertEqual(self.status(self.serve(trust_lan=True), {"Cf-Ray": "x", "Cookie": "CF_Authorization=" + sign(claims())}), 200)
    def test_with_access_not_configured_a_cloudflare_request_is_refused_not_let_through(self):
        self.assertEqual(self.status(self.serve(trust_lan=True, with_access=False), {"Cf-Ray": "x"}), 401)
    def test_localhost_still_works_for_development(self):
        self.assertEqual(self.status(self.serve(with_access=False)), 200)

if __name__ == "__main__":
    unittest.main()
