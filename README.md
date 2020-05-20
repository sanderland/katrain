# KaTrain v1.0.6
[![Supported Python versions](https://img.shields.io/pypi/pyversions/katrain.svg)](#Installation)
[![Latest version on PyPI](https://img.shields.io/pypi/v/katrain.svg)](https://pypi.org/project/katrain)
[![Downloads](https://pepy.tech/badge/katrain)](https://pepy.tech/project/katrain)
![PyPI - License](https://img.shields.io/pypi/l/katrain)
![Build Status](https://github.com/sanderland/katrain/workflows/release/badge.svg)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Discord](https://img.shields.io/discord/417022162348802048?logo=discord)](https://discord.com/channels/417022162348802048/629446365688365067)

KaTrain is a tool for analyzing and playing go with AI feedback from KataGo.

The original idea was to give immediate feedback on the many large mistakes we make in terms of inefficient moves,
but has since grown to include a wide range of features, including:

* Review your games to find the moves that were most costly in terms of points lost.
* Play against AI and get immediate feedback on mistakes with option to retry.
* Play against a wide range of weakened versions of AI with various styles.
* Play against a stronger player and use the retry option instead of handicap stones.
* Automatically generate focused SGF reviews which show your biggest mistakes.

## Animated Screenshots

| Analyze games  | Play against an AI Teacher |
| ------------- | ------------- |
| ![screenshot](katrain/img/anim_analyze.gif)  | ![screenshot](katrain/img/anim_teach.gif)  |

## Quickstart

* You can right-click most button or checkbox labels to get a tooltip with help.
* To analyze a game, load it using the button in the bottom right, or press `ctrl-L`
* To play against AI, pick an AI from the dropdown and either 'human' or 'teach' for yourself and start playing.
    * For different board sizes, use the button with the little goban in the bottom right for a new game.

## Installation
* See the [releases tab](https://github.com/sanderland/katrain/releases) for pre-built installers for windows.
* Alternatively use `pip3 install -U katrain` to install the latest version from PyPI on any OS.
    * Note that on MacOS you will need to set up KataGo using brew, as described [here](INSTALL.md).
* See [here](INSTALL.md#MacPrereq) for detailed instructions for running from source files on Window, Linux and MacOS,
  as well as setting up KataGo to use multiple GPUs.

## Manual

### Play

Under the 'play' tab you can select who is playing black and white.

* Human is simple play with potential feedback, but without auto-undo.
* Teach will give you instant feedback, and auto-undo bad moves to give you a second chance.
    * Settings for this mode can be found under 'Configure Teacher'
* AI will activate the AI in the dropdown menu next to the buttons.
    * Settings for all AIs can be found under 'Configure AIs'

If you do not want to see 'Points lost' or other feedback for your moves,
 set 'show last n dots' to 0 under 'Configure Teacher', and click on the words 'Points lost' to hide its value.

#### What are all these coloured dots?

The dots indicate how many points were lost by that move.

* The colour indicates the size of the mistake according to KataGo
* The size indicates if the mistake was actually punished. Going from fully punished at maximal size,
  to no actual effect on the score at minimal size.

In short, if you are a weaker player you should mostly on large dots that are red or purple,
while stronger players can pay more attention to smaller mistakes. If you want to hide some colours, you 
can do so under 'Configure Teacher'.

#### AIs

Available AIs, with strength indicating an estimate for the default settings based on their current OGS rankings, are:

* **[9p+]** **Default** is full KataGo, above professional level.
* **(RECOMMENDED)** **[~5k]**  **ScoreLoss** is KataGo making moves with probability `~ e^(-strength * points lost)`, playing a varied style with small mistakes.
* **Balance** is KataGo occasionally making weaker moves, attempting to win by ~2 points.
* **Jigo** is KataGo aggressively making weaker moves, attempting to win by 0.5 points.
* **[~4d]** **Policy** uses the top move from the policy network (it's 'shape sense' without reading), should be around high dan level depending on the model used. There is a setting to increase variety in the opening, but otherwise it plays deterministically.
* **(RECOMMENDED)** **[~3k]**: **P:Weighted** picks a random move weighted by the policy, as long as it's above `lower_bound`. `weaken_fac` uses `policy^(1/weaken_fac)`, increasing the chance for weaker moves.
* **[~7k]**: **P:Pick** picks `pick_n + pick_frac *  <number of legal moves>` moves at random, and play the best move among them.
   The setting `pick_override` determines the minimum value at which this process is bypassed to play the best move instead, preventing obvious blunders.
   This, along with 'Weighted' are probably the best choice for kyu players who want a chance of winning without playing the sillier bots below. Variants of this strategy include:
    * **[~3k]**: **P:Local** will pick such moves biased towards the last move with probability related to `local_stddev`.
    * **[~5k]**: **P:Tenuki** is biased in the opposite way as P:Local, using the same setting. After about half the board is filled, it stops and plays like P:Pick.
    * **[~6k]**: **P:Influence** is biased towards 4th+ line moves, with every line below that dividing both the chance of considering the move and the policy value by `influence_weight`. Consider setting `pick_frac=1.0` to only affect the policy weight.
    * **[~8k]**: **P:Territory** is biased in the opposite way, towards 1-3rd line moves, using the same setting. Both of these also stop the strategy in endgame and revert to P:Pick.

The Engine based AIs (Default, ScoreLoss, Balance, Jigo) are affected by both the model and choice of max_visits/max_time,
 while the Policy net based AIs (Policy, P:...) are affected by the choice of model file, but work identically with 'max_visits' set to 1. 

### Analysis

Keyboard shortcuts are shown with **[key]**.

* The checkboxes configure:
    * **[q]**: Child moves are shown. On by default, can turn it off to avoid obscuring other information or when wanting to guess the next move.
    * **[w]**: All dots: Show all evaluation dots instead of the last few.
        * You can configure how many are shown with this setting off, and whether they are shown for AIs under 'Play/Configure Teacher'.
    * **[e]**: Top moves: Show the next moves KataGo considered, colored by their expected point loss. Small dots indicate high uncertainty. Hover over any of them to see the principal variation.
    * **[r]**: Show owner: Show expected ownership of each intersection.
    * **[t]**: NN Policy: Show KataGo's policy network evaluation, i.e. where it thinks the best next move is purely from the position, and in the absence of any 'reading'.

* The analysis buttons are used for:
    * **[a]**: Extra: Re-evaluate the position using more visits, usually resulting in a more accurate evaluation.
    * **[s]**: Equalize: Re-evaluate all currently shown next moves with the same visits as the current top move. Useful to increase confidence in the suggestions with high uncertainty.
    * **[d]**: Sweep: Evaluate all possible next moves. This can take a bit of time even though 'fast_visits' is used, but the result is nothing if not colourful.

## Keyboard and mouse shortcuts

In addition to shortcuts mentioned above, there are:

* **[Tab]**: to switch between analysis and play modes. (NB. keyboard shortcuts function regardless)
* **[~]** or **[`]** or **[m]**: Hide side panel UI and only show the board.
* **[enter]**: AI Move
* **[p]**: Pass
* **[spacebar]**: Pause/Resume timer
* **[arrow up]** or **[z]**: Undo move. Hold shift for 10 moves at a time, or ctrl to skip to the start.
* **[arrow down]** or **[x]**: Redo move. Hold shift for 10 moves at a time, or ctrl to skip to the start.
* **[scroll up]**: Undo move. Only works when hovering the cursor over the board.
* **[scroll down]**: Redo move. Only works when hovering the cursor over the board.
* **[click on a move]**: See detailed statistics for a previous move, along with expected variation that was best instead of this move.
* **[double-click on a move]**: Navigate directly to that point in the game.
* **[Ctrl-v]**: Load SGF from clipboard and do a 'fast' analysis of the game (with a high priority normal analysis for the last move).
* **[Ctrl-c]**: Save SGF to clipboard.
* **[Ctrl-l]**: Load SGF from file and do a normal analysis.
* **[Ctrl-s]**: Save SGF with automated review to file.
* **[Ctrl-n]**: Load SGF from clipboard


## Configuration

Configuration is stored in `config.json`. Most settings are now available to edit in the program, but some advanced options are not.
You can use `python katrain.py your_config_file.json` to use another config file instead.

If you ever need to reset to the original settings, simply re-download the `config.json` file in this repository.

### Settings Panel

* engine settings
    * These settings can be updated anytime:
        * max_visits: The number of visits used in analyses and AI moves, higher is more accurate but slower.
        * max_time: Maximal time in seconds for analyses, even when the target number of visits has not been reached.    
        * fast_visits: The number of visits used for certain operations with fewer visits.
        * wide_root_noise: Consider a wider variety of moves, using KataGo's `analysisWideRootNoise` option. Will affect both analysis and AIs such as ScoreLoss. (KataGo 1.4+ only, keep at 0.0 otherwise)
    * These settings cause the engine to be restarted:
        * katago: Path to your KataGo executable. If blank, as is the default, uses the included binaries on windows/linux, or 'katago' on MacOS (which assumes you have installed KataGo yourself).
        * model: Path to your KataGo model file. Note that the default model file included is an older 15 block one for high speed and low memory requirements. Replace it with a new model from [here](https://github.com/lightvector/KataGo/releases) for maximal strength.
        * config: Path to your KataGo config file.    
        * threads: Number of threads to use in the KataGo analysis engine.
* game settings
    * init_size: the initial size of the board, on start-up.
    * init_komi: likewise, for komi.
* sgf settings
    * sgf_load: default path where the load SGF dialog opens.
    * sgf_save: path where SGF files are saved.    
* board_ui settings
    * anim_pv_time: time in seconds between each stone when animating variations. 
    * eval_dot_max_size: size of coloured dots when point size is maximal, relative to stone size.
    * eval_dot_min_size: size of coloured dots when point size is minimal
    * ... various other minor cosmetic options.
* debug settings
    * level: determines the level of output in the console, where 0 shows no debug output, 1 shows some and 2 shows a lot. This is mainly used for reporting bugs.

## FAQ

* The program is running too slowly. How can I speed it up?
  *  Adjust the number of visits or maximum time allowed in the settings.
* KataGo crashes with out of memory errors, how can I prevent this?
  *  Try using a lower number for `nnMaxBatchSize` in `KataGo/analysis_config.cfg`, and avoid using versions compiled with large board sizes.
* How can I play on larger boards?
  * For windows, change the `katago` setting to `katrain\KataGo\katago-bs52.exe`. For other operating systems, you need to compile your own KataGo version with higher limits.

## Contributing

* Feedback and pull requests are both very welcome. I would also be happy to host translations of this manual into languages where English fluency is typically lower.
* For suggestions and planned improvements, see the 'issues' tab on github.
* You can also contact me on [discord](https://discord.gg/AjTPFpN) (Sander#3278), [KakaoTalk](https://open.kakao.com/o/gTsMJCac) or [Reddit](http://reddit.com/u/sanderbaduk) to give feedback, or simply show your appreciation.
* Some people have also asked me how to donate. Something go-related such as a book or teaching time is highly appreciated.
