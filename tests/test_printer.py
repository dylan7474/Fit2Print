import json, socket, struct, threading, unittest
from fit2print import printer

REPORT = {"print": {"gcode_state": "RUNNING", "mc_percent": 54, "layer_num": 311, "total_layer_num": 579, "mc_remaining_time": 160,
                    "nozzle_temper": 220.0, "bed_temper": 65.0, "subtask_name": "pod_L", "print_error": 0}}

def _varlen(n):
    return printer._varlen(n)

class FakeBroker:
    """A minimal MQTT broker that behaves like the printer: CONNACK, SUBACK, then a report after it is asked (pushall)."""
    def __init__(self, code="12345678", rc_if_wrong=5, report=REPORT, silent=False):
        self.code, self.rc_wrong, self.report, self.silent = code, rc_if_wrong, report, silent
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(1); self.port = self.srv.getsockname()[1]
        self.got = []
        threading.Thread(target=self.run, daemon=True).start()
    def run(self):
        c, _ = self.srv.accept(); c.settimeout(5)
        try:
            first, pkt = printer._read_packet(c)
            # parse CONNECT: skip protocol name(6) level flags keepalive(2)=4 -> then client id, user, password
            off = 2 + 4 + 1 + 1 + 2
            n = struct.unpack(">H", pkt[off:off + 2])[0]; off += 2 + n
            n = struct.unpack(">H", pkt[off:off + 2])[0]; off += 2 + n
            n = struct.unpack(">H", pkt[off:off + 2])[0]; pw = pkt[off + 2:off + 2 + n].decode()
            if pw != self.code:
                c.sendall(bytes([0x20, 2, 0, self.rc_wrong])); return
            c.sendall(bytes([0x20, 2, 0, 0]))
            first, pkt = printer._read_packet(c)                       # SUBSCRIBE
            c.sendall(bytes([0x90, 3]) + pkt[:2] + b"\x00")
            first, pkt = printer._read_packet(c)                       # PUBLISH pushall
            self.got.append(pkt)
            if self.silent:
                import time; time.sleep(3)                                  # a quiet printer keeps the connection open
            else:
                body = printer._utf("device/SER/report") + json.dumps(self.report).encode()
                c.sendall(bytes([0x30]) + _varlen(len(body)) + body)
                import time; time.sleep(0.3)
        except Exception:
            pass
        finally:
            c.close(); self.srv.close()

class Mqtt(unittest.TestCase):
    def test_reads_the_status(self):
        b = FakeBroker()
        rep = printer.mqtt_report("127.0.0.1", "SER", "12345678", port=b.port, tls=False, wait=4)
        s = printer.summarise(rep)
        self.assertEqual((s["state"], s["percent"], s["layer"], s["layers"], s["minutes_left"], s["job"]), ("printing", 54, 311, 579, 160, "pod_L"))
        self.assertIn(b"pushall", b.got[0])
    def test_it_only_asks_for_status_and_never_commands_the_printer(self):   # the one thing it sends: pushall
        b = FakeBroker()
        printer.mqtt_report("127.0.0.1", "SER", "12345678", port=b.port, tls=False, wait=4)
        msg = json.loads(b.got[0][2 + len("device/SER/request"):])
        self.assertEqual(list(msg), ["pushing"]); self.assertEqual(msg["pushing"]["command"], "pushall")
    def test_a_wrong_access_code_is_reported_as_such(self):    # NEGATIVE CONTROL
        b = FakeBroker()
        with self.assertRaises(PermissionError):
            printer.mqtt_report("127.0.0.1", "SER", "wrong", port=b.port, tls=False, wait=2)
    def test_a_silent_printer_times_out_cleanly(self):
        b = FakeBroker(silent=True)
        with self.assertRaises(TimeoutError):
            printer.mqtt_report("127.0.0.1", "SER", "12345678", port=b.port, tls=False, wait=1.5)
    def test_summarise_other_states(self):
        self.assertEqual(printer.summarise({"gcode_state": "FINISH"})["state"], "finished")
        self.assertEqual(printer.summarise({"gcode_state": "FAILED"})["state"], "failed")
        self.assertTrue(printer.summarise({"gcode_state": "RUNNING", "print_error": 50348044})["errors"])

class Camera(unittest.TestCase):
    def serve(self, payload):
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        def run():
            c, _ = srv.accept(); printer._read_exact(c, 80)
            if payload is not None: c.sendall(payload)
            c.close(); srv.close()
        threading.Thread(target=run, daemon=True).start()
        return srv.getsockname()[1]
    def test_gets_a_jpeg(self):
        img = b"\xff\xd8\xff\xe0" + b"1" * 100
        port = self.serve(struct.pack("<IIII", len(img), 0, 1, 0) + img)
        self.assertEqual(printer.camera_frame("127.0.0.1", "x", port, tls=False), img)
    def test_rejects_something_that_is_not_a_jpeg(self):      # NEGATIVE CONTROL
        junk = b"NOTAJPEG" * 10
        port = self.serve(struct.pack("<IIII", len(junk), 0, 1, 0) + junk)
        with self.assertRaises(ConnectionError):
            printer.camera_frame("127.0.0.1", "x", port, tls=False)
    def test_rejects_an_absurd_length(self):
        port = self.serve(struct.pack("<IIII", 999_999_999, 0, 1, 0))
        with self.assertRaises(ConnectionError):
            printer.camera_frame("127.0.0.1", "x", port, tls=False)

class Wrapper(unittest.TestCase):
    def test_offline_printer_gives_a_state_not_an_exception(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()      # a port with nothing listening
        p = printer.Printer(dict(host="127.0.0.1", serial="S", access_code="x"), mqtt_port=port, tls=False)
        st = p.refresh()
        self.assertEqual(st["state"], "offline"); self.assertIn("can not reach", st["error"])
    def test_the_status_never_contains_the_access_code(self):
        b = FakeBroker(); p = printer.Printer(dict(host="127.0.0.1", serial="SER", access_code="12345678"), mqtt_port=b.port, tls=False)
        self.assertNotIn("12345678", json.dumps(p.refresh()))

if __name__ == "__main__":
    unittest.main()
