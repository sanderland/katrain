"""Remote KataGo Analysis Engine over WebSocket.

When `engine.remote_url` is set in the config, KaTrain runs queries
against a remote KataGo Analysis Engine instead of spawning a local
subprocess. The server is expected to expose the KataGo Analysis
Engine JSON protocol over a WebSocket.

Generic transport — any KataGo-compatible server works. KaTrain has
no awareness of who hosts the engine.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback

import certifi
from websocket import (  # provided by `websocket-client`
    ABNF,
    WebSocket,
    WebSocketException,
    WebSocketTimeoutException,
    create_connection,
)

from katrain.core.constants import (
    OUTPUT_DEBUG,
    OUTPUT_ERROR,
    OUTPUT_EXTRA_DEBUG,
    OUTPUT_INFO,
    STATUS_INFO,
)
from katrain.core.engine import BaseEngine, KataGoEngine
from katrain.core.lang import i18n
from katrain.core.utils import json_truncate_arrays


class RemoteKataGoEngine(KataGoEngine):
    """KataGo engine that talks to a remote Analysis Engine server
    over a WebSocket instead of spawning a local subprocess.

    Activated when `engine.remote_url` in the config is non-empty.
    The URL must be `ws://...` or `wss://...`.
    """

    READ_TIMEOUT_S = 120

    def __init__(self, katrain, config):
        # Bypass KataGoEngine.__init__'s subprocess setup; initialise
        # only the bookkeeping the rest of KaTrain reads.
        BaseEngine.__init__(self, katrain, config)
        self.allow_recovery = self.config.get("allow_recovery", True)
        self.queries = {}
        self.ponder_query = None
        self.query_counter = 0
        self.katago_process = None  # rest of the codebase checks this
        self.base_priority = 0
        self.override_settings = {"reportAnalysisWinratesAs": "BLACK"}
        self.write_queue = queue.Queue()
        self.thread_lock = threading.Lock()
        self.shell = False
        self.command = "<remote websocket>"

        self.remote_url = (config.get("remote_url") or "").strip()
        if not self.remote_url:
            self.on_error(
                i18n._("Remote KataGo URL is empty"),
                "REMOTE-URL-MISSING",
                allow_popup=False,
            )
            return
        if not self.remote_url.startswith(("ws://", "wss://")):
            self.on_error(
                i18n._("Remote KataGo URL must start with ws:// or wss://"),
                "REMOTE-URL-INVALID",
                allow_popup=False,
            )
            return

        self.ws: WebSocket | None = None
        self.ws_send_lock = threading.Lock()
        self.analysis_thread = None
        self.write_stdin_thread = None
        self.stderr_thread = None
        self._closing = False
        self._reported_dead = False

        self.start()

    def start(self):
        with self.thread_lock:
            self.write_queue = queue.Queue()
            self._closing = False
            self._reported_dead = False
            try:
                self.katrain.log(
                    f"Connecting to remote KataGo at {self.remote_url}",
                    OUTPUT_DEBUG,
                )
                # macOS's bundled Python may have no configured CA bundle,
                # so provide certifi explicitly for secure WebSockets.
                sslopt = {"ca_certs": certifi.where()} if self.remote_url.startswith("wss://") else None
                self.ws = create_connection(
                    self.remote_url,
                    timeout=self.READ_TIMEOUT_S,
                    enable_multithread=True,
                    sslopt=sslopt,
                )
            except Exception as e:
                self.on_error(
                    i18n._("Connecting to remote KataGo failed").format(
                        url=self.remote_url,
                        error=e,
                    ),
                    code="REMOTE-CONNECT",
                )
                self.ws = None
                return

            self.analysis_thread = threading.Thread(
                target=self._analysis_read_thread,
                daemon=True,
            )
            self.write_stdin_thread = threading.Thread(
                target=self._write_stdin_thread,
                daemon=True,
            )
            # Dummy stderr thread so callers that join all three don't
            # crash on None — remote engines have no stderr channel.
            self.stderr_thread = threading.Thread(
                target=lambda: None,
                daemon=True,
            )
            self.analysis_thread.start()
            self.write_stdin_thread.start()
            self.stderr_thread.start()

    def shutdown(self, finish=False):
        self._closing = True
        ws = self.ws
        if finish and ws is not None:
            self.wait_to_finish()
        self.ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if finish is not None:
            for t in [self.write_stdin_thread, self.analysis_thread, self.stderr_thread]:
                if t and t.is_alive():
                    t.join(timeout=2.0)

    def wait_to_finish(self):
        while self.queries and self.ws is not None:
            time.sleep(0.1)

    def check_alive(self, os_error="", exception_if_dead=False, maybe_open_recovery=False):
        ok = self.ws is not None and not self._closing
        if not ok and exception_if_dead and not self._reported_dead:
            self._reported_dead = True
            self.on_error(
                i18n._("Remote KataGo engine disconnected").format(error=os_error),
                code="REMOTE-DISCONNECTED",
                allow_popup=maybe_open_recovery,
            )
            self.ws = None
        return ok

    def _read_stderr_thread(self):
        # Remote engines have no stderr channel; warnings come via the
        # `warning` field on responses. Override prevents the parent's
        # stderr thread from reading from a None process.
        return

    def _write_stdin_thread(self):
        """Pop (query, callback, error_callback, next_move, node)
        tuples off write_queue, register the callback in self.queries
        so the read thread can match responses by id, then send the
        JSON query over the WebSocket. Ponder dedupe lives inside the
        lock so rapid Ponder presses don't queue duplicate analyses.
        """
        while self.ws is not None and not self._closing:
            try:
                query, callback, error_callback, next_move, node = self.write_queue.get(
                    block=True,
                    timeout=0.1,
                )
            except queue.Empty:
                continue
            ws = self.ws
            if ws is None:
                return
            with self.thread_lock:
                if "id" not in query:
                    self.query_counter += 1
                    query["id"] = f"QUERY:{self.query_counter}"

                ponder = query.pop(self.PONDER_KEY, False)
                if ponder:
                    pq = self.ponder_query or {}
                    differences = {
                        k: (pq.get(k), query.get(k))
                        for k in (query.keys() | pq.keys()) - {"id", "maxVisits", "reportDuringSearchEvery"}
                        if pq.get(k) != query.get(k)
                    }
                    if differences:
                        self.stop_pondering()
                        query["maxVisits"] = 10_000_000
                        from katrain.core.constants import PONDERING_REPORT_DT

                        query["reportDuringSearchEvery"] = PONDERING_REPORT_DT
                        self.ponder_query = query
                    else:
                        continue

                terminate = query.get("action") == "terminate"
                if not terminate:
                    self.queries[query["id"]] = (
                        callback,
                        error_callback,
                        time.time(),
                        next_move,
                        node,
                    )
                tag = "ponder " if ponder else ("terminate " if terminate else "")
                self.katrain.log(
                    f"Sending {tag}query {query['id']}: {json.dumps(query)}",
                    OUTPUT_DEBUG,
                )
                try:
                    payload = json.dumps(query)
                    with self.ws_send_lock:
                        ws.send(payload)
                except WebSocketException as e:
                    self.ws = None
                    self.check_alive(
                        os_error=str(e),
                        exception_if_dead=True,
                        maybe_open_recovery=True,
                    )
                    return
                except Exception as e:
                    self.ws = None
                    self.katrain.log(
                        f"Unexpected exception sending to remote KataGo: {e}",
                        OUTPUT_ERROR,
                    )
                    traceback.print_exc()
                    return

    def _analysis_read_thread(self):
        """Read JSON responses from the WebSocket and dispatch to the
        matching callbacks in self.queries."""
        while self.ws is not None and not self._closing:
            ws = self.ws
            try:
                # recv_data(control_frame=True) lets us inspect non-text frames
                # (e.g. close, whose payload carries the status code + reason).
                opcode, data = ws.recv_data(control_frame=True)
            except WebSocketTimeoutException:
                continue
            except WebSocketException as e:
                if self._closing:
                    return
                self.ws = None
                self.check_alive(os_error=str(e), exception_if_dead=True, maybe_open_recovery=True)
                return
            except Exception as e:
                self.ws = None
                self.katrain.log(
                    f"Unexpected exception reading from remote KataGo: {e}",
                    OUTPUT_ERROR,
                )
                traceback.print_exc()
                return

            if opcode == ABNF.OPCODE_CLOSE:
                if not self._closing:
                    # RFC 6455 close payload: 2-byte status code + UTF-8 reason.
                    reason = "closed by remote"
                    if data and len(data) >= 2:
                        reason = data[2:].decode("utf-8", errors="replace").strip() or reason
                    self.ws = None
                    self.check_alive(
                        os_error=reason,
                        exception_if_dead=True,
                        maybe_open_recovery=True,
                    )
                return

            if opcode not in (ABNF.OPCODE_TEXT, ABNF.OPCODE_BINARY):
                # ping/pong/continuation — nothing to dispatch.
                continue

            if not data:
                continue

            raw = data.decode("utf-8") if isinstance(data, bytes) else data

            # A frame may contain multiple newline-delimited JSON
            # objects (matches KataGo's stdio framing).
            for line in str(raw).splitlines():
                line = line.strip()
                if not line:
                    continue
                self._dispatch_response_line(line)

    def _dispatch_response_line(self, line: str) -> None:
        """Parse one JSON response line and dispatch to the matching
        query callback. Warning text is mirrored to the UI status
        panel so users see notices like "visits capped" without
        reading the log."""
        try:
            analysis = json.loads(line)
        except json.JSONDecodeError as e:
            self.katrain.log(
                f"Bad JSON from remote KataGo: {e} (line: {line[:200]!r})",
                OUTPUT_ERROR,
            )
            return

        try:
            if "id" not in analysis:
                self.katrain.log(
                    f"Error without ID {analysis} received from remote KataGo",
                    OUTPUT_ERROR,
                )
                return

            query_id = analysis["id"]
            if query_id not in self.queries:
                if analysis.get("action") != "terminate":
                    self.katrain.log(
                        f"Query result {query_id} discarded -- recent new game or node reset?",
                        OUTPUT_DEBUG,
                    )
                return

            callback, error_callback, start_time, next_move, _ = self.queries[query_id]

            # Handled BEFORE the dispatch chain so analysis data
            # alongside a warning still reaches the callback.
            if "warning" in analysis:
                warning_text = str(analysis.get("warning"))
                self.katrain.log(
                    f"Remote KataGo warning: {warning_text}",
                    OUTPUT_INFO,
                )
                try:
                    self.katrain.controls.set_status(warning_text, STATUS_INFO)
                except Exception:
                    pass

            if "error" in analysis:
                del self.queries[query_id]
                if error_callback:
                    error_callback(analysis)
                elif not (next_move and "Illegal move" in analysis["error"]):
                    self.katrain.log(
                        f"{analysis} received from remote KataGo",
                        OUTPUT_ERROR,
                    )
            elif "terminateId" in analysis:
                self.katrain.log(
                    f"{analysis} received from remote KataGo",
                    OUTPUT_DEBUG,
                )
            else:
                partial_result = analysis.get("isDuringSearch", False)
                if not partial_result:
                    del self.queries[query_id]
                time_taken = time.time() - start_time
                results_exist = not analysis.get("noResults", False)
                self.katrain.log(
                    f"[{time_taken:.1f}][{query_id}][{'....' if partial_result else 'done'}] "
                    f"KataGo analysis received: {len(analysis.get('moveInfos', []))} "
                    f"candidate moves, "
                    f"{analysis['rootInfo']['visits'] if results_exist else 'n/a'} visits",
                    OUTPUT_DEBUG,
                )
                self.katrain.log(json_truncate_arrays(analysis), OUTPUT_EXTRA_DEBUG)
                try:
                    if callback and results_exist:
                        callback(analysis, partial_result)
                except Exception as e:
                    self.katrain.log(
                        f"Error in engine callback for query {query_id}: {e}",
                        OUTPUT_ERROR,
                    )
                    traceback.print_exc()

            if getattr(self.katrain, "update_state", None):
                self.katrain.update_state()
        except Exception as e:
            self.katrain.log(
                f"Unexpected exception {e} processing remote KataGo output: {line[:200]!r}",
                OUTPUT_ERROR,
            )
            traceback.print_exc()


def make_engine(katrain, config):
    """Return RemoteKataGoEngine if `engine.remote_url` is set,
    otherwise the normal local-subprocess KataGoEngine."""
    if (config.get("remote_url") or "").strip():
        return RemoteKataGoEngine(katrain, config)
    return KataGoEngine(katrain, config)
