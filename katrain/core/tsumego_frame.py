from katrain.core.game_node import GameNode
from katrain.core.sgf_parser import Move

# tsumego frame ported from lizgoban by kaorahi
# note: coords = (j, i) in katrain

near_to_edge = 2
offence_to_win = 5

BLACK = "B"
WHITE = "W"


def tsumego_frame_from_katrain_game(game, komi, black_to_play_p, ko_p, margin):
    current_node = game.current_node
    bw_board = [[game.chains[c][0].player if c >= 0 else "-" for c in line] for line in game.board]
    isize, jsize = ij_sizes(bw_board)
    blacks, whites, analysis_region = tsumego_frame(bw_board, komi, black_to_play_p, ko_p, margin)
    sgf_blacks = katrain_sgf_from_ijs(blacks, isize, jsize, "B")
    sgf_whites = katrain_sgf_from_ijs(whites, isize, jsize, "W")

    played_node = GameNode(parent=current_node, properties={"AB": sgf_blacks, "AW": sgf_whites})  # this inserts

    katrain_region = analysis_region and (analysis_region[1], analysis_region[0])
    return (played_node, katrain_region)


def katrain_sgf_from_ijs(ijs, isize, jsize, player):
    return [Move((j, i)).sgf((jsize, isize)) for i, j in ijs]


def tsumego_frame(bw_board, komi, black_to_play_p, ko_p, margin):
    stones = stones_from_bw_board(bw_board)
    filled_stones = tsumego_frame_stones(stones, komi, black_to_play_p, ko_p, margin)
    region_pos = pick_all(filled_stones, "tsumego_frame_region_mark")
    bw = pick_all(filled_stones, "tsumego_frame")
    blacks = [(i, j) for i, j, black in bw if black]
    whites = [(i, j) for i, j, black in bw if not black]
    return (blacks, whites, get_analysis_region(region_pos))


def pick_all(stones, key):
    return [[i, j, s.get("black")] for i, row in enumerate(stones) for j, s in enumerate(row) if s.get(key)]


def get_analysis_region(region_pos):
    if len(region_pos) == 0:
        return None
    ai, aj, dummy = tuple(zip(*region_pos))
    ri = (min(ai), max(ai))
    rj = (min(aj), max(aj))
    return ri[0] < ri[1] and rj[0] < rj[1] and (ri, rj)


def tsumego_frame_stones(stones, komi, black_to_play_p, ko_p, margin):
    sizes = ij_sizes(stones)
    isize, jsize = sizes
    ijs = [
        {"i": i, "j": j, "black": h.get("black")}
        for i, row in enumerate(stones)
        for j, h in enumerate(row)
        if h.get("stone")
    ]

    if len(ijs) == 0:
        return []
    # find range of problem
    top = min_by(ijs, "i", +1)
    left = min_by(ijs, "j", +1)
    bottom = min_by(ijs, "i", -1)
    right = min_by(ijs, "j", -1)
    imin = snap0(top["i"])
    jmin = snap0(left["j"])
    imax = snapS(bottom["i"], isize)
    jmax = snapS(right["j"], jsize)
    # flip/rotate for standard position
    # don't mix flip and swap (FF = SS = identity, but SFSF != identity)
    flip_spec = (
        [False, False, True] if imin < jmin else [need_flip_p(imin, imax, isize), need_flip_p(jmin, jmax, jsize), False]
    )
    if True in flip_spec:
        flipped = flip_stones(stones, flip_spec)
        filled = tsumego_frame_stones(flipped, komi, black_to_play_p, ko_p, margin)
        return flip_stones(filled, flip_spec)
    # put outside stones
    i0 = imin - margin
    i1 = imax + margin
    j0 = jmin - margin
    j1 = jmax + margin
    frame_range = [i0, i1, j0, j1]
    black_to_attack_p = guess_black_to_attack([top, bottom, left, right], sizes)
    put_border(stones, sizes, frame_range, black_to_attack_p)
    put_outside(stones, sizes, frame_range, black_to_attack_p, black_to_play_p, komi)
    put_ko_threat(stones, sizes, frame_range, black_to_attack_p, black_to_play_p, ko_p)
    return stones


# detect corner/edge/center problems
# (avoid putting border stones on the first lines)
def snap(k, to):
    return to if abs(k - to) <= near_to_edge else k


def snap0(k):
    return snap(k, 0)


def snapS(k, size):
    return snap(k, size - 1)


def min_by(ary, key, sign):
    by = [sign * z[key] for z in ary]
    return ary[by.index(min(by))]


def need_flip_p(kmin, kmax, size):
    return kmin < size - kmax - 1


def guess_black_to_attack(extrema, sizes):
    return sum([sign_of_color(z) * height2(z, sizes) for z in extrema]) > 0


