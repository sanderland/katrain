# KaTrain v1.0

This repository contains  tool for analyzing and playing go with AI feedback from KataGo.

The original idea was to give immediate feedback on the many large mistakes we make in terms of inefficient moves,
but has since grown to include a wide range of features, including:

* Review your games to find the moves that were most costly in terms of points lost.
* Play against AI and get immediate feedback on mistakes with option to retry.
* Play against a wide range of weakened versions of AI with various styles.
* Play against a stronger player and use the retry option instead of handicap stones.

![screenshot](https://imgur.com/t3Im6Xu.png)

## Installation

### Installation for Windows users

* Download the repository by clicking the green *Clone or download* on this page and *Download zip*. Extract the contents.
* Make sure you have a python installation, I will assume Anaconda (Python 3.7), available [here](https://www.anaconda.com/distribution/#download-section). 
* Open 'Anaconda prompt' from the start menu and navigate to where you extracted the zip file using the `cd <folder>` command.
* Execute the command `pip install numpy kivy_deps.glew kivy_deps.sdl2 kivy_deps.gstreamer kivy`
* Start the app by running `python katrain.py` in the directory where you downloaded the scripts. Note that the program can be slow to initialize the first time, due to kata's gpu tuning.

### Installation for Linux/Mac users

* This assumed you have a working Python 3.6/3.7 installation as a default. If your default is python 2, use pip3/python3. Kivy currently does not have a release for Python 3.8.
* Git clone or download the repository.
* `pip install -U kivy numpy`
* Put your KataGo binary in the `KataGo/` directory or change the `engine.command` field in `config.json` to your KataGo v1.3.5+ binary.
    *  Compiled binaries and source code can be found [here](https://github.com/lightvector/KataGo/releases).
    * You will need to `chmod +x katago` your binary if you downloaded it.  
    * Executables for Mac are not available, so compiling from source code is required there.
* Start the app by running `python katrain.py`.  Note that the program can be slow to initialize the first time, due to KataGo's GPU tuning.

## Manual

### Play

* Human is simple play with potential feedback, but without auto-undo.
* Teach will give you instant feedback, and auto-undo bad moves to give you a second chance. 
    * Settings for this mode can be found under 'Configure teacher'
* AI will active the AI in the dropdown next to the buttons.


 
#### AIs
Available AIs are:

* Default is full KataGo, above professional level. 
* Balance is KataGo occasionally making weaker moves, attempting to win by ~2 points. 
* Jigo is KataGo aggressively making weaker moves, attempting to win by 0.5 points.
* Policy is the top move from the policy network (it's 'shape sense' without reading), should be around high dan level depending on the model used.
* P:Pick will pick a `pick_n + pick_frac *  <number of legal moves>` moves at random, and play the best move among them.
   The setting `pick_override` determines the minimum value at which this process is bypassed to play the best move instead, preventing obvious blunders.
   This is probably the best choice for kyu players who want a chance of winning. Variants of this strategy include:
    * P:Local will pick such moves biased towards the last move with probability related to `local_stddev`.
    * P:Tenuki is biased in the opposite way as P:Local, using the same setting.
    * P:Influence is biased towards 4th+ line moves, with every line below that dividing both the chance of considering the move and the policy value by `influence_weight`. Consider setting `pick_frac=1.0` to only affect the policy weight. 
    * P:Territory is biased in the opposite way, towards 1-3rd line moves, using the same setting. 
* P:Noise mixes the policy with `noise_strength` Dirichlet noise. At `noise_strength=0.9` play is near-random, while `noise_strength=0.7` is still quite strong. Regardless, mistakes are typically strange can include senseless first-line moves. 
* `<Pause>` pauses AI moves, in case you want to do analysis without triggering moves, or simply hide the evaluation dots for this player.

Selecting the AI as either white or black opens up the option to configure it under 'Configure AI'.

### Analysis


### Keyboard shortcuts


In addition to these, there are:

* ~ or ` or `p` : Hide side panel UI and only show the board.
* Ctrl-V : Load SGF from clipboard
* Ctrl-C : Save SGF to clipboard
* Ctrl-L : Load SGF from file
* Ctrl-S : Load SGF to file
* Ctrl-N : Load SGF from clipboard


### Configuration

Configuration is stored in `config.json`. Most settings are available to edit in the program, but some are not.
You can use `python katrain.py your_config_file.json` to use another config file instead.

#### The settings panel



The `trainer` block has the following options to tweak for engine assisted play and reviewing:

* `eval_off_show_last`: when the `eval` checkbox is off for a player, show coloured dots on the last this many moves regardless. 
* `undo_eval_threshold`, `undo_point_threshold`: prompt player to undo if move is worse than this in terms of points AND evaluation.

The following options are relevant for the `balance score` AI play mode. 

* `balance_play_target_score`: indicates how many points the AI aims to win by when using 'balance score'.
* `balance_play_randomize_eval`: when not needing to balance score, the AI will pick a random move which is at least this good as long as it stays ahead.
* `balance_play_min_eval`: when needing to balance score, the AI will pick a move which is at least this good.
* `balance_play_min_visits`: never pick a move with fewer playouts than this.

The cfg file has additional configuration for KataGo, which are documented there. 

#### Configuring feedback

* `num_undo_prompts`: automatically undo bad moves when `undo` is on at most this many times. Can be a fraction like 0.5 for 50% chance of being granted an undo on a bad move. 

## FAQ

* The program is slow to start!
  * The first startup of KataGo can be slow, after that it should be much faster.
* The program is running too slowly!
  *  Lower the visits count in the `max_visits` block of `config.json` by half or so and try again.
 

## Contributing

* Feedback and pull requests are both very welcome.
* For suggestions and planned improvements, see the 'issues' tab on github.
