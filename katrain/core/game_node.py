import base64
import copy
import gzip
import json
import random
from typing import Dict, List, Optional, Tuple

from katrain.core.constants import (
    ANALYSIS_FORMAT_VERSION,
    PROGRAM_NAME,
    REPORT_DT,
    SGF_INTERNAL_COMMENTS_MARKER,
    SGF_SEPARATOR_MARKER,
    VERSION,
    PRIORITY_DEFAULT,
    ADDITIONAL_MOVE_ORDER,
)
from katrain.core.lang import i18n
from katrain.core.sgf_parser import Move, SGFNode
from katrain.core.utils import evaluation_class, pack_floats, unpack_floats, var_to_grid
from katrain.gui.theme import Theme


def analysis_dumps(analysis):
    analysis = copy.deepcopy(analysis)
    for movedict in analysis["moves"].values():
        if "ownership" in movedict:  # per-move ownership rarely used
            del movedict["ownership"]
    ownership_data = pack_floats(analysis.pop("ownership"))
    policy_data = pack_floats(analysis.pop("policy"))
    main_data = json.dumps(analysis).encode("utf-8")
    return [
        base64.standard_b64encode(gzip.compress(data)).decode("utf-8")
        for data in [ownership_data, policy_data, main_data]
    ]


class GameNode(SGFNode):
    """Represents a single game node, with one or more moves and placements."""

    def __init__(self, parent=None, properties=None, move=None):
        super().__init__(parent=parent, properties=properties, move=move)
        self.auto_undo = None  # None = not analyzed. False: not undone (good move). True: undone (bad move)
        self.played_sound = None
        self.ai_thoughts = ""
        self.note = ""
        self.move_number = 0
        self.time_used = 0
        self.undo_threshold = random.random()  # for fractional undos
        self.end_state = None
        self.shortcuts_to = []
        self.shortcut_from = None
        self.analysis_from_sgf = None
        self.clear_analysis()

    def add_shortcut(self, to_node):  # collapses the branch between them
        nodes = [to_node]
        while nodes[-1].parent and nodes[-1] != self:  # ensure on path
            nodes.append(nodes[-1].parent)
        if nodes[-1] == self and len(nodes) > 2:
            via = nodes[-2]
            self.shortcuts_to.append((to_node, via))  # and first child
            to_node.shortcut_from = self

    def remove_shortcut(self):
        from_node = self.shortcut_from
        if from_node:
            from_node.shortcuts_to = [(m, v) for m, v in from_node.shortcuts_to if m != self]
            self.shortcut_from = None

    def load_analysis(self):
        if not self.analysis_from_sgf:
            return False
        try:
            szx, szy = self.root.board_size
            board_squares = szx * szy
            version = self.root.get_property("KTV", ANALYSIS_FORMAT_VERSION)
            if version > ANALYSIS_FORMAT_VERSION:
                raise ValueError(f"Can not decode analysis data with version {version}, please update {PROGRAM_NAME}")
            ownership_data, policy_data, main_data, *_ = [
                gzip.decompress(base64.standard_b64decode(data)) for data in self.analysis_from_sgf
            ]
            self.analysis = {
                **json.loads(main_data),
                "policy": unpack_floats(policy_data, board_squares + 1),
                "ownership": unpack_floats(ownership_data, board_squares),
            }
            return True
        except Exception as e:
            print(f"Error in loading analysis: {e}")
            return False

    def add_list_property(self, property: str, values: List):
        if property == "KT":
            self.analysis_from_sgf = values
        elif property == "C":
            comments = [  # strip out all previously auto generated comments
                c
                for v in values
                for c in v.split(SGF_SEPARATOR_MARKER)
                if c.strip() and SGF_INTERNAL_COMMENTS_MARKER not in c
            ]
            self.note = "".join(comments).strip()  # no super call intended, just save as note to be editable
        else:
            return super().add_list_property(property, values)

    def clear_analysis(self):
        self.analysis_visits_requested = 0
        self.analysis = {"moves": {}, "root": None, "ownership": None, "policy": None, "completed": False}

    def sgf_properties(
        self,
        save_comments_player=None,
        save_comments_class=None,
        eval_thresholds=None,
        save_analysis=False,
        save_marks=False,
    ):
        properties = copy.copy(super().sgf_properties())
        note = self.note.strip()
        if save_analysis and self.analysis_complete:
            try:
                properties["KT"] = analysis_dumps(self.analysis)
            except Exception as e:
                print(f"Error in saving analysis: {e}")
        if self.points_lost and save_comments_class is not None and eval_thresholds is not None:
            show_class = save_comments_class[evaluation_class(self.points_lost, eval_thresholds)]
        else:
            show_class = False
        comments = properties.get("C", [])
        if (
            self.parent
            and self.parent.analysis_exists
            and self.analysis_exists
            and (note or ((save_comments_player or {}).get(self.player, False) and show_class))
        ):
            if save_marks:
                candidate_moves = self.parent.candidate_moves
                top_x = Move.from_gtp(candidate_moves[0]["move"]).sgf(self.board_size)
                best_sq = [
                    Move.from_gtp(d["move"]).sgf(self.board_size)
                    for d in candidate_moves
                    if d["pointsLost"] <= 0.5 and d["move"] != "pass" and d["order"] != 0
                ]
                if best_sq and "SQ" not in properties:
                    properties["SQ"] = best_sq
                if top_x and "MA" not in properties:
                    properties["MA"] = [top_x]
            comments.append("\n" + self.comment(sgf=True, interactive=False) + SGF_INTERNAL_COMMENTS_MARKER)
        if self.is_root:
            if save_marks:
                comments = [i18n._("SGF start message") + SGF_INTERNAL_COMMENTS_MARKER + "\n"]
            else:
                comments = []
            comments += [
                *comments,
                f"\nSGF generated by {PROGRAM_NAME} {VERSION}{SGF_INTERNAL_COMMENTS_MARKER}\n",
            ]
            properties["CA"] = ["UTF-8"]
            properties["AP"] = [f"{PROGRAM_NAME}:{VERSION}"]
            properties["KTV"] = [ANALYSIS_FORMAT_VERSION]
        if self.shortcut_from:
            properties["KTSF"] = [id(self.shortcut_from)]
        elif "KTSF" in properties:
            del properties["KTSF"]
        if self.shortcuts_to:
            properties["KTSID"] = [id(self)]
        elif "KTSID" in properties:
            del properties["KTSID"]
        if note:
            comments.insert(0, f"{self.note}\n")  # user notes at top!
        if comments:
            properties["C"] = [SGF_SEPARATOR_MARKER.join(comments).strip("\n")]
        elif "C" in properties:
            del properties["C"]
        return properties

    @staticmethod
    def order_children(children):
        return sorted(
            children, key=lambda c: 0.5 if c.auto_undo is None else int(c.auto_undo)
        )  # analyzed/not undone main, non-teach second, undone last

    # various analysis functions
    def analyze(
        self,
        engine,
        priority=PRIORITY_DEFAULT,
        visits=None,
        ponder=False,
        time_limit=True,
        refine_move=None,
        analyze_fast=False,
        find_alternatives=False,
        region_of_interest=None,
        report_every=REPORT_DT,
    ):
        engine.request_analysis(
            self,
            callback=lambda result, partial_result: self.set_analysis(
                result, refine_move, find_alternatives, region_of_interest, partial_result
            ),
            priority=priority,
            visits=visits,
            ponder=ponder,
            analyze_fast=analyze_fast,
            time_limit=time_limit,
            next_move=refine_move,
            find_alternatives=find_alternatives,
            region_of_interest=region_of_interest,
            report_every=report_every,
        )

    def update_move_analysis(self, move_analysis, move_gtp):
        cur = self.analysis["moves"].get(move_gtp)
        if cur is None:
            self.analysis["moves"][move_gtp] = {
                "move": move_gtp,
                "order": ADDITIONAL_MOVE_ORDER,
                **move_analysis,
            }  # some default values for keys missing in rootInfo
        else:
            cur["order"] = min(
                cur["order"], move_analysis.get("order", ADDITIONAL_MOVE_ORDER)
            )  # parent arriving after child
            if cur["visits"] < move_analysis["visits"]:
                cur.update(move_analysis)
            else:  # prior etc only
                cur.update({k: v for k, v in move_analysis.items() if k not in cur})

    def set_analysis(
        self,
        analysis_json: Dict,
        refine_move: Optional[Move] = None,
        additional_moves: bool = False,
        region_of_interest=None,
        partial_result: bool = False,
    ):
        if refine_move:
            pvtail = analysis_json["moveInfos"][0]["pv"] if analysis_json["moveInfos"] else []
            self.update_move_analysis(
                {"pv": [refine_move.gtp()] + pvtail, **analysis_json["rootInfo"]}, refine_move.gtp()
            )
        else:
            if additional_moves:  # additional moves: old order matters, ignore new order
                for m in analysis_json["moveInfos"]:
                    del m["order"]
            elif refine_move is None:  # normal update: old moves to end, new order matters. also for region?
                for move_dict in self.analysis["moves"].values():
                    move_dict["order"] = ADDITIONAL_MOVE_ORDER  # old moves to end
            for move_analysis in analysis_json["moveInfos"]:
                self.update_move_analysis(move_analysis, move_analysis["move"])
            self.analysis["ownership"] = analysis_json.get("ownership")
            self.analysis["policy"] = analysis_json.get("policy")
            if not additional_moves and not region_of_interest:
                self.analysis["root"] = analysis_json["rootInfo"]
                if self.parent and self.move:
                    analysis_json["rootInfo"]["pv"] = [self.move.gtp()] + (
                        analysis_json["moveInfos"][0]["pv"] if analysis_json["moveInfos"] else []
                    )
                    self.parent.update_move_analysis(
                        analysis_json["rootInfo"], self.move.gtp()
                    )  # update analysis in parent for consistency
            is_normal_query = refine_move is None and not additional_moves
            self.analysis["completed"] = self.analysis["completed"] or (is_normal_query and not partial_result)

    @property
    def ownership(self):
        return self.analysis.get("ownership")

    @property
    def policy(self):
        return self.analysis.get("policy")

    @property
    def analysis_exists(self):
        return self.analysis["root"] is not None

    @property
    def analysis_complete(self):
        return self.analysis["completed"] and self.analysis["root"] is not None

    @property
    def root_visits(self):
        return ((self.analysis or {}).get("root") or {}).get("visits", 0)

    @property
    def score(self) -> Optional[float]:
        if self.analysis_exists:
            return self.analysis["root"].get("scoreLead")

    def format_score(self, score=None):
        score = score or self.score
        if score is not None:
            return f"{'B' if score >= 0 else 'W'}+{abs(score):.1f}"

    @property
    def winrate(self) -> Optional[float]:
        if self.analysis_exists:
            return self.analysis["root"].get("winrate")

    def format_winrate(self, win_rate=None):
        win_rate = win_rate or self.winrate
        if win_rate is not None:
            return f"{'B' if win_rate > 0.5 else 'W'} {max(win_rate,1-win_rate):.1%}"

    def move_policy_stats(self) -> Tuple[Optional[int], float, List]:
        single_move = self.move
        if single_move and self.parent:
            policy_ranking = self.parent.policy_ranking
            if policy_ranking:
                for ix, (p, m) in enumerate(policy_ranking):
                    if m == single_move:
                        return ix + 1, p, policy_ranking
        return None, 0.0, []

    def make_pv(self, player, pv, interactive):
        pvtext = f"{player}{' '.join(pv)}"
        if interactive:
            pvtext = f"[u][ref={pvtext}][color={Theme.INFO_PV_COLOR}]{pvtext}[/color][/ref][/u]"
        return pvtext

    def comment(self, sgf=False, teach=False, details=False, interactive=True):
        single_move = self.move
        if not self.parent or not single_move:  # root
            if self.root:
                rules = self.get_property("RU", "Japanese")
                if isinstance(rules, str):  # else katago dict
                    rules = i18n._(rules.lower())
                return f"{i18n._('komi')}: {self.komi:.1f}\n{i18n._('ruleset')}: {rules}\n"
            return ""

        text = i18n._("move").format(number=self.depth) + f": {single_move.player} {single_move.gtp()}\n"
        if self.analysis_exists:
            score = self.score
            if sgf:
                text += i18n._("Info:score").format(score=self.format_score(score)) + "\n"
                text += i18n._("Info:winrate").format(winrate=self.format_winrate()) + "\n"
            if self.parent and self.parent.analysis_exists:
                previous_top_move = self.parent.candidate_moves[0]
                if sgf or details:
                    if previous_top_move["move"] != single_move.gtp():
                        points_lost = self.points_lost
                        if sgf and points_lost > 0.5:
                            text += i18n._("Info:point loss").format(points_lost=points_lost) + "\n"
                        top_move = previous_top_move["move"]
                        score = self.format_score(previous_top_move["scoreLead"])
                        text += (
                            i18n._("Info:top move").format(
                                top_move=top_move,
                                score=score,
                            )
                            + "\n"
                        )
                    else:
                        text += i18n._("Info:best move") + "\n"
                    if previous_top_move.get("pv") and (sgf or details):
                        pv = self.make_pv(single_move.player, previous_top_move["pv"], interactive)
                        text += i18n._("Info:PV").format(pv=pv) + "\n"
                if sgf or details or teach:
                    currmove_pol_rank, currmove_pol_prob, policy_ranking = self.move_policy_stats()
                    if currmove_pol_rank is not None:
                        policy_rank_msg = i18n._("Info:policy rank")
                        text += policy_rank_msg.format(rank=currmove_pol_rank, probability=currmove_pol_prob) + "\n"
                    if currmove_pol_rank != 1 and policy_ranking and (sgf or details):
                        policy_best_msg = i18n._("Info:policy best")
                        pol_move, pol_prob = policy_ranking[0][1].gtp(), policy_ranking[0][0]
                        text += policy_best_msg.format(move=pol_move, probability=pol_prob) + "\n"
            if self.auto_undo and sgf:
                text += i18n._("Info:teaching undo") + "\n"
                top_pv = self.analysis_exists and self.candidate_moves[0].get("pv")
                if top_pv:
                    text += i18n._("Info:undo predicted PV").format(pv=f"{self.next_player}{' '.join(top_pv)}") + "\n"
        else:
            text = i18n._("No analysis available") if sgf else i18n._("Analyzing move...")

        if self.ai_thoughts and (sgf or details):
            text += "\n" + i18n._("Info:AI thoughts").format(thoughts=self.ai_thoughts)

        if "C" in self.properties:
            text += "\n[u]SGF Comments:[/u]\n" + "\n".join(self.properties["C"])

        return text

    @property
    def points_lost(self) -> Optional[float]:
        single_move = self.move
        if single_move and self.parent and self.analysis_exists and self.parent.analysis_exists:
            parent_score = self.parent.score
            score = self.score
            return self.player_sign(single_move.player) * (parent_score - score)

    @property
    def parent_realized_points_lost(self) -> Optional[float]:
        single_move = self.move
        if (
            single_move
            and self.parent
            and self.parent.parent
            and self.analysis_exists
            and self.parent.parent.analysis_exists
        ):
            parent_parent_score = self.parent.parent.score
            score = self.score
            return self.player_sign(single_move.player) * (score - parent_parent_score)

    @staticmethod
    def player_sign(player):
        return {"B": 1, "W": -1, None: 0}[player]

    @property
    def candidate_moves(self) -> List[Dict]:
        if not self.analysis_exists:
            return []
        if not self.analysis["moves"]:
            polmoves = self.policy_ranking
            top_polmove = polmoves[0][1] if polmoves else Move(None)  # if no info at all, pass
            return [
                {
                    **self.analysis["root"],
                    "pointsLost": 0,
                    "winrateLost": 0,
                    "order": 0,
                    "move": top_polmove.gtp(),
                    "pv": [top_polmove.gtp()],
                }
            ]  # single visit -> go by policy/root

        root_score = self.analysis["root"]["scoreLead"]
        root_winrate = self.analysis["root"]["winrate"]
        move_dicts = list(self.analysis["moves"].values())  # prevent incoming analysis from causing crash
        top_move = [d for d in move_dicts if d["order"] == 0]
        top_score_lead = top_move[0]["scoreLead"] if top_move else root_score
        return sorted(
            [
                {
                    "pointsLost": self.player_sign(self.next_player) * (root_score - d["scoreLead"]),
                    "relativePointsLost": self.player_sign(self.next_player) * (top_score_lead - d["scoreLead"]),
                    "winrateLost": self.player_sign(self.next_player) * (root_winrate - d["winrate"]),
                    **d,
                }
                for d in move_dicts
            ],
            key=lambda d: (d["order"], d["pointsLost"]),
        )

    @property
    def policy_ranking(self) -> Optional[List[Tuple[float, Move]]]:  # return moves from highest policy value to lowest
        if self.policy:
            szx, szy = self.board_size
            policy_grid = var_to_grid(self.policy, size=(szx, szy))
            moves = [(policy_grid[y][x], Move((x, y), player=self.next_player)) for x in range(szx) for y in range(szy)]
            moves.append((self.policy[-1], Move(None, player=self.next_player)))
            return sorted(moves, key=lambda mp: -mp[0])
