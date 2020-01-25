Manual
======

Installation
------------
* pip install kivy
* On linux, change the `engine.command` field in `config.json` to your kata v1.3+ installation.
* start the app by running `python katrain.py`

Options
-------
* Check box options
    * Eval: show the coloured dots on the moves for this player.
    * Hints: show suggested moves for this player.
    * Undo: automatically undo poor moves for this player and make them try again.
    * AI: let the AI control this player. Check both for self-play.
    * Show owner: show expected control of territory.    
    * Lock AI: disallow extra undos, changing hints options, changing auto move, or AI move.
    * Fast: use a lower number of max visits for evaluation/AI move.
    * Balance score: Deliberately make sub-optimal moves as the AI in an attempt to balance the score towawrds a slight win.

* Temperature/Evaluation/Score: Not that these fields can be hidden by clicking on the text.
    * Temperature is the point difference between passing and the best move.
    * Evaluation is where on this scale the last move was, from 0% (equivalent to a pass) to 100% (best move). 
    This can be < 0% in case of suicidal moves, or >100% when Kata did not consider the move before, or further analysis shows it to be better than the best one considered.
    * Score: How far one player is ahead.

Play
----

* Play against the AI
    * Turn on AI for the chosen player. 
    * Choose whether to turn on `balance score` to make the AI play slack moves.
    * Choose whether to turn on `undo` for your colour to be prompted to re-try poor moves. 
    * Choose whether or not to turn on `fast` to make the AI play faster but read less deeply (NB: with balance score, faster AI can be a stronger opponent, as there are fewer mediocre moves considered).
    * Possibly lock AI to prevent yourself from peeking at hints, etc.
    * Possibly hide score or temperature.
    * If you chose AI to play black, click AI move for the first move.
    
* Engine-assisted play
    * Turn off auto move.
    * Choose whether to turn on `undo` for either colour to be prompted to re-try poor moves.
    * Possibly lock AI to prevent peeking at hints.
    * Possibly hide score or temperature.
    * Play with a friend with instant feedback and/or undos for both, or see how many stones stronger you are with one undo. (But please play unranked and be honest to your opponent on what you're doing) 

* Analysis
    * Copy the SGF into the text box. Note that branches are not supported and will lead to strange results.
    * Choose whether or not to turn on `fast` to make the AI weaker but analyze faster.
    * Click `Analyze`
    
* Save game
    * Click save to get an sgf as `out.sgf` with comments (and a short version in the text box).

Configuration
-------------
`config.json` has a number of options, many of them are stylistic.

The `trainer` block has the following options to tweak:

* `balance_play_target_score`: indicates how many points the AI aims to win by when using 'balance score'.
* `balance_play_randomize_eval`: when not needing to balance score, the AI will pick a random move which is at least this good.
* `balance_play_min_eval`: when needing to balance score, the AI will pick a move which is at least this good.
* `balance_play_min_visits`: never pick a move with fewer playouts than this.
* `undo_eval_threshold`, `undo_point_threshold`: prompt player to undo if move is worse than this in terms of points AND evaluation.
* `num_undo_prompts`: automatically undo bad moves when `undo` is on at most this many times.

The cfg file has additional configuration for kata. In particular, it changes the default to being more exploratory and score-based (and therefore nicer as an opponent, but weaker as analysis tool).

TODO
----
* Prisoner count
* Better name
* ....
