import copy
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union

# TODO: handle AE ?
# https://www.red-bean.com/sgf/properties.html


class ParseError(Exception):
    pass


class Move:
    GTP_COORD = list("ABCDEFGHJKLMNOPQRSTUVWXYZ") + ["A" + c for c in "ABCDEFGHJKLMNOPQRSTUVWXYZ"]  # kata board size 29 support
    PLAYERS = "BW"
    SGF_COORD = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ".lower()) + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    @classmethod
    def from_gtp(cls, gtp_coords, player="B"):
        if "pass" in gtp_coords.lower():
            return cls(coords=None, player=player)
        match = re.match(r"([A-Z]+)(\d+)", gtp_coords)
        return cls(coords=(Move.GTP_COORD.index(match[1]), int(match[2]) - 1), player=player)

    @classmethod
    def from_sgf(cls, sgf_coords, board_size, player="B"):
        if sgf_coords == "" or Move.SGF_COORD.index(sgf_coords[0]) == board_size[0]:  # some servers use [tt] for pass
            return cls(coords=None, player=player)
        return cls(coords=(Move.SGF_COORD.index(sgf_coords[0]), board_size[0] - Move.SGF_COORD.index(sgf_coords[1]) - 1), player=player)

    def __init__(self, coords: Optional[Tuple[int, int]] = None, player: str = "B"):
        self.player = player
        self.coords = coords

    def __repr__(self):
        return f"Move({self.player}{self.gtp()})"

    def __eq__(self, other):
        return self.coords == other.coords and self.player == other.player

    def gtp(self):
        if self.is_pass:
            return "pass"
        return Move.GTP_COORD[self.coords[0]] + str(self.coords[1] + 1)

    def sgf(self, board_size):
        if self.is_pass:
            return ""
        return f"{Move.SGF_COORD[self.coords[0]]}{Move.SGF_COORD[board_size[0] - self.coords[1] - 1]}"

    @property
    def is_pass(self):
        return self.coords is None

    @property
    def opponent(self):
        return "W" if self.player == "B" else "B"


class SGFNode:
    def __init__(self, parent=None, properties=None, move=None):
        self.children = []
        self.properties = defaultdict(list)
        if properties:
            for k, v in properties.items():
                self.set_property(k, v)
        self.parent = parent
        if self.parent:
            self.parent.children.append(self)
        if parent and move:
            self.set_property(move.player, move.sgf(self.board_size))

    def sgf_properties(self, **xargs) -> Dict:
        """For hooking into in a subclass and overriding/formatting any additional properties to be output"""
        return copy.deepcopy(self.properties)

    def sgf(self, **xargs) -> str:
        """Generates an SGF, calling sgf_properties on each node with the given xargs, so it can filter relevant properties if needed."""
        import sys

        sys.setrecursionlimit(max(sys.getrecursionlimit(), 3 * 29 * 29))  # thanks to lightvector for causing stack overflows
        sgf_str = "".join([prop + "".join(f"[{v}]" for v in values) for prop, values in self.sgf_properties(**xargs).items() if values])
        if self.children:
            children = [c.sgf(**xargs) for c in self.children]
            if len(children) == 1:
                sgf_str += ";" + children[0]
            else:
                sgf_str += "(;" + ")(;".join(children) + ")"
        return f"(;{sgf_str})" if self.is_root else sgf_str

    def add_list_property(self, property: str, values: List):
        """Add some values to the property list."""
        self.properties[property] += values

    def get_list_property(self, property, default=None) -> Any:
        """Get the list of values for a property."""
        return self.properties.get(property, default)

    def set_property(self, property: str, value: Any):
        """Add some values to the property. If not a list, it will be made into a single-value list."""
        if isinstance(value, list):
            self.properties[property] = value
        else:
            self.properties[property] = [value]

    def get_property(self, property, default=None) -> Any:
        """Get the first value of the property, typically when exactly one is expected."""
        return self.properties.get(property, [default])[0]

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

    # some root properties are available on any node
    @property
    def board_size(self) -> Tuple[int, int]:
        size = str(self.root.get_property("SZ", "19"))
        if ":" in size:
            x, y = map(int, size.split(":"))
        else:
            x = int(size)
            y = x
        return x, y

    @property
    def komi(self) -> float:
        return float(self.root.get_property("KM", 6.5))

    @property
    def ruleset(self) -> str:
        return self.root.get_property("RU")

    @property
    def moves(self) -> List[Move]:
        """Returns all moves in the node."""
        return [Move.from_sgf(move, player=pl, board_size=self.board_size) for pl in Move.PLAYERS for move in self.get_list_property(pl, [])]

    @property
    def placements(self) -> List[Move]:
        """Returns all placements (AB/AW) in the node."""
        return [Move.from_sgf(sgf_coords, player=pl, board_size=self.board_size) for pl in Move.PLAYERS for sgf_coords in self.get_list_property("A" + pl, [])]

    @property
    def move_with_placements(self) -> List[Move]:
        """Returns all moves (B/W) and placements (AB/AW) in the node."""
        return self.placements + self.moves

    @property
    def single_move(self) -> Optional[Move]:
        """Returns the single move for the node if one exists, or None if no moves (or multiple ones) exist."""
        moves = self.moves
        if len(moves) == 1:  # TODO: and not placements?
            return moves[0]

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def is_pass(self) -> bool:
        return not self.placements and self.single_move and self.single_move.is_pass

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
            if c.single_move == move:
                return c
        return self.__class__(parent=self, move=move)

    @property
    def next_player(self):
        if self.get_list_property("B") or self.get_list_property("AB"):
            return "W"
        return "B"

    @property
    def player(self):
        if self.get_list_property("B") or self.get_list_property("AB"):
            return "B"
        return "W"


class SGF:
    _NODE_CLASS = SGFNode

    @classmethod
    def parse(cls, input_str) -> SGFNode:
        return cls(input_str).root

    @classmethod
    def parse_file(cls, filename, encoding=None) -> SGFNode:
        with open(filename, "rb") as f:
            bin_contents = f.read()
            if not encoding:
                match = re.search(rb"CA\[(.*?)\]", bin_contents)
                if match:
                    encoding = match[1].decode("ascii")
                else:
                    encoding = "ISO-8859-1"  # default
            decoded = bin_contents.decode(encoding=encoding)
            return cls.parse(decoded)

    def __init__(self, contents):
        self.contents = contents
        try:
            self.ix = self.contents.index("(") + 1
        except ValueError:
            raise ParseError("Parse error: Expected '('")
        self.root = self._NODE_CLASS()
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
                self._parse_branch(self._NODE_CLASS(parent=current_move))
            elif match[0] == ";":
                if not current_move.empty:  # ignore ; that generate empty nodes
                    current_move = self._NODE_CLASS(parent=current_move)
            else:
                property, value = match[1], match[2].strip()[1:-1]
                values = re.split(r"\]\s*\[", value)
                current_move.add_list_property(property, values)
        if self.ix < len(self.contents):
            raise ParseError(f"Parse Error: unexpected character at {self.contents[self.ix:self.ix+25]}")
        raise ParseError("Parse Error: expected ')' at end of input.")