def sign_of_color(z):
    return 1 if z["black"] else -1


def height2(z, sizes):
    isize, jsize = sizes
    return height(z["i"], isize) + height(z["j"], jsize)


def height(k, size):
    return size - abs(k - (size - 1) / 2)


######################################
# sub


def put_border(stones, sizes, frame_range, is_black):
    i0, i1, j0, j1 = frame_range
    put_twin(stones, sizes, i0, i1, j0, j1, is_black, False)
    put_twin(stones, sizes, j0, j1, i0, i1, is_black, True)


def put_twin(stones, sizes, beg, end, at0, at1, is_black, reverse_p):
    for at in (at0, at1):
        for k in range(beg, end + 1):
            i, j = (at, k) if reverse_p else (k, at)
            put_stone(stones, sizes, i, j, is_black, False, True)


def put_outside(stones, sizes, frame_range, black_to_attack_p, black_to_play_p, komi):
    isize, jsize = sizes
    count = 0
    offense_komi = (+1 if black_to_attack_p else -1) * komi
    defense_area = (isize * jsize - offense_komi - offence_to_win) / 2
    for i in range(isize):
        for j in range(jsize):
            if inside_p(i, j, frame_range):
                continue
            count += 1
            black_p = xor(black_to_attack_p, (count <= defense_area))
            empty_p = (i + j) % 2 == 0 and abs(count - defense_area) > isize
            put_stone(stones, sizes, i, j, black_p, empty_p)


# standard position:
# ? = problem, X = offense, O = defense
# OOOOOOOOOOOOO
# OOOOOOOOOOOOO
# OOOOOOOOOOOOO
# XXXXXXXXXXXXX
# XXXXXXXXXXXXX
# XXXX.........
# XXXX.XXXXXXXX
# XXXX.X???????
# XXXX.X???????

# (pattern, top_p, left_p)
offense_ko_threat = (
    """
....OOOX.
.....XXXX
""",
    True,
    False,
)

defense_ko_threat = (
    """
..
..
X.
XO
OO
.O
""",
    False,
    True,
)


def put_ko_threat(stones, sizes, frame_range, black_to_attack_p, black_to_play_p, ko_p):
    isize, jsize = sizes
    for_offense_p = xor(ko_p, xor(black_to_attack_p, black_to_play_p))
    pattern, top_p, left_p = offense_ko_threat if for_offense_p else defense_ko_threat
    aa = [list(line) for line in pattern.splitlines() if len(line) > 0]
    height, width = ij_sizes(aa)
    for i, row in enumerate(aa):
        for j, ch in enumerate(row):
            ai = i + (0 if top_p else isize - height)
            aj = j + (0 if left_p else jsize - width)
            if inside_p(ai, aj, frame_range):
                return
            black = xor(black_to_attack_p, ch == "O")
            empty = ch == "."
            put_stone(stones, sizes, ai, aj, black, empty)


def xor(a, b):
    return bool(a) != bool(b)


######################################
# util


def flip_stones(stones, flip_spec):
    swap_p = flip_spec[2]
    sizes = ij_sizes(stones)
    isize, jsize = sizes
    new_isize, new_jsize = [jsize, isize] if swap_p else [isize, jsize]
    new_stones = [[None for z in range(new_jsize)] for row in range(new_isize)]
    for i, row in enumerate(stones):
        for j, z in enumerate(row):
            new_i, new_j = flip_ij((i, j), sizes, flip_spec)
            new_stones[new_i][new_j] = z
    return new_stones


def put_stone(stones, sizes, i, j, black, empty, tsumego_frame_region_mark=False):
    isize, jsize = sizes
    if i < 0 or isize <= i or j < 0 or jsize <= j:
        return
    stones[i][j] = (
        {}
        if empty
        else {
            "stone": True,
            "tsumego_frame": True,
            "black": black,
            "tsumego_frame_region_mark": tsumego_frame_region_mark,
        }
    )


def inside_p(i, j, region):
    i0, i1, j0, j1 = region
    return i0 <= i and i <= i1 and j0 <= j and j <= j1


def stones_from_bw_board(bw_board):
    return [[stone_from_str(s) for s in row] for row in bw_board]


def stone_from_str(s):
    black = s == BLACK
    white = s == WHITE
    return {"stone": True, "black": black} if (black or white) else {}


def ij_sizes(stones):
    return (len(stones), len(stones[0]))


def flip_ij(ij, sizes, flip_spec):
    i, j = ij
    isize, jsize = sizes
    flip_i, flip_j, swap_ij = flip_spec
    fi = flip1(i, isize, flip_i)
    fj = flip1(j, jsize, flip_j)
    return (fj, fi) if swap_ij else (fi, fj)


def flip1(k, size, flag):
    return size - 1 - k if flag else k
