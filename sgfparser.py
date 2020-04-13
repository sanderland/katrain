import re
from typing import Any, Dict, List, Optional


class ParseError(Exception):
    pass


class Move:
    CAST_FIELDS = {"KM": float, "SZ": int, "HA": int}  # cast property to this type
    LIST_FIELDS = ["AB", "AW", "TW", "TB"]  # cast these properties to lists

    def __init__(self):
        self.parent = None
        self.children = []
        self.properties = {}

    def __str__(self) -> str:
        return f"(;{self._node_sgf()})"

    def empty(self) -> bool:
        return not self.children and not self.properties

    def add_child(self,child_branch):
        self.children.append(child_branch)
        child_branch.parent = self

    def __setitem__(self, prop: str, value: Any):
        if prop in self.LIST_FIELDS and isinstance(value, str):  # lists (placements, IGS marked dead stones)
            self.properties[prop] = re.split(r"\]\s*\[", value)
        elif prop in self.CAST_FIELDS:
            self.properties[prop] = self.CAST_FIELDS[prop](value)
        else:
            self.properties[prop] = value

    def __getitem__(self, ix) -> Any:
        return self.properties.get(ix)

    def _node_sgf(self) -> str:
        move_props = "".join([f"{k}[{']['.join(v) if isinstance(v,list) else v}]" for k, v in self.properties.items()])
        if not self.children:
            return move_props
        else:
            children = [c._node_sgf() for c in self.children]
            if len(children) == 1:
                return move_props + ";" + children[0]
            else:
                return move_props + "(;" + ")(;".join(children) + ")"


class SGF:
    _MOVE_CLASS = Move

    def __init__(self, contents):
        self.contents = contents
        try:
            self.ix = self.contents.index("(") + 1
        except ValueError:
            raise ParseError("Parse error: Expected '('")
        self.root = self._parse_branch()

    @staticmethod
    def parse(input_str) -> Move:
        return SGF(input_str).root

    @staticmethod
    def parse_file(filename, encoding=None) -> Move:
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

    def _parse_branch(self) -> Move:
        move_tree = self._MOVE_CLASS()
        current_move = move_tree

        while self.ix < len(self.contents):  # https://xkcd.com/1171/
            match = re.match(r"\s*(?:\(|\)|;|(?:(\w+)((?:\[.*?(?<!\\)\]\s*)+)))", self.contents[self.ix :], re.DOTALL)
            if not match:
                break
            self.ix += len(match[0])
            if match[0] == ")":
                return move_tree
            if match[0] == "(":
                current_move.add_child(self._parse_branch())
            elif match[0] == ";":
                if not current_move.empty():  # ignore ; that generate empty nodes
                    next_move = self._MOVE_CLASS()
                    current_move.add_child(next_move)
                    current_move = next_move
            else:
                prop, value = match[1], match[2].strip()[1:-1]
                current_move[prop] = value
        if self.ix < len(self.contents):
            raise ParseError(
                f"Parse Error: unexpected character at {self.contents[self.ix - 25:self.ix]}>{self.contents[self.ix]}<{self.contents[self.ix + 1:self.ix + 25]}"
            )
        raise ParseError("Parse Error: expected ')' at end of input.")
