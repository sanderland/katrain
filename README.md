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

### Quick Installation for Windows users
* See the releases tab for pre-built installers

### Installation from source for Windows users
* Download the repository by clicking the green *Clone or download* on this page and *Download zip*. Extract the contents.
* Make sure you have a python installation, I will assume Anaconda (Python 3.7), available [here](https://www.anaconda.com/distribution/#download-section). 
* Open 'Anaconda prompt' from the start menu and navigate to where you extracted the zip file using the `cd <folder>` command.
* Execute the command `pip install numpy kivy_deps.glew kivy_deps.sdl2 kivy_deps.gstreamer kivy`
* Start the app by running `python katrain.py` in the directory where you downloaded the scripts. Note that the program can be slow to initialize the first time, due to kata's gpu tuning.

### Installation for Linux/Mac users

* This assumed you have a working Python 3.6/3.7 installation as a default. If your default is python 2, use pip3/python3. Kivy currently does not have a release for Python 3.8.
* Git clone or download the repository.
* `pip install kivy numpy`
* Put your KataGo binary in the `KataGo/` directory or change the `engine.command` field in `config.json` to your KataGo v1.3.5+ binary.
    *  Compiled binaries and source code can be found [here](https://github.com/lightvector/KataGo/releases).
    * You will need to `chmod +x katago` your binary if you downloaded it.  
    * Executables for Mac are not available, so compiling from source code is required there.
* Start the app by running `python katrain.py`.  Note that the program can be slow to initialize the first time, due to KataGo's GPU tuning.

## Quickstart
* To analyze a game, load it using the button in the top right, or press `ctrl-L`
* To play against AI, pick an AI from the drop down a color and either 'human' or 'teach' for yourself and start playing.
    * For different board sizes, use the button with the little goban in the bottom right for a new game.
            
## Manual

[Screenshot]

### Play

* Human is simple play with potential feedback, but without auto-undo.
* Teach will give you instant feedback, and auto-undo bad moves to give you a second chance. 
    * Settings for this mode can be found under 'Configure teacher'
* AI will activate the AI in the dropdown next to the buttons.
    * Settings for the selected AI(s) can be found under 'Configure AI'
 
#### AIs
Available AIs, with strength indicating an estimate for the default settings, are:

* **9p**: **Default** is full KataGo, above professional level. 
* **Balance** is KataGo occasionally making weaker moves, attempting to win by ~2 points. 
* **Jigo** is KataGo aggressively making weaker moves, attempting to win by 0.5 points.
* **~4d**: **Policy** is the top move from the policy network (it's 'shape sense' without reading), should be around high dan level depending on the model used.
* **~1d**: **P:Weighted** will pick a random move weighted by the policy, as long as it's above `lower_bound`. `weaken_fac` uses policy^(1/weaken_fac), increasing the chance for weaker moves.
* **~5k**: **P:Pick** will pick a `pick_n + pick_frac *  <number of legal moves>` moves at random, and play the best move among them.
   The setting `pick_override` determines the minimum value at which this process is bypassed to play the best move instead, preventing obvious blunders.
   This is probably the best choice for kyu players who want a chance of winning. Variants of this strategy include:
    * **~3k**: **P:Local** will pick such moves biased towards the last move with probability related to `local_stddev`.
    * **~10k**: **~P:Tenuki** is biased in the opposite way as P:Local, using the same setting.
    * **~7k**: P:Influence is biased towards 4th+ line moves, with every line below that dividing both the chance of considering the move and the policy value by `influence_weight`. Consider setting `pick_frac=1.0` to only affect the policy weight. 
    * **~7k**: P:Territory is biased in the opposite way, towards 1-3rd line moves, using the same setting. 
* * **~7k**: P:Noise mixes the policy with `noise_strength` Dirichlet noise. At `noise_strength=0.9` play is near-random, while `noise_strength=0.7` is still quite strong. Regardless, mistakes are typically strange can include senseless first-line moves. 
* `<Pause>` pauses AI moves, in case you want to do analysis without triggering moves, or simply hide the evaluation dots for this player.

Selecting the AI as either white or black opens up the option to configure it under 'Configure AI'.

### Analysis

* The checkboxes have the following keyboard shortscuts, and they configure:
    * **[q]**: Child moves are shown. On by default, can turn it off to avoid obscuring other information or when wanting to guess the next move.
    * **[w]**: All dots: Show all evaluation dots instead of the last few. You can configure how many are shown with thsi setting off under 'Configure Teacher'.
    * **[e]**:
    


### Keyboard shortcuts


In addition to these, there are:

* Tab to switch between analysis and play modes. (NB. keyboard shortcuts function regardless)
* ~ or ` or p : Hide side panel UI and only show the board.
* Ctrl-v : Load SGF from clipboard
* Ctrl-c : Save SGF to clipboard
* Ctrl-l : Load SGF from file
* Ctrl-s : Load SGF to file
* Ctrl-n : Load SGF from clipboard


### Configuration

Configuration is stored in `config.json`. Most settings are now available to edit in the program, but
 some cosmetic options are now.
You can use `python katrain.py your_config_file.json` to use another config file instead.

If you ever need to reset to the original settings, simply re-download the `config.json` file in this repository.

## FAQ

* The program is slow to start!
  * The first startup of KataGo can be slow, after that it should be much faster.
* The program is running too slowly!
  *  Lower the visits count in the `max_visits` block of `config.json` by half or so and try again.
 

## Contributing

* Feedback and pull requests are both very welcome.
* For suggestions and planned improvements, see the 'issues' tab on github.
