import copy
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


class ParseError(Exception):
    """Exception raised on a parse error"""

    pass


class Move:
    GTP_COORD = list("ABCDEFGHJKLMNOPQRSTUVWXYZ") + [
        xa + c for xa in "AB" for c in "ABCDEFGHJKLMNOPQRSTUVWXYZ"
    ]  # board size 52+ support
    PLAYERS = "BW"
    SGF_COORD = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ".lower()) + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")  # sgf goes to 52

    @classmethod
    def from_gtp(cls, gtp_coords, player="B"):
        """Initialize a move from GTP coordinates and player"""
        if "pass" in gtp_coords.lower():
            return cls(coords=None, player=player)
        match = re.match(r"([A-Z]+)(\d+)", gtp_coords)
        return cls(coords=(Move.GTP_COORD.index(match[1]), int(match[2]) - 1), player=player)

    @classmethod
    def from_sgf(cls, sgf_coords, board_size, player="B"):
        """Initialize a move from SGF coordinates and player"""
        if sgf_coords == "" or Move.SGF_COORD.index(sgf_coords[0]) == board_size[0]:  # some servers use [tt] for pass
            return cls(coords=None, player=player)
        return cls(
            coords=(Move.SGF_COORD.index(sgf_coords[0]), board_size[1] - Move.SGF_COORD.index(sgf_coords[1]) - 1),
            player=player,
        )

    def __init__(self, coords: Optional[Tuple[int, int]] = None, player: str = "B"):
        """Initialize a move from zero-based coordinates and player"""
        self.player = player
        self.coords = coords

    def __repr__(self):
        return f"Move({self.player}{self.gtp()})"

    def __eq__(self, other):
        return self.coords == other.coords and self.player == other.player

    def gtp(self):
        """Returns GTP coordinates of the move"""
        if self.is_pass:
            return "pass"
        return Move.GTP_COORD[self.coords[0]] + str(self.coords[1] + 1)

    def sgf(self, board_size):
        """Returns SGF coordinates of the move"""
        if self.is_pass:
            return ""
        return f"{Move.SGF_COORD[self.coords[0]]}{Move.SGF_COORD[board_size[1] - self.coords[1] - 1]}"

    @property
    def is_pass(self):
        """Returns True if the move is a pass"""
        return self.coords is None

    @property
    def opponent(self):
        """Returns the opposing player, i.e. W <-> B"""
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
        """For hooking into in a subclass and overriding/formatting any additional properties to be output."""
        return copy.deepcopy(self.properties)

    @staticmethod
    def order_children(children):
        """For hooking into in a subclass and overriding branch order."""
        return children

    @property
    def ordered_children(self):
        return self.order_children(self.children)

    @staticmethod
    def _escape_value(value):
        return re.sub(r"([\]\\])", r"\\\1", value) if isinstance(value, str) else value  # escape \ and ]

    @staticmethod
    def _unescape_value(value):
        return re.sub(r"\\([\]\\])", r"\1", value) if isinstance(value, str) else value  # unescape \ and ]

    def sgf(self, **xargs) -> str:
        """Generates an SGF, calling sgf_properties on each node with the given xargs, so it can filter relevant properties if needed."""

        def node_sgf_str(node):
            return ";" + "".join(
                [
                    prop + "".join(f"[{self._escape_value(v)}]" for v in values)
                    for prop, values in node.sgf_properties(**xargs).items()
                    if values
                ]
            )

        stack = [")", self, "("]
        sgf_str = ""
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                sgf_str += item
            else:
                sgf_str += node_sgf_str(item)
                if len(item.children) == 1:
                    stack.append(item.children[0])
                elif item.children:
                    stack += sum([[")", c, "("] for c in item.ordered_children[::-1]], [])
        return sgf_str

    def add_list_property(self, property: str, values: List):
        """Add some values to the property list."""
        self.properties[property] += values

    def get_list_property(self, property, default=None) -> Any:
        """Get the list of values for a property."""
        return self.properties.get(property, default)

    def set_property(self, property: str, value: Any):
        """Add some values to the property. If not a list, it will be made into a single-value list."""
        if not isinstance(value, list):
            value = [value]
        self.properties[property] = value

    def get_property(self, property, default=None) -> Any:
        """Get the first value of the property, typically when exactly one is expected."""
        return self.properties.get(property, [default])[0]

    @property
    def parent(self) -> Optional["SGFNode"]:
        """Returns the parent node"""
        return self._parent

    @parent.setter
    def parent(self, parent_node):
        self._parent = parent_node
        self._root = None
        self._depth = None

    @property
    def root(self) -> "SGFNode":
        """Returns the root of the tree, cached for speed"""
        if self._root is None:
            self._root = self.parent.root if self.parent else self
        return self._root

    @property
    def depth(self) -> int:
        """Returns the depth of this node, where root is 0, cached for speed"""
        if self._depth is None:
            if self.is_root:
                self._depth = 0
            else:
                self._depth = self.parent.depth + 1
        return self._depth

    @property
    def board_size(self) -> Tuple[int, int]:
        """Retrieves the root's SZ property, or 19 if missing. Parses it, and returns board size as a tuple x,y"""
        size = str(self.root.get_property("SZ", "19"))
        if ":" in size:
            x, y = map(int, size.split(":"))
        else:
            x = int(size)
            y = x
        return x, y

    @property
    def komi(self) -> float:
        """Retrieves the root's KM property, or 6.5 if missing"""
        return float(self.root.get_property("KM", 6.5))

    @property
    def ruleset(self) -> str:
        """Retrieves the root's RU property, or 'japanese' if missing"""
        return self.root.get_property("RU", "japanese")

    @property
    def moves(self) -> List[Move]:
        """Returns all moves in the node - typically 'move' will be better."""
        return [
            Move.from_sgf(move, player=pl, board_size=self.board_size)
            for pl in Move.PLAYERS
            for move in self.get_list_property(pl, [])
        ]

    @property
    def placements(self) -> List[Move]:
        """Returns all placements (AB/AW) in the node."""
        return [
            Move.from_sgf(sgf_coords, player=pl, board_size=self.board_size)
            for pl in Move.PLAYERS
            for sgf_coords in self.get_list_property("A" + pl, [])
        ]

    @property
    def move_with_placements(self) -> List[Move]:
        """Returns all moves (B/W) and placements (AB/AW) in the node."""
        return self.placements + self.moves

    @property
    def move(self) -> Optional[Move]:
        """Returns the single move for the node if one exists, or None if no moves (or multiple ones) exist."""
        moves = self.moves
        if len(moves) == 1:
            return moves[0]

    @property
    def is_root(self) -> bool:
        """Returns true if node is a root"""
        return self.parent is None

    @property
    def is_pass(self) -> bool:
        """Returns true if associated move is pass"""
        return not self.placements and self.move and self.move.is_pass

    @property
    def empty(self) -> bool:
        """Returns true if node has no children or properties"""
        return not self.children and not self.properties

    @property
    def nodes_in_tree(self) -> List:
        """Returns all nodes in the tree rooted at this node"""
        stack = [self]
        nodes = []
        while stack:
            item = stack.pop(0)
            nodes.append(item)
            stack += item.children
        return nodes

    @property
    def nodes_from_root(self) -> List:
        """Returns all nodes from the root up to this node, i.e. the moves played in the current branch of the game"""
        nodes = [self]
        n = self
        while not n.is_root:
            n = n.parent
            nodes.append(n)
        return nodes[::-1]

    def play(self, move) -> "SGFNode":
        """Either find an existing child or create a new one with the given move."""
        for c in self.children:
            if c.move == move:
                return c
        return self.__class__(parent=self, move=move)

    @property
    def next_player(self):
        """Returns player to move"""
        if "B" in self.properties or "AB" in self.properties:  # root or black moved
            return "W"
        else:
            return "B"

    @property
    def player(self):
        """Returns player that moved last. nb root is considered white played if no handicap stones are placed"""
        if "B" in self.properties or "AB" in self.properties:
            return "B"
        else:
            return "W"


