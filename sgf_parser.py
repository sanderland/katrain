import re
import copy
from typing import Any, Dict, List, Optional, Tuple


class ParseError(Exception):
    pass


class Move:
    GTP_COORD = "ABCDEFGHJKLMNOPQRSTUVWYXYZ"
    PLAYERS = "BW"
    SGF_COORD = [chr(i) for i in range(97, 123)]

    @staticmethod
    def from_gtp(gtp_coords, player="B"):
        if "pass" in gtp_coords:
            Move(coords=None, player=player)
        return Move(coords=(Move.GTP_COORD.index(gtp_coords[0]), int(gtp_coords[1:]) - 1), player=player)

    @staticmethod
    def from_sgf(sgf_coords, board_size, player="B"):
        if sgf_coords == "" or Move.SGF_COORD.index(sgf_coords[0]) == board_size:  # some servers use [tt] for pass
            return Move(coords=None, player=player)
        return Move(coords=(Move.SGF_COORD.index(sgf_coords[0]), board_size - Move.SGF_COORD.index(sgf_coords[1]) - 1), player=player)

    def __init__(self, coords: Optional[Tuple[int, int]] = None, player: str = "B"):
        self.player = player
        self.coords = coords

    def __repr__(self):
        return f"Move({self.player}{self.gtp()})"

    #    def __hash__(self):
    #        return self.__repr__().__hash__()
    #    def __eq__(self, other):
    #        return self.coords == other.coords and self.player == other.player

    def gtp(self):
        if self.is_pass:
            return "pass"
        return Move.GTP_COORD[self.coords[0]] + str(self.coords[1] + 1)

    def sgf(self, board_size):
        if self.is_pass:
            return ""
        return f"{Move.SGF_COORD[self.coords[0]]}{Move.SGF_COORD[board_size - self.coords[1] - 1]}"

    @property
    def is_pass(self):
        return self.coords is None

    @property
    def opponent(self):
        return "W" if self.player == "B" else "B"


class SGFNode:
    CAST_FIELDS = {"KM": float, "SZ": int, "HA": int}  # cast property to this type
    LIST_FIELDS = ["AB", "AW", "TW", "TB", "MA", "SQ", "CR", "TR", "LN", "AR", "LB"]  # cast these properties to lists
    # TODO: all are potential lists? what a headache!

    def __init__(self, parent=None, properties=None, move=None):
        self.children = []
        self.properties = copy.copy(properties) if properties is not None else {}
        self.parent = parent
        if self.parent:
            self.parent.children.append(self)
        if parent and move:
            self.properties[move.player] = move.sgf(self.board_size)

    @property
    def sgf_properties(self) -> Dict:
        """For hooking into in a subclass and overriding/formatting any additional properties to be output"""
        return self.properties

    def sgf(self) -> str:
        sgf_str = "".join([f"{k}[{']['.join(v) if isinstance(v,list) else v}]" for k, v in self.sgf_properties.items()])
        if self.children:
            children = [c.sgf() for c in self.children]
            if len(children) == 1:
                sgf_str += ";" + children[0]
            else:
                sgf_str += "(;" + ")(;".join(children) + ")"
        return f"(;{sgf_str})" if self.is_root else sgf_str

    def __setitem__(self, prop: str, value: Any):
        if prop in self.LIST_FIELDS and isinstance(value, str):  # lists (placements, IGS marked dead stones)
            self.properties[prop] = self.properties.get(prop, []) + re.split(r"\]\s*\[", value)
        elif prop in self.CAST_FIELDS:
            self.properties[prop] = self.CAST_FIELDS[prop](value)
        else:
            self.properties[prop] = value

    def __getitem__(self, property) -> Any:
        return self.properties.get(property)

    def get(self, property, default) -> Any:
        return self.properties.get(property, default)

    @property
    def parent(self) -> Optional["SGFNode"]:
        return self._parent

    @parent.setter
    def parent(self, parent_node):
        self._parent = parent_node
        self._root = None
        self._depth = None

    @property
    def root(self) -> "SGFNode":  # cached root property
        if self._root is None:
            self._root = self.parent.root if self.parent else self
        return self._root

    @property
    def depth(self) -> int:  # cached depth property
        if self._depth is None:
            if self.is_root:
                self._depth = 0
            else:
                self._depth = self.parent.depth + 1
        return self._depth

    @property
    def board_size(self) -> int:
        return self.root.get("SZ", 19)

    @property
    def move(self) -> Optional[Move]:
        for pl in Move.PLAYERS:
            if self[pl]:
                return Move.from_sgf(self[pl], player=pl, board_size=self.board_size)

    @property
    def placements(self) -> List[Move]:
        return [Move.from_sgf(self[pl], player=pl, board_size=self.board_size) for pl in Move.PLAYERS for sgf in self.get("A" + pl, [])]

    @property
    def move_with_placements(self) -> List[Move]:
        move = self.move
        return self.placements + ([move] if move else [])

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def is_pass(self) -> bool:
        return not self.placements and self.move and self.move.is_pass

    @property
    def empty(self) -> bool:
        return not self.children and not self.properties

    @property
    def nodes_in_tree(self) -> List:
        return [self] + sum([c.nodes_in_tree for c in self.children], [])

    @property
    def nodes_from_root(self) -> List:
        return [self] if self.is_root else self.parent.nodes_from_root + [self]

    def play(self, move) -> "SGFNode":
        """Either find an existing child or create a new one with the given move."""
        for c in self.children:
            if c.move == move:
                return c.move
        return self.__class__(parent=self, move=move)

    @property
    def next_player(self):
        m = self.move
        if m and m.player == "B" or "AB" in self.properties:
            return "W"
        return "B"


class SGF:
    _MOVE_CLASS = SGFNode

    @staticmethod
    def parse(input_str) -> SGFNode:
        return SGF(input_str).root

    @staticmethod
    def parse_file(filename, encoding=None) -> SGFNode:
        with open(filename, "rb") as f:
            bin_contents = f.read()
            if not encoding:
                match = re.search(rb"CA\[(.*?)\]", bin_contents)
                if match:
                    encoding = match[1].decode("ascii")
                else:
                    encoding = "utf-8"  # default
            decoded = bin_contents.decode(encoding=encoding)
            return SGF.parse(decoded)

    def __init__(self, contents):
        self.contents = contents
        try:
            self.ix = self.contents.index("(") + 1
        except ValueError:
            raise ParseError("Parse error: Expected '('")
        self.root = SGFNode()
        self._parse_branch(self.root)

    def _parse_branch(self, current_move: SGFNode):
        while self.ix < len(self.contents):  # https://xkcd.com/1171/
            match = re.match(r"\s*(?:\(|\)|;|(?:(\w+)((?:\[.*?(?<!\\)\]\s*)+)))", self.contents[self.ix :], re.DOTALL)
            if not match:
                break
            self.ix += len(match[0])
            if match[0] == ")":
                return
            if match[0] == "(":
                self._parse_branch(SGFNode(parent=current_move))
            elif match[0] == ";":
                if not current_move.empty:  # ignore ; that generate empty nodes
                    current_move = self._MOVE_CLASS(parent=current_move)
            else:
                prop, value = match[1], match[2].strip()[1:-1]
                current_move[prop] = value
        if self.ix < len(self.contents):
            raise ParseError(f"Parse Error: unexpected character at {self.contents[self.ix - 25:self.ix]}>{self.contents[self.ix]}<{self.contents[self.ix + 1:self.ix + 25]}")
        raise ParseError("Parse Error: expected ')' at end of input.")
