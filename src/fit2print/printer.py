"""Talk to a Bambu printer on the local network: its status (MQTT over TLS, port 8883) and its camera (a JPEG stream over TLS, port 6000).
Both use the printer's LAN access code. Read-only: it subscribes to the printer's own report and asks it to repeat its status ("pushall");
it never sends a command that moves, heats or stops anything.

The MQTT client is a few dozen lines on purpose (no outside library): CONNECT, SUBSCRIBE, one PUBLISH, and reading PUBLISH packets back."""
import json, os, socket, ssl, struct, threading, time

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

STATES = {"IDLE": "idle", "RUNNING": "printing", "PAUSE": "paused", "FINISH": "finished", "FAILED": "failed", "PREPARE": "preparing", "SLICING": "preparing", "INIT": "starting"}

def load_printer(path=None):
    """Printer settings from a file only the user can read (host, serial, access_code), or None. The access code is never printed or logged."""
    path = path or os.path.expanduser("~/.config/fit2print/printer.toml")
    if not os.path.exists(path) or tomllib is None:
        return None
    with open(path, "rb") as f:
        d = tomllib.load(f).get("printer", {})
    if not all(d.get(k) for k in ("host", "serial", "access_code")):
        return None
    return d

def _utf(s):
    b = s.encode()
    return struct.pack(">H", len(b)) + b

def _varlen(n):
    out = bytearray()
    while True:
        d, n = n % 128, n // 128
        out.append(d | (128 if n else 0))
        if not n:
            return bytes(out)

def _read_exact(sock, n):
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c:
            raise ConnectionError("the printer closed the connection")
        buf += c
    return buf

def _read_packet(sock):
    first = _read_exact(sock, 1)[0]
    mult, length = 1, 0
    while True:
        b = _read_exact(sock, 1)[0]
        length += (b & 127) * mult
        if not b & 128:
            break
        mult *= 128
    return first, _read_exact(sock, length) if length else b""

def mqtt_report(host, serial, code, port=8883, tls=True, wait=8.0):
    """Connect, ask for the full status and return the 'print' dict from the printer's report. Raises PermissionError for a wrong access code,
    TimeoutError if nothing arrived, ConnectionError/OSError if the printer cannot be reached."""
    raw = socket.create_connection((host, port), timeout=6)
    sock = raw
    if tls:
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE      # the printer's certificate is its own
        sock = ctx.wrap_socket(raw, server_hostname=host)
    sock.settimeout(4)
    try:
        body = _utf("MQTT") + bytes([4, 0xC2]) + struct.pack(">H", 60) + _utf("fit2print-" + str(os.getpid())) + _utf("bblp") + _utf(code)
        sock.sendall(bytes([0x10]) + _varlen(len(body)) + body)
        first, pkt = _read_packet(sock)
        if first >> 4 != 2 or len(pkt) < 2:
            raise ConnectionError("unexpected reply from the printer")
        if pkt[1] != 0:
            raise PermissionError("the printer refused the access code")
        topic = f"device/{serial}/report"
        sub = struct.pack(">H", 1) + _utf(topic) + b"\x00"
        sock.sendall(bytes([0x82]) + _varlen(len(sub)) + sub)
        req = _utf(f"device/{serial}/request") + json.dumps({"pushing": {"sequence_id": "0", "command": "pushall", "version": 1, "push_target": 1}}).encode()
        sock.sendall(bytes([0x30]) + _varlen(len(req)) + req)
        end, merged = time.time() + wait, {}
        while time.time() < end:
            sock.settimeout(max(0.2, min(4.0, end - time.time())))      # never wait past the budget for one more packet
            try:
                first, pkt = _read_packet(sock)
            except socket.timeout:
                continue
            if first >> 4 != 3:
                continue
            tl = struct.unpack(">H", pkt[:2])[0]
            off = 2 + tl + (2 if (first >> 1) & 3 else 0)
            try:
                d = json.loads(pkt[off:].decode("utf-8", "replace")).get("print")
            except ValueError:
                continue
            if d:
                merged.update(d)
                if "gcode_state" in merged and "mc_percent" in merged:
                    return merged
        if merged.get("gcode_state"):
            return merged
        raise TimeoutError("the printer did not report its status")
    finally:
        try:
            sock.close()
        except OSError:
            pass

def summarise(rep):
    """The fields the page shows, from a raw report."""
    st = STATES.get(str(rep.get("gcode_state", "")).upper(), str(rep.get("gcode_state", "unknown")).lower())
    return dict(state=st, job=rep.get("subtask_name") or str(rep.get("gcode_file", "")).rsplit("/", 1)[-1].replace(".gcode", "").replace(".3mf", ""),
                percent=rep.get("mc_percent"), layer=rep.get("layer_num"), layers=rep.get("total_layer_num"),
                minutes_left=rep.get("mc_remaining_time"), nozzle=rep.get("nozzle_temper"), bed=rep.get("bed_temper"),
                errors=int(rep.get("print_error") or 0) != 0 or bool(rep.get("hms")))

def camera_frame(host, code, port=6000, tls=True, timeout=10):
    """One JPEG frame from the printer's camera."""
    raw = socket.create_connection((host, port), timeout=timeout)
    sock = raw
    if tls:
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        sock = ctx.wrap_socket(raw, server_hostname=host)
    sock.settimeout(timeout)
    try:
        sock.sendall(struct.pack("<IIQ", 0x40, 0x3000, 0) + b"bblp".ljust(32, b"\0") + code.encode().ljust(32, b"\0"))
        hdr = _read_exact(sock, 16)
        n = struct.unpack("<I", hdr[:4])[0]
        if n <= 0 or n > 5_000_000:
            raise ConnectionError("the camera sent nonsense (wrong access code?)")
        img = _read_exact(sock, n)
        if img[:2] != b"\xff\xd8":
            raise ConnectionError("the camera did not send a JPEG")
        return img
    finally:
        try:
            sock.close()
        except OSError:
            pass

class Printer:
    """What the page uses: a status refreshed in the background (the page never waits for the printer) and a camera frame on demand."""
    def __init__(self, cfg, every=20, mqtt_port=8883, cam_port=6000, tls=True):
        self.cfg, self.every, self.mqtt_port, self.cam_port, self.tls = cfg, every, mqtt_port, cam_port, tls
        self.last = dict(state="unknown", error="not asked yet", at=0)
        self._frame, self._frame_at, self._lock = None, 0, threading.Lock()
        self._stop = threading.Event()
    def refresh(self):
        try:
            rep = mqtt_report(self.cfg["host"], self.cfg["serial"], self.cfg["access_code"], self.mqtt_port, self.tls)
            s = summarise(rep); s["at"] = time.time(); s["error"] = ""
        except PermissionError:
            s = dict(state="unknown", error="the printer refused the access code", at=time.time())
        except Exception as e:
            s = dict(state="offline", error="can not reach the printer (" + type(e).__name__ + ")", at=time.time())
        self.last = s
        return s
    def start(self):
        def loop():
            while not self._stop.is_set():
                self.refresh()
                self._stop.wait(self.every)
        threading.Thread(target=loop, daemon=True).start()
    def stop(self):
        self._stop.set()
    def frame(self, max_age=8):
        with self._lock:
            if self._frame is None or time.time() - self._frame_at > max_age:
                self._frame = camera_frame(self.cfg["host"], self.cfg["access_code"], self.cam_port, self.tls)
                self._frame_at = time.time()
            return self._frame
