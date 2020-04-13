# KaTrain v1.0

This repository contains  tool for playing go with AI feedback.
The idea is to give immediate feedback on the many large mistakes we make in terms of inefficient moves.
It is based on the KataGo AI and relies heavily on score estimation rather than win rate.

Some uses include:

* Review your games to find the moves that were most costly in terms of points lost.
* Play against AI and get immediate feedback on mistakes with option to retry.
* Play against a stronger player and use the retry option instead of handicap stones.
* Play a match with an evenly matched friend where both players get instant feedback.

![screenshot](https://imgur.com/t3Im6Xu.png)

## Manual

### Installation for Windows users

* Download the repository by clicking the green *Clone or download* on this page and *Download zip*. Extract the contents.
* Make sure you have a python installation, I will assume Anaconda (Python 3.7), available [here](https://www.anaconda.com/distribution/#download-section). 
* Open 'Anaconda prompt' from the start menu and navigate to where you extracted the zip file.
* Execute the command 'pip install kivy'
* Start the app by running `python katrain.py` in the directory where you downloaded the scripts. Note that the program can be slow to initialize the first time, due to kata's gpu tuning.

### Installation for Linux/Mac users

* This assumed you have a working Python 3.6/3.7 installation as a default. If your default is python 2, use pip3/python3. Kivy currently does not have a release for Python 3.8.
* Git clone or download the repository.
* `pip install -U kivy`
* Put your KataGo binary in the `KataGo/` directory or change the `engine.command` field in `config.json` to your KataGo v1.3.5+ binary.
    *  Compiled binaries and source code can be found [here](https://github.com/lightvector/KataGo/releases).
    * You will need to `chmod +x katago` your binary if you downloaded it.  
    * Executables for Mac are not available, so compiling from source code is required there.
* Start the app by running `python katrain.py`.  Note that the program can be slow to initialize the first time, due to KataGo's GPU tuning.

### Options

* Check box options
    * All Eval: show the coloured dots on all the moves for this player.
    * Hints: show suggested moves for this player and output more statistics on moves.
    * Undo: automatically undo poor moves for this player and make them try again.
    * AI: let the AI control this player. Check both for self-play.
    * Show owner: show expected control of territory.    
    * Lock AI: disallow extra undos, changing hints options, changing auto move, or AI move. Also turns off the option to click on a move to see detailed comments.
    * Fast: use a lower number of max visits for evaluation/AI move.
    * Balance score: Deliberately make sub-optimal moves as the AI in an attempt to balance the score towards a slight win.

* Temperature/Evaluation/Score: Not that these fields can be hidden by clicking on the text.
    * Temperature is the point difference between passing and the best move.
    * Evaluation is where on this scale the last move was, from 0% (equivalent to a pass) to 100% (best move). 
    This can be < 0% in case of suicidal moves, or >100% when KataGo did not consider the move before, or further analysis shows it to be better than the best one considered.
    * Score: How far one player is ahead.

* Keyboard controls
   * Arrow up: undo
   * Arrow down: redo
   * Arrow left/right: alternate branch.

### Play

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
    * Click 'Load' when the text box is empty-ish to get a file chooser dialog.  Note that branches are not supported and will lead to strange results.
    * Select if you want fast analysis or rewinding to the start for reviewing. Note that the 'fast' checkbox still affects speed as well,
      this is just an additional lowering of visits.
    * Alternatively copy the SGF into the text box and click 'Load'. 
    
* Save game
    * Click save to get an sgf with comments saved in the sgfout/ directory (and a short version in the text box).

### Configuration

`config.json` has a number of options, many of them are stylistic, but also including the command KataGo is started with (and thus the KataGo config and model).
You can use `python katrain.py your_config_file.json` to use another config file instead.

The `trainer` block has the following options to tweak for engine assisted play and reviewing:

* `eval_off_show_last`: when the `eval` checkbox is off for a player, show coloured dots on the last this many moves regardless. 
* `undo_eval_threshold`, `undo_point_threshold`: prompt player to undo if move is worse than this in terms of points AND evaluation.
* `num_undo_prompts`: automatically undo bad moves when `undo` is on at most this many times. Can be a fraction like 0.5 for 50% chance of being granted an undo on a bad move.
* `dont_lock_undos`: don't lock the undo button when `ai lock` is active.

The following options are relevant for the `balance score` AI play mode. 

* `balance_play_target_score`: indicates how many points the AI aims to win by when using 'balance score'.
* `balance_play_randomize_eval`: when not needing to balance score, the AI will pick a random move which is at least this good as long as it stays ahead.
* `balance_play_min_eval`: when needing to balance score, the AI will pick a move which is at least this good.
* `balance_play_min_visits`: never pick a move with fewer playouts than this.

The cfg file has additional configuration for KataGo, which are documented there. 

## FAQ

* The program is slow to start!
  * The first startup of KataGo can be slow, after that it should be much faster.
* The program is running too slowly!
  *  Lower the visits count in the `analysis` block of `config.json` by half or so and try again.
* Why are the dots changing colour?
  *  If the next move made is the predicted top move, more information is available to analyze the previous move and this is used to update the evaluation.  
* Can I play on sizes other than 9, 13 or 19?
  * Type in `SZ[n]HA[h]KM[k]` in the text box and hit 'load' for a game on a n by n board with h handicap stones and k komi, but note that the default KataGo does not support sizes above 19x19.  

## Contributing

* Feedback and pull requests are both very welcome.
* For suggestions and planned improvements, see the 'issues' tab on github.
