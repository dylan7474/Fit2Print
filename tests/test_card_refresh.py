"""Real-browser test: after the assistant draws a picture, the 'What it should look like' card shows it WITHOUT reloading the page.
(Found 2026-10-31: the card was drawn once when the page loaded, so on the concept stage the pictures only showed after a manual reload.)
Skipped when there is no Chrome or no websockets library."""
import asyncio, json, os, shutil, subprocess, sys, tempfile, threading, time, unittest, urllib.request
from fit2print import server, project, assistant
try:
    import websockets
except ImportError:
    websockets = None
CHROME = shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")
FAKE = [sys.executable, os.path.join(os.path.dirname(__file__), "fake_claude.py")]

@unittest.skipUnless(CHROME and websockets, "needs Chrome and the websockets library")
class CardRefresh(unittest.TestCase):
    def test_pictures_appear_without_a_reload(self):
        d = tempfile.mkdtemp(); f = os.path.join(d, "p"); project.init(f, "Pic Browser Test")
        a = assistant.Assistant(command=FAKE, model="sonnet", budget_usd=0.5, f2p="fit2print")
        srv = server.make_server(dict(projects=[f], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0, assistant=a); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        result = {}
        async def main():
            cport = 9378; prof = tempfile.mkdtemp()
            p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={cport}", f"--user-data-dir={prof}", "--window-size=1200,1400", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try: tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{cport}/json")); break
                    except Exception: time.sleep(0.2)
                ws_url = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
                async with websockets.connect(ws_url, max_size=50_000_000) as ws:
                    n = 0
                    async def call(m, **pr):
                        nonlocal n; n += 1; await ws.send(json.dumps({"id": n, "method": m, "params": pr}))
                        while True:
                            x = json.loads(await ws.recv())
                            if x.get("id") == n: return x.get("result", x)
                    async def js(e):
                        r = await call("Runtime.evaluate", expression=e, awaitPromise=True, returnByValue=True); return r.get("result", {}).get("value")
                    await call("Runtime.enable"); await call("Page.enable")
                    await call("Page.navigate", url=f"http://127.0.0.1:{port}/p/pic-browser-test")
                    for _ in range(60):
                        await asyncio.sleep(0.5)
                        if await js("document.readyState==='complete' && !!document.getElementById('msg')"): break
                    result["before"] = await js("document.querySelectorAll('#rcard img').length")
                    await js("window.__no_reload_marker = 1")
                    async def center(sel):
                        return await js(f"(()=>{{const b=document.querySelector({json.dumps(sel)}).getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2]}})()")
                    await js("document.querySelector('#msg').scrollIntoView({block:'center'})"); await asyncio.sleep(0.3)
                    for sel, text in (("#msg", "please DRAW the concept"), ("#sendbtn", None)):
                        x, y = await center(sel)
                        for t in ("mouseMoved", "mousePressed", "mouseReleased"): await call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
                        if text: await call("Input.insertText", text=text); await asyncio.sleep(0.3)
                    for _ in range(14):
                        await asyncio.sleep(1)
                        result["after"] = await js("document.querySelectorAll('#rcard img').length")
                        if result["after"]: break
                    result["no_reload"] = await js("window.__no_reload_marker===1")
            finally:
                p.terminate()
        asyncio.run(main()); srv.shutdown()
        self.assertEqual(result["before"], 0)
        self.assertEqual(result["after"], 1, "the picture the assistant drew never appeared in the card")
        self.assertTrue(result["no_reload"], "the page had to reload to show it")

if __name__ == "__main__":
    unittest.main()
