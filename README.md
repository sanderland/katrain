# <a name="manual"></a> KaTrain

[![Latest Release](http://img.shields.io/github/release/sanderland/katrain?label=download)](http://github.com/sanderland/katrain/releases)
[![License:MIT](http://img.shields.io/pypi/l/katrain)](http://en.wikipedia.org/wiki/MIT_License)
[![GitHub Downloads](http://img.shields.io/github/downloads/sanderland/katrain/total?color=%23336699&label=github%20downloads)](http://github.com/sanderland/katrain/releases)
[![PyPI Downloads](http://pepy.tech/badge/katrain)](http://pepy.tech/project/katrain)
[![Discord](http://img.shields.io/discord/417022162348802048?logo=discord)](http://discord.com/channels/417022162348802048/629446365688365067)

KaTrain is a tool for analyzing games and playing go with AI feedback from KataGo:

* Review your games to find the moves that were most costly in terms of points lost.
* Play against AI and get immediate feedback on mistakes with option to retry.
* Play against a wide range of weakened versions of AI with various styles.
* Automatically generate focused SGF reviews which show your biggest mistakes.

## Manual

<table>
<td>

- [ KaTrain](#-katrain)
  - [Manual](#manual)
  - [  Preview and Youtube Videos](#--preview-and-youtube-videos)
  - [ Installation](#-installation)
  - [  Configuring KataGo](#--configuring-katago)
  - [ Play against AI](#-play-against-ai)
    - [Instant feedback](#instant-feedback)
    - [AIs](#ais)
  - [ Analysis](#-analysis)
  - [ Keyboard and mouse shortcuts](#-keyboard-and-mouse-shortcuts)
  - [ Contributing to distributed training](#-contributing-to-distributed-training)
  - [ Themes](#-themes)
  - [ FAQ](#-faq)
  - [ Support / Contribute](#-support--contribute)


<td>

<a href="http://github.com/sanderland/katrain/blob/master/README.md"><img alt="English" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-uk.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=de&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="German" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-de.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=fr&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="French" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-fr.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=uk&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Ukrainian" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-ua.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=ru&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Russian" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-ru.png" width=50></a>
<br/>
<a href="http://translate.google.com/translate?sl=en&tl=tr&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Turkish" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-tr.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=zh-CN&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Simplified Chinese" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-cn.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=zh-TW&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Traditional Chinese" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-tw.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=ko&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Korean" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-ko.png" width=50></a>
<a href="http://translate.google.com/translate?sl=en&tl=ja&u=https%3A%2F%2Fgithub.com%2Fsanderland%2Fkatrain%2Fblob%2Fmaster%2FREADME.md"><img alt="Japanese" src="https://github.com/sanderland/katrain/blob/master/katrain/img/flags/flag-jp.png" width=50></a>

</td>
</table>

## <a name="preview"></a>  Preview and Youtube Videos

<img alt="screenshot" src="https://raw.githubusercontent.com/sanderland/katrain/master/screenshots/analysis.png" width="550">

| **Local Joseki Analysis**                  | **Analysis Tutorial**                                                                              | **Teaching Game Tutorial**                                                                                   |
|:-----------------------------------------------------------------------------------------------------:|:-----------------------------------------------------------------------------------------------------:|:------------------------------------------------------------------------------------------------------------:|
| [![Local Joseki Analysis Video](http://i.imgur.com/YcpmSBx.png)](https://www.youtube.com/watch?v=tXniX57KtKk) | [![Analysis Tutorial](http://i.imgur.com/3EP4IEr.png)](http://www.youtube.com/watch?v=qjxkcKgrsbU) | [![ Teaching Game Tutorial](http://i.imgur.com/jAdcSL5.png)](http://www.youtube.com/watch?v=wFl4Bab_eGM)   |



## <a name="install"></a> Installation
* See the [releases page](http://github.com/sanderland/katrain/releases) for downloadable executables for Windows and macOS.
* Alternatively use `pip3 install -U katrain` to install the latest version from PyPI on any 64-bit OS.
* On macOS, you can also use `brew install katrain` to install the app.
* [This page](https://github.com/sanderland/katrain/blob/master/INSTALL.md) has detailed instructions for Window, Linux and macOS,
  as well as troubleshooting and setting up KataGo to use multiple GPUs.

## <a name="kata"></a>  Configuring KataGo

KaTrain comes pre-packaged with a working KataGo (OpenCL version) for Windows, Linux, and pre-M1 Mac operating systems, and the rather old 15 block model.

To change the model, open 'General and Engine settings' in the application and 'Download models'. You can then select the model you want from the dropdown menu.

To change the katago binary, e.g. to the Eigen/CPU version if you don't have a GPU, click 'Download KataGo versions'.
  You can then select the KataGo binary from the dropdown menu.
There are also CUDA and TensorRT versions available on [the KataGo release site](https://github.com/lightvector/KataGo/releases). Particularly the latter may offer much better performance on NVIDIA GPUs, but will be harder to 
set up: [see here for more details](https://github.com/lightvector/KataGo#opencl-vs-cuda-vs-tensorrt-vs-eigen).

Finally, you can override the entire command used to start the analysis engine, which 
 can be useful for connecting to a remote server. Do keep in mind that KaTrain uses the *analysis engine*
 of KataGo, and not the GTP engine.


## <a name="ai"></a> Play against AI

* Select the players in the main menu, or under 'New Game'.
* In a teaching game, KaTrain will analyze your moves and automatically undo those that are sufficiently bad.
* When playing against AI, note that the "Undo" button will undo both the AI's last move and yours.

### Instant feedback

The dots on the move indicate how many points were lost by that move.

* The colour indicates the size of the mistake according to KataGo
* The size indicates if the mistake was actually punished. Going from fully punished at maximal size,
  to no actual effect on the score at minimal size.

In short, if you are a weaker player you should mostly focus on large dots that are red or purple,
while stronger players can pay more attention to smaller mistakes. If you want to hide some colours
on the board, or not output details for them in SGFs,you can do so under 'Configure Teacher'.

### AIs

This section describes the available AIs.

In the 'AI settings', settings which have been tested and calibrated are at the top and have a lighter color,
changing these will show an estimate of rank.
This estimate should be reasonably accurate as long as you have not changed the other settings.

* Recommended options for serious play include:
    * **KataGo** is full KataGo, above professional level. The analysis and feedback given is always based on this full strength KataGo AI.
    * **Calibrated Rank Bot** was calibrated on various bots (e.g. GnuGo and Pachi at different strength settings) to play a balanced
     game from the opening to the endgame without making serious (DDK) blunders. Further discussion can be found
      [here](http://github.com/sanderland/katrain/issues/44) and [here](http://github.com/sanderland/katrain/issues/74).
    * **Simple Style** Prefers moves that solidify both player's territory, leading to relatively simpler moves.
* Legacy options which were developed earlier include: 
    * **ScoreLoss** is KataGo analyzing as usual, but
      choosing from potential moves depending on the expected score loss, leading to a varied style with mostly small mistakes.
    * **Policy** uses the top move from the policy network (it's 'shape sense' without reading).
    * **Policy Weighted** picks a random move weighted by the policy, leading to a varied style with mostly small mistakes, and occasional blunders due to a lack of reading.
    * **Blinded Policy** picks a number of moves at random and play the best move among them, being effectively 'blind' to part of the board each turn. Calibrated rank is based on the same idea, and recommended over this option.
* Options that are more on the 'fun and experimental' side include: 
    * Variants of **Blinded Policy**, which use the same basic strategy, but with a twist:
       * **Local Style** will consider mostly moves close to the last move.
       * **Tenuki Style** will consider mostly moves away from the last move.
       * **Influential Style** will consider mostly 4th+ line moves, leading to a center-oriented style.
       * **Territory Style** is biased in the opposite way, towards 1-3rd line moves.
    * **KataJigo** is KataGo attempting to win by 0.5 points, typically by responding to your mistakes with an immediate mistake of it's own.
    * **KataAntiMirror** is KataGo assuming you are playing mirror go and attempting to break out of it with profit as long as you are.
    
The Engine based AIs (KataGo, ScoreLoss, KataJigo) are affected by both the model and choice of visits and maximum time,
 while the policy net based AIs are affected by the choice of model file, but work identically with 1 visit.

Further technical details and discussion on some of these AIs can be found on [this](http://lifein19x19.com/viewtopic.php?f=10&t=17488&sid=b11e42c005bb6f4f48c83771e6a27eff) thread at the life in 19x19 forums.

## <a name="analysis"></a> Analysis

Analysis options in KaTrain allow you to explore variations and request more in-depth analysis from the engine at any point in the game.

| Key            | Short Description                      | Details                                                                                                                                                                                                                                                                                               |
| -------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <kbd>Tab</kbd> | Switch between analysis and play modes | AI moves, teaching mode and timers are suspended in analysis mode. The state of the analysis options and right-hand side panels and options is saved independently for 'play' and 'analyze', allowing you to quickly switch between a more minimalistic 'play' mode and more complex 'analysis' mode. |

The checkboxes at the top of the screen:

| Key          | Short Description     | Details                                                                                                                                                                                                                                     |
| ------------ | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <kbd>q</kbd> | Child moves are shown | On by default, can turn it off to avoid obscuring other information or when wanting to guess the next move.                                                                                                                                 |
| <kbd>w</kbd> | Show all dots         | Toggles showing coloured evaluation 'dots' on the last few moves or not. You can configure the thresholds, along with how many of the last moves they are shown for under 'Teaching/Analysis Settings'.                                     |
| <kbd>e</kbd> | Top moves             | Show the next moves KataGo considered, colored by their expected point loss. Small/faint dots indicate high uncertainty and never show text (lower than your 'fast visits' setting). Hover over any of them to see the principal variation. |
| <kbd>r</kbd> | Policy moves          | Show KataGo's policy network evaluation, i.e. where it thinks the best next move is purely from the position, and in the absence of any 'reading'. This turns off the 'top moves' setting as the overlap is often not useful.               |
| <kbd>t</kbd> | Expected territory    | Show expected ownership of each intersection.                                                                                                                                                                                               |

The analysis options available under the 'Analysis' button are used for deeper evaluation of the position:

| Key                                 | Short Description                                                                                            | Details                                                                                                                                                                                                                      |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <kbd>a</kbd>                        | Deeper analysis                                                                                              | Re-evaluate the position using more visits, usually resulting in a more accurate evaluation.                                                                                                                                 |
| <kbd>s</kbd>                        | Equalize visits                                                                                              | Re-evaluate all currently shown next moves with the same visits as the current top move. Useful to increase confidence in the suggestions with high uncertainty.                                                             |
| <kbd>d</kbd>                        | Analyze all moves                                                                                            | Evaluate all possible next moves. This can take a bit of time even though 'fast_visits' is used, but can be useful to see how many reasonable next moves are available.                                                      |
| <kbd>f</kbd>                        | Find alternatives                                                                                            | Increases analysis of current candidate moves to at least the 'fast visits' level, and request a new query that excludes all current candidate moves.                                                                        |
| <kbd>g</kbd>                        | Select area of interest                                                                                      | Set an area and search only for moves in this box. Good for solving tsumegos. Note that some results may appear outside the box due to establishing a baseline for the best move, and the opponent can tenuki in variations. |
| <kbd>h</kbd>                        | Reset analysis                                                                                               | This reverts the analysis to what the engine returns after a normal query, removing any additional exploration.                                                                                                              |
| <kbd>i</kbd>                        | Start insertion mode                                                                                         | Allows you to insert moves, to improve analysis when both players ignore an important exchange or life and death situation. Press again to stop inserting and copy the rest of the branch.                                   |
| <kbd>l</kbd>                        | Play out the game until the end and add as a collapsed branch, to visualize the potential effect of mistakes | This is done in the background, and can be started at several nodes at once when comparing the results at different starting positions.                                                                                      |
| <kbd>Space</kbd>                    | Turn continuous analysis on/off.                                                                             | This will continuously improve analysis of the current position, similar to Lizzie's 'pondering', but only when there are no other queries going on.                                                                         |
| <kbd>Shift</kbd> + <kbd>Space</kbd> | As above, but does not turn 'top moves' hints on when it is off.                                             |                                                                                                                                                                                                                              |
| <kbd>Enter</kbd>                    | AI move                                                                                                      | Makes the AI move for the current player regardless of current player selection.                                                                                                                                             |
| <kbd>F2</kbd>                       | Deeper full game analysis                                                                                    | Analyze the entire game to a higher number of visits.                                                                                                                                                                        |
| <kbd>F3</kbd>                       | Performance report                                                                                           | Show an overview of performance statistics for both players.                                                                                                                                                                 |
| <kbd>F10</kbd>                      | Tsumego Frame                                                                                                | After placing a life and death problem in a corner/side, use this to fill up the rest of the board to improve AI's ability in solving life and death problems.                                                               |

## <a name="keyboard"></a> Keyboard and mouse shortcuts

In addition to shortcuts mentioned above and those shown in the main menu:

| Key                                            | Short Description                                                                    | Details                                                                                                                                 |
| ---------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| <kbd>Alt</kbd>                                 | Open the main menu                                                                   |                                                                                                                                         |
| <kbd>~</kbd> or <kbd>`</kbd> or <kbd>F12</kbd> | Cycles through more minimalistic UI modes                                            |                                                                                                                                         |
| <kbd>k</kbd>                                   | Toggle display of board coordinates                                                  |                                                                                                                                         |
| <kbd>p</kbd>                                   | Pass                                                                                 |                                                                                                                                         |
| <kbd>Pause</kbd>                               | Pause/Resume timer                                                                   |                                                                                                                                         |
| <kbd>←</kbd> or <kbd>z</kbd>                   | Undo move                                                                            | Hold shift for 10 moves at a time, or ctrl to skip to the start.                                                                        |
| <kbd>→</kbd> or <kbd>x</kbd>                   | Redo move                                                                            | Hold shift for 10 moves at a time, or ctrl to skip to the end.                                                                          |
| <kbd>↑</kbd>/<kbd>↓</kbd>                      | Switch branch                                                                        | As would be expected from the move tree.                                                                                                |
| <kbd>Home</kbd>/<kbd>End</kbd>                 | Go to the beginning/end of the game                                                  |                                                                                                                                         |
| <kbd>PageUp</kbd>                              | Make the currently selected node the main branch                                     |                                                                                                                                         |
| <kbd>Ctrl</kbd> + <kbd>Delete</kbd>            | Delete current node                                                                  |                                                                                                                                         |
| <kbd>c</kbd>                                   | Collapse/Uncollapse the branch from the current node to the previous branching point |                                                                                                                                         |
| <kbd>b</kbd>                                   | Go back to the previous branching point                                              |                                                                                                                                         |
| <kbd>Shift</kbd> + <kbd>b</kbd>                | Go back the main branch                                                              |                                                                                                                                         |
| <kbd>n</kbd>                                   | Go to one move before the next mistake (orange or worse) by a human player           | As in clicking the forward red arrow                                                                                                    |
| <kbd>Shift</kbd> + <kbd>n</kbd>                | Go to one move before the previous mistake                                           | As in clicking the backward red arrow                                                                                                   |
| Scroll Mouse                                   | Redo/Undo move or Scroll through principal variation                                 | When hovering the cursor over the right panel: Redo/Undo move. When hovering over a candidate move: Scroll through principal variation. |
| Middle Scroll Wheel Click                      | Add principal variation to the move tree                                             | When scrolling, only moves up to the point you are viewing are added.                                                                   |
| Click on a Move                                | See detailed statistics for a previous move                                          | Along with expected variation that was best instead of this move                                                                        |
| Double Click on a Move                         | Navigate directly to just before that point in the game                              |                                                                                                                                         |
| <kbd>Ctrl</kbd> + <kbd>v</kbd>                 | Load SGF from the clipboard and do a 'fast' analysis of the game                     | With a high priority normal analysis for the last move.                                                                                 |
| <kbd>Ctrl</kbd> + <kbd>c</kbd>                 | Save SGF to clipboard                                                                |                                                                                                                                         |
| <kbd>Escape</kbd>                              | Stop all analysis                                                                    |                                                                                                                                         |

## <a name="distributed"></a> Contributing to distributed training

Starting in December 2020, KataGo started [distributed training](https://katagotraining.org/).
This allows people to all help generate self-play games to increase KataGo's strength and train bigger models.

KaTrain 1.8.0+ makes it easy to contribute to distributed training: simply select the option from the main menu, register an account, and click run.
During this mode you can do little more than watch games.

Keep in mind that partial games are not uploaded,
so it is best to plan to keep it running for at least an hour, if not several, for the most effective contribution.

A few keyboard shortcuts have special functions in this mode:

| Key               | Short Description                                                  | Details                                                                                                |
| ----------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| <kbd>Space</kbd>  | Switch between manually navigating the current game                | And automatically advancing it.                                                                        |
| <kbd>Escape</kbd> | Sends the `quit` command to KataGo                                 | Which starts a slow shutdown, finishing partial games but not starting new ones. Only works on v1.11+. |
| <kbd>Pause</kbd>  | Pauses/resumes contributions via the `pause` and `resume` commands | Introduced in KataGo v1.11                                                                             |

## <a name="themes"></a> Themes

See [these instructions](THEMES.md) for how to modify the look of any graphics or colours, and creating or install themes.
   
## <a name="faq"></a> FAQ

* The program is running too slowly. How can I speed it up?
  *  Adjust the number of visits or maximum time allowed in the settings.
* KataGo crashes with "out of memory" errors, how can I prevent this?
  * Try using a lower number for `nnMaxBatchSize` in `KataGo/analysis_config.cfg`, and avoid using versions compiled with large board sizes.
  * If still encountering problems, please start KataGo by itself to check for any errors it gives.
  * Note that if you don't have a GPU, or your GPU does not support OpenCL, you should use the 'eigen' binaries which run on CPU only.
* The font size is too small
  * On some ultra-high resolution monitors, dialogs and other elements with text can appear too small. Please see [these](https://github.com/sanderland/katrain/issues/359#issuecomment-784096271) instructions to adjust them.
* The app crashes with an error about "unable to find any valuable cutbuffer provider"
  * Install xclip using `sudo apt-get install xclip`


## <a name="support"></a> Support / Contribute

[![GitHub issues](http://img.shields.io/github/issues/sanderland/katrain)](http://github.com/sanderland/katrain/issues)
[![Contributors](http://img.shields.io/static/v1?label=contributors&message=<3&color=dcb424)](CONTRIBUTIONS.md)

 * Ideas, feedback, and contributions to code or translations are all very welcome.
    * For suggestions and planned improvements, see [open issues](http://github.com/sanderland/katrain/issues) on github to check if the functionality is already planned.
* You can join the [Computer Go Community Discord (formerly Leela Zero & Friends)](http://discord.gg/AjTPFpN) (use the #gui channel) to get help, discuss improvements, or simply show your appreciation. Please do not use github issues to ask for technical help, this is only for bugs, suggestions and discussing contributions.



