import math


def median(data):
    sorteddata = sorted(data)
    lendata = len(data)
    index = (lendata - 1) // 2
    if (lendata % 2):
        return sorteddata[index]
    else:
        return (sorteddata[index] + sorteddata[index + 1])/2.0

def calculate_rank(len_legal, rank):
    size = [19, 19] # game.board_size
    board_size = size[0]*size[1]
    median_rank = median(rank)
    median_len_legal = median(len_legal)
    n_moves = (math.sqrt(math.exp(1))*(median_len_legal)-(median_rank-0.5))/((-1+2*math.sqrt(math.exp(1)))*(median_rank-0.5)) # the median_rank is the median of the best move from a selection of n_moves with median_len_legal of total legal moves
    rank_kyu = (math.log10(n_moves*361/board_size)-1.9482)/-0.05737 # using the calibration curve of p:pick:rank
    return rank_kyu



def rank_game(len_legal_policy_moves, policy_rank, policy_value, len_segment):
    size = [19, 19] # game.board_size
    board_size = size[0]*size[1]
    total_game_len_legal = []
    total_game_rank = []
    segments_len_legal = [[]]
    segments_rank = [[]]
    j = 0
    for i in range(len(len_legal_policy_moves)):

        if policy_value[i]<(0.8*(1-(board_size-len_legal_policy_moves[i])/board_size*.5)): # do not include moves that are too obvious/would be terrible blunder if not played
            total_game_len_legal.append(len_legal_policy_moves[i])
            total_game_rank.append(policy_rank[i])
            segments_len_legal[j].append(len_legal_policy_moves[i])
            segments_rank[j].append(policy_rank[i])
            if i>=(j+1)*len_segment/2-1: # 50 moves on the board means 25 move for the player
                segments_len_legal.append([])
                segments_rank.append([])
                j+=1
        
    if j>0: # concatenate the last two segments to avoid low sample number in the last one
        segments_len_legal[-2] = segments_len_legal[-1]+segments_len_legal[-2]
        segments_rank[-2] = segments_rank[-1]+segments_rank[-2]
        segments_len_legal.pop()
        segments_rank.pop()
    
    ranks = []
    ranks.append(calculate_rank(total_game_len_legal, total_game_rank)) # first in the list is the overall rank
    for part in range(len(segments_len_legal)):
        ranks.append(calculate_rank(segments_len_legal[part], segments_rank[part])) # the rest are ranks of consecutive segments
    
    return ranks
                

if __name__ == '__main__':
    import glob,  os
    filelist = glob.glob("*.csv")
    filelist.sort(key=os.path.getmtime)
    for fil in filelist:
        filer = open(fil, "r")
        listr = filer.readlines()
        len_segment = 50 # length of a segment
        len_legal_policy_moves = [] # a list containing the number of legal moves
        policy_rank = [] # a list with the policy rank of the move
        policy_value = [] # a list with the policy value of the move
        for line in listr:
            a, b, c = line.strip().split(",")
            len_legal_policy_moves.append(eval(a))
            policy_rank.append(eval(b))
            policy_value.append(eval(c))
        ranks = rank_game(len_legal_policy_moves, policy_rank, policy_value, len_segment)
        print("File name: {0:s}".format(fil))
        print("Move quality for the entire game: {0:.0f} kyu".format(ranks[0]))
        for ind in range(1, len(ranks)-1):
            print("Move quality from move {1:d} to {2:d}: {0:.0f} kyu".format(ranks[ind], (ind-1)*len_segment,  ind*len_segment))
        print("Move quality from move {1:d} to the end: {0:.0f} kyu\n".format(ranks[ind+1], (ind)*len_segment))
        filer.close()
        
