import os

from katrain.core.sgf_parser import SGF, SGFNode


def test_simple():
    input_sgf = "(;GM[1]FF[4]SZ[19]DT[2020-04-12]AB[dd][dj];B[dp];W[pp];B[pj])"
    root = SGF.parse_sgf(input_sgf)
    assert "4" == root.get_property("FF")
    assert root.get_property("XYZ") is None
    assert "dp" == root.children[0].get_property("B")
    assert input_sgf == root.sgf()


def test_branch():
    input_sgf = "(;GM[1]FF[4]CA[UTF-8]AP[Sabaki:0.43.3]KM[6.5]SZ[19]DT[2020-04-12]AB[dd][dj](;B[dp];W[pp](;B[pj])(;PL[B]AW[jp]C[sdfdsfdsf]))(;B[pd]))"
    root = SGF.parse_sgf(input_sgf)
    assert input_sgf == root.sgf()


def test_dragon_weirdness():  # dragon go server has weird line breaks
    input_sgf = "\n(\n\n;\nGM[1]\nFF[4]\nCA[UTF-8]AP[Sabaki:0.43.3]KM[6.5]SZ[19]DT[2020-04-12]AB[dd]\n[dj]\n(\n;\nB[dp]\n;\nW[pp]\n(\n;\nB[pj]\n)\n(\n;\nPL[B]\nAW[jp]\nC[sdfdsfdsf]\n)\n)\n(\n;\nB[pd]\n)\n)\n"
    root = SGF.parse_sgf(input_sgf)
    assert input_sgf.replace("\n", "") == root.sgf()


def test_weird_escape():
    input_sgf = """(;GM[1]FF[4]CA[UTF-8]AP[Sabaki:0.43.3]KM[6.5]SZ[19]DT[2020-04-12]C[how does it escape
[
or \\]
])"""
    root = SGF.parse_sgf(input_sgf)
    assert input_sgf == root.sgf()


def test_backslash_escape():
    nasty_string = "[]]\\"
    nasty_strings = ["[\\]\\]\\\\", "[", "]", "\\", "\\[", "\\]", "\\\\[", "\\\\]", "]]]\\]]\\]]["]
    assert "[\\]\\]\\\\" == SGFNode._escape_value(nasty_string)
    for x in nasty_strings:
        assert x == SGFNode._unescape_value(SGFNode._escape_value(x))

    c2 = ["]", "\\"]
    node = SGFNode(properties={"C1": nasty_string})
    node.set_property("C2", c2)
    assert "(;C1[[\\]\\]\\\\]C2[\\]][\\\\])" == node.sgf()
    assert {"C1": [nasty_string], "C2": c2} == SGF.parse_sgf(node.sgf()).properties


def test_alphago():
    file = os.path.join(os.path.dirname(__file__), "data/LS vs AG - G4 - English.sgf")
    SGF.parse_file(file)


def test_pandanet():
    file = os.path.join(os.path.dirname(__file__), "data/panda1.sgf")
    root = SGF.parse_file(file)
    root_props = {
        "GM",
        "EV",
        "US",
        "CP",
        "GN",
        "RE",
        "PW",
        "WR",
        "NW",
        "PB",
        "BR",
        "NB",
        "PC",
        "DT",
        "SZ",
        "TM",
        "KM",
        "LT",
        "RR",
        "HA",
        "AB",
        "C",
    }
    assert root_props == root.properties.keys()

    move = root
    while move.children:
        move = move.children[0]
    assert 94 == len(move.get_list_property("TW"))
    assert "Trilan" == move.get_property("OS")
    while move.parent:
        move = move.parent
    assert move is root


def test_ogs():
    file = os.path.join(os.path.dirname(__file__), "data/ogs.sgf")
    tree = SGF.parse_file(file)


def test_gibo():
    file = os.path.join(os.path.dirname(__file__), "data/test.gib")
    root = SGF.parse_file(file)
    assert {
        "PW": ["wildsim1"],
        "WR": ["2D"],
        "PB": ["kim"],
        "BR": ["2D"],
        "RE": ["W+T"],
        "KM": [6.5],
        "DT": ["2020-06-14"],
    } == root.properties
    assert "pd" == root.children[0].get_property("B")


def test_ngf():
    file = os.path.join(os.path.dirname(__file__), "data/handicap2.ngf")
    root = SGF.parse_file(file)
    root.properties["AB"].sort()
    assert {
        "AB": ["dp", "pd"],
        "DT": ["2017-03-16"],
        "HA": [2],
        "PB": ["p81587"],
        "PW": ["ace550"],
        "RE": ["W+"],
        "SZ": [19],
    } == root.properties
    assert "pq" == root.children[0].get_property("W")