class SGF:

    _NODE_CLASS = SGFNode  # Class used for SGF Nodes, can change this to something that inherits from SGFNode
    # https://xkcd.com/1171/
    SGFPROP_PAT = re.compile(r"\s*(?:\(|\)|;|(\w+)((\s*\[([^\]\\]|\\.)*\])+))", flags=re.DOTALL)

    @classmethod
    def parse(cls, input_str) -> SGFNode:
        """Parse a string as SGF."""
        return cls(input_str).root

    @classmethod
    def parse_file(cls, filename, encoding=None) -> SGFNode:
        """Parse a file as SGF, encoding will be detected if not given."""
        with open(filename, "rb") as f:
            bin_contents = f.read()
            if not encoding:
                match = re.search(rb"CA\[(.*?)\]", bin_contents)
                if match:
                    encoding = match[1].decode("ascii", errors="ignore")
                else:
                    encoding = "ISO-8859-1"  # default
            decoded = bin_contents.decode(encoding=encoding, errors="ignore")
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
        while self.ix < len(self.contents):
            match = re.match(self.SGFPROP_PAT, self.contents[self.ix :])
            if not match:
                break
            self.ix += len(match[0])
            matched_item = match[0].strip()
            if matched_item == ")":
                return
            if matched_item == "(":
                self._parse_branch(self._NODE_CLASS(parent=current_move))
            elif matched_item == ";":
                if not current_move.empty:  # ignore ; that generate empty nodes
                    current_move = self._NODE_CLASS(parent=current_move)
            else:
                property, value = match[1], match[2].strip()[1:-1]
                values = re.split(r"\]\s*\[", value)
                current_move.add_list_property(property, [SGFNode._unescape_value(v) for v in values])
        if self.ix < len(self.contents):
            raise ParseError(f"Parse Error: unexpected character at {self.contents[self.ix:self.ix+25]}")
        raise ParseError("Parse Error: expected ')' at end of input.")
