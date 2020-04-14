import os,sys,shlex
import subprocess, threading
import shlex, json, time, copy
from .katrain import OUTPUT_ERROR, OUTPUT_DEBUG

class KataGoEngine:
    def __init__(self,config,logger):
        self.command = os.path.join(config["command"])
        self.logger = logger
        if "win" not in sys.platform:
            self.command = shlex.split(self.command)
        self.kata = None
        self.query_time = {}
        self.outstanding_analysis_queries = []  # allows faster interaction while kata is starting
        

    # engine main loop
    def _engine_thread(self):
        try:
            self.kata = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        except FileNotFoundError:
            self.logger(f"Starting kata with command '{self.command}' failed. If you are on Mac or Linux, please edit configuration file (config.json) to point to the correct KataGo executable.",OUTPUT_ERROR)  # fmt off
        self.analysis_thread = threading.Thread(target=self._analysis_read_thread, daemon=True).start()

    # analysis thread
    def _analysis_read_thread(self):
        while True:
            while self.outstanding_analysis_queries:
                self._send_analysis_query(self.outstanding_analysis_queries.pop(0))
            line = self.kata.stdout.readline()
            if not line:  # occasionally happens?
                return
            try:
                analysis = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"JSON decode error: '{e}' encountered after receiving input '{line}'")
                return
            if self.debug:
                print(f"[{time.time()-self.query_time.get(analysis['id'],0):.1f}] kata analysis received:", line[:80], "...")
            if "error" in analysis:
                if "AA" not in analysis["id"]:  # silently drop illegal moves from analysis all
                    print(analysis)
                    self.logger(f"ERROR IN KATA ANALYSIS: {analysis['error']}")
            else:
                self.board.store_analysis(analysis)
                self.update_evaluation()

    def _send_analysis_query(self, query):
        self.query_time[query["id"]] = time.time()
        query = {"rules": "japanese", "komi": self.komi, "boardXSize": self.board_size, "boardYSize": self.board_size, "analyzeTurns": [len(query["moves"])], **query}
        if self.kata:
            self.kata.stdin.write((json.dumps(query) + "\n").encode())
            self.kata.stdin.flush()
        else:  # early on / root / etc
            self.outstanding_analysis_queries.append(copy.copy(query))

    def _request_analysis(self, analysis_node: KaTrainSGFNode, faster=False, min_visits=0, priority=0):
        faster_fac = 5 if faster else 1
        node_id = analysis_node.id
        fast = self.ai_fast.active
        query = {
            "id": str(node_id),
            "moves": [[m.player, m.gtp()] for node in analysis_node.nodes_from_root for m in node.move_with_placements],
            "includeOwnership": True,
            "maxVisits": max(min_visits, self.visits[fast][1] // faster_fac),
            "priority": priority,
        }
        if self.debug:
            print(f"sending query for move {node_id}: {str(query)[:80]}")
        self._send_analysis_query(query)
        query.update({"id": f"PASS_{node_id}", "maxVisits": self.visits[fast][0] // faster_fac, "includeOwnership": False})
        query["moves"] += [[analysis_node.next_player, "pass"]]
        self._send_analysis_query(query)
