#!/usr/bin/env python3
"""Exercise the local viewer in headless Chrome through the DevTools protocol."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_json(url: str, timeout_seconds: float = 15.0) -> object:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                return json.load(response)
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


class CdpSession:
    def __init__(self, websocket: websockets.ClientConnection) -> None:
        self.websocket = websocket
        self.next_id = 1
        self.events: list[dict] = []

    async def command(self, method: str, params: dict | None = None) -> dict:
        command_id = self.next_id
        self.next_id += 1
        await self.websocket.send(
            json.dumps({"id": command_id, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(await self.websocket.recv())
            if message.get("id") == command_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    async def evaluate(self, expression: str) -> object:
        result = await self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        payload = result.get("result", {})
        if payload.get("subtype") == "error":
            raise RuntimeError(payload.get("description", "JavaScript evaluation error"))
        return payload.get("value")


async def exercise_viewer(websocket_url: str, page_url: str, screenshot_path: Path) -> dict:
    async with websockets.connect(websocket_url, max_size=32 * 1024 * 1024) as websocket:
        cdp = CdpSession(websocket)
        await cdp.command("Runtime.enable")
        await cdp.command("Page.enable")
        await cdp.command("Log.enable")
        await cdp.command("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        await cdp.command("Page.navigate", {"url": page_url})

        deadline = time.monotonic() + 20.0
        ready = False
        while time.monotonic() < deadline:
            ready = bool(
                await cdp.evaluate(
                    "document.readyState === 'complete' && typeof data !== 'undefined' && data.edges.length === 18468"
                )
            )
            if ready:
                break
            await asyncio.sleep(0.1)
        if not ready:
            raise RuntimeError("Viewer did not reach its expected loaded state")

        initial = await cdp.evaluate(
            "({title:document.title, edges:data.edges.length, legend:Object.keys(data.metadata.legend).length, canvas:[canvas.width,canvas.height], info:info.innerText})"
        )

        searched_edge = "E_N001012_N002152"
        search_result = await cdp.evaluate(
            f"search.value='{searched_edge}'; search.dispatchEvent(new Event('input',{{bubbles:true}})); info.innerText"
        )
        default_screenshot = await cdp.command(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
        )
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(base64.b64decode(default_screenshot["data"]))

        toggle_result = await cdp.evaluate(
            "(() => { const box=document.querySelector('input[data-class=\"possible_unintended_missing\"]'); box.checked=false; box.dispatchEvent(new Event('change',{bubbles:true})); return {checked:box.checked,visible:visible.possible_unintended_missing}; })()"
        )

        zoom_result = await cdp.evaluate(
            "(() => { const before=zoom; canvas.dispatchEvent(new WheelEvent('wheel',{deltaY:-100,bubbles:true,cancelable:true})); return {before,after:zoom}; })()"
        )
        reset_result = await cdp.evaluate(
            "(() => { document.getElementById('reset').click(); return {rotX,rotY,zoom}; })()"
        )
        focused_state = await cdp.evaluate(
            "(() => { const keep=new Set(['possible_unintended_missing','possible_unintended_disconnected','designed_removed']); for (const box of document.querySelectorAll('input[data-class]')) { const state=keep.has(box.dataset.class); box.checked=state; box.dispatchEvent(new Event('change',{bubbles:true})); } return Object.fromEntries(Object.entries(visible)); })()"
        )
        focused_screenshot_path = screenshot_path.with_name("viewer_defects_only.png")
        focused_screenshot = await cdp.command(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
        )
        focused_screenshot_path.write_bytes(base64.b64decode(focused_screenshot["data"]))

        logged_errors = [
            event
            for event in cdp.events
            if event.get("method") in {"Log.entryAdded", "Runtime.exceptionThrown"}
            and (
                event.get("method") == "Runtime.exceptionThrown"
                or event.get("params", {}).get("entry", {}).get("level") == "error"
            )
        ]
        ignored_favicon_errors = [
            event
            for event in logged_errors
            if event.get("params", {}).get("entry", {}).get("url", "").endswith("/favicon.ico")
        ]
        errors = [event for event in logged_errors if event not in ignored_favicon_errors]

        checks = {
            "title": initial["title"] == "LLNL DSC Part 2 Defect Viewer",
            "edge_count": initial["edges"] == 18468,
            "legend_count": initial["legend"] == 7,
            "canvas_nonempty": initial["canvas"][0] > 0 and initial["canvas"][1] > 0,
            "search": searched_edge in str(search_result),
            "legend_toggle": toggle_result == {"checked": False, "visible": False},
            "wheel_zoom": zoom_result["after"] > zoom_result["before"],
            "reset": reset_result == {"rotX": -0.75, "rotY": 0.65, "zoom": 1},
            "console_errors": not errors,
            "screenshot": (
                screenshot_path.is_file()
                and screenshot_path.stat().st_size > 0
                and focused_screenshot_path.is_file()
                and focused_screenshot_path.stat().st_size > 0
            ),
        }
        return {
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
            "initial_state": initial,
            "search_result": search_result,
            "toggle_result": toggle_result,
            "zoom_result": zoom_result,
            "reset_result": reset_result,
            "focused_visible_classes": focused_state,
            "console_errors": errors,
            "ignored_favicon_errors": ignored_favicon_errors,
            "screenshots": {
                "default_with_search": str(screenshot_path),
                "defects_only": str(focused_screenshot_path),
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--viewer-dir",
        type=Path,
        default=Path("collaboration/part2_verification_handoff_20260727/viewer"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("Aman_Scripts/collaboration_codex/audit_outputs/browser"),
    )
    args = parser.parse_args()
    viewer_dir = args.viewer_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not CHROME.is_file():
        raise SystemExit(f"Google Chrome not found: {CHROME}")
    if not (viewer_dir / "index.html").is_file():
        raise SystemExit(f"Viewer index not found: {viewer_dir / 'index.html'}")

    http_port = free_port()
    debug_port = free_port()
    handler = lambda *handler_args, **handler_kwargs: QuietHandler(
        *handler_args, directory=str(viewer_dir), **handler_kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", http_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / "viewer_runtime.png"
    result_path = output_dir / "viewer_runtime_result.json"
    try:
        with tempfile.TemporaryDirectory(prefix="codex-viewer-chrome-") as profile:
            process = subprocess.Popen(
                [
                    str(CHROME),
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--no-first-run",
                    f"--remote-debugging-port={debug_port}",
                    f"--user-data-dir={profile}",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                tabs = wait_for_json(f"http://127.0.0.1:{debug_port}/json/list")
                page = next(item for item in tabs if item.get("type") == "page")
                result = asyncio.run(
                    exercise_viewer(
                        page["webSocketDebuggerUrl"],
                        f"http://127.0.0.1:{http_port}/",
                        screenshot_path,
                    )
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        server.shutdown()
        server.server_close()

    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
