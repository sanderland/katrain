# KataGo troubleshooting

This page lists common ways in which the provided KataGo fails to work out of the box, and how to resolve these issues.
If you find your problem is not in here, you can ask on the [Computer Go Community Discord](https://discord.gg/AjTPFpN) (use the #gui channel),
 providing detailed information about your error.


* [General](#General)
    * [GPU vs CPU](#CPU)
    * [KataGo model versions](#Models)
* [macOS specific help](#Mac)
* [Windows specific help](#Windows)
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

KataGo models have changed over time, and loading a newer model with an older executable can lead to errors.
The transformer models, including the `b10c384h6nbt` model included with KaTrain, require KataGo v1.17.0 or later.
The binaries offered under 'Download KataGo versions' are all recent enough, but if you have selected an older
 KataGo binary of your own, either upgrade it or select an older model, such as one of
 the distributed training models available under 'Download models'.


## <a name="Mac"></a><img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Apple_Logo.svg" alt="macOs" height="35"/> For macOS users

### Running from source

Make sure you `brew install katago` or set the engine path to your own KataGo binary, as there is no executable included.
Homebrew's KataGo uses the Metal backend, which is the fastest option on macOS.

### Which engine the .app bundles

The Apple Silicon .app bundles a KataGo built with the Metal backend, which uses the GPU and Neural Engine and
 requires macOS 13 or later. The Intel .app bundles an OpenCL build.
If the bundled engine does not work on your machine, `brew install katago` and set the engine path to that binary.

### Getting more information about errors

On macOS, the .app distributable will not show a console, so you will need to install via pip/pipx and run `katrain` from a terminal to see console output.

##  <a name="Windows"></a><img src="https://upload.wikimedia.org/wikipedia/commons/5/5f/Windows_logo_-_2012.svg" alt="Windows" height="35"/> For Windows users

### Getting more information about errors

Run `debugkatrain.exe`, which is included next to the main executable in the `KaTrain.zip` distributable on the
 [releases page](https://github.com/sanderland/katrain/releases). This will show a console window which typically tells you more.


## <a name="Linux"></a><img src="https://upload.wikimedia.org/wikipedia/commons/a/ab/Linux_Logo_in_Linux_Libertine_Font.svg" alt="Linux" height="35"/> For Linux users

### libzip compatibility

The most common KataGo issue relates to incompatible library versions, leading to an "Error 127".

* A good alternative is to go [here](https://github.com/lightvector/KataGo) and compile KataGo yourself.
* Installing dependencies mentioned [here](INSTALL.md#LinuxTrouble) may also resolve certain issues with KataGo or the gui.


### Getting more information about errors

* Check the terminal output around startup time.
* Start KataGo by itself using `katrain/KataGo/katago` when running from source and check output.