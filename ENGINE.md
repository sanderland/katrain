# KataGo troubleshooting

This page lists common ways in which the provided KataGo fails to work out of the box, and how to resolve these issues.
If you find your problem is not in here, you can ask on the [Leela Zero & Friends Discord](http://discord.gg/AjTPFpN) (use the #gui channel),
 providing detailed information about your error.  


* [General](#General)
    * [GPU vs CPU](#CPU)
* [Windows specific help](#Windows)
* [MacOS specific help](#Mac)
* [Linux specific help](#Linux)



## <a name="General"></a> General

###  <a name="CPU"></a> GPU vs CPU

The standard executables assume you have a compatible graphics card (GPU). 
If you don't, KataGo will fail to start in ways that are difficult for KaTrain to pick up.  

On Windows and Linux, you should be able to resolve this by:

* Going to general and engine settings (F8)
* Click 'download katago versions' and wait for downloads to finish.
* Select a CPU based KataGo version (named 'Eigen' after the library it uses).

Keep in mind that a CPU based engine can be significantly slower, and you may want to set your maximum number of
visits to a lower number to compensate for this.

###  <a name="Models"></a> KataGo model versions

KataGo models have changed over time, and selecting an older executable with a newer model can lead to errors.
Of the provided binaries, this is typically the case for the 1.6.1 'bigger boards' binary, which should
 only be used with the standard 15/20/30/40 block models, and not the newer distributed training models.


## <a name="Mac"></a><img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Apple_Logo.svg" alt="macOs" height="35"/> For macOS users

### Running from source

Make sure you `brew install katago` or set the engine path to your own KataGo binary, as there is no executable included.

### New Macs with M1 architecture

Make sure you `brew install katago` as the provided executable does not work on rosetta.

### Getting more information about errors

On macOS, the .app distributable will not show a console, so you will need install using `pip` to see the console window.

##  <a name="Windows"></a><img src="https://upload.wikimedia.org/wikipedia/commons/5/5f/Windows_logo_-_2012.svg" alt="Windows" height="35"/> For Windows users

### Getting more information about errors

Run DebugKaTrain.exe, which is released in the .zip file distributable in releases. This will show a console window
 which typically tells you more.


## <a name="Linux"></a><img src="https://upload.wikimedia.org/wikipedia/commons/a/ab/Linux_Logo_in_Linux_Libertine_Font.svg" alt="Linux" height="35"/> For Linux users

### libzip compatibility

The most common KataGo issue relates to incompatible library versions, leading to an "Error 127".

* A good alternative is to go [here](https://github.com/lightvector/KataGo) and compile KataGo yourself.
* Installing dependencies mentioned [here](INSTALL.md#LinuxTrouble) may also resolve certain issues with KataGo or the gui.


### Getting more information about errors

* Check the terminal output around startup time.
* Start KataGo by itself using `katrain/KataGo/katago` when running from source and check output.