# KaTrain Installation

* [Quick install guide for MacOS](#MacQuick)
    * [Troubleshooting and installation from sources](#MacSources)
* [Quick install guide for Windows](#WindowsQuick)
    * [Troubleshooting and installation from sources](#WindowsSources)
* [Quick install guide for Linux](#LinuxQuick)
    * [Troubleshooting and installation from sources](#LinuxSources)
* [Configuring multiple GPUs](#GPU)
* [Troubleshooting KataGo](#KataGo)

## <img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Apple_Logo.svg" alt="macOs" height="35"/> Installation for macOS users

### <a name="MacQuick"></a>Quick install guide

You can find downloadable macOS installers [on the releases page](https://github.com/sanderland/katrain/releases). Recent releases include both Intel (`KaTrain-*-x86_64.dmg`) and Apple Silicon (`KaTrain-*-arm64.dmg`) installers, so download the one matching your Mac. Mount the `.dmg` and drag the `.app` to your Applications folder.

There is also a [Homebrew](https://brew.sh/) cask: `brew install katrain` downloads and installs a pre-built .app, but note that the cask can lag several versions behind the releases page.

The first time you launch the app, macOS may block it as an app from an unknown developer.
Follow Apple's current guide [here](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unidentified-developer-mh40616/mac):
1. Try opening the app once from Finder.
2. Open `System Settings > Privacy & Security`.
3. In the Security section, click `Open` and then `Open Anyway` for KaTrain.
4. Enter your password to confirm.

This is simply a result of Apple charging $99/year to developers to be 'identified'.

### <a name="MacCommand"></a>Command line install guide

[Open a terminal](https://support.apple.com/guide/terminal/open-or-quit-terminal-apd5265185d-f365-44cb-8b09-71a064a42125/mac) and enter the following commands:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
brew install katago
brew install pipx && pipx ensurepath
pipx install katrain
```
These commands install [Homebrew](https://brew.sh), which simplifies installing packages,
 followed by the KataGo AI, and KaTrain itself in an isolated Python environment.
Now you can start KaTrain by simply typing `katrain` in a (new) terminal.

To upgrade to a newer version, run `pipx upgrade katrain`.

### <a name="MacSources"></a>Troubleshooting and Installation from sources

Installation from sources is essentially the same as for Linux, see [here](#LinuxSources),
 note that you will still need to install your own KataGo, using brew or otherwise. 

If you encounter SSL errors on downloading model files, you may need to follow [these](https://stackoverflow.com/questions/52805115/certificate-verify-failed-unable-to-get-local-issuer-certificate) instructions to fix your certificates.

## <img src="https://upload.wikimedia.org/wikipedia/commons/5/5f/Windows_logo_-_2012.svg" alt="Windows" height="35"/> Installation for Windows users

### <a name="WindowsQuick"></a>Quick install guide

You can find downloadable .exe files for windows [here](https://github.com/sanderland/katrain/releases). 
Simply download and run, everything is included.

### <a name="WindowsSources"></a>Installation from sources

* Download the repository by clicking the green *Code* button on the [repository page](https://github.com/sanderland/katrain) and choosing *Download ZIP*, then extract the contents. Alternatively, `git clone` it.
* Make sure you have a working Python installation, version 3.11 up to 3.13, e.g. from [python.org](https://www.python.org/downloads/) or [Anaconda](https://www.anaconda.com/download).
* Open a command prompt (e.g. 'Anaconda prompt' from the start menu) and navigate to the extracted folder using the `cd <folder>` command.
* Execute the command `pip install .`
* Start the app by running `katrain` in the command prompt.

## <img src="https://upload.wikimedia.org/wikipedia/commons/a/ab/Linux_Logo_in_Linux_Libertine_Font.svg" alt="Linux" height="35"/> Installation for Linux users

### <a name="LinuxQuick"></a>Quick install guide

If you have a working Python 3.11 or later (up to 3.13) available, you should be able to simply:

* Run `pipx install katrain` to install, or `pipx upgrade katrain` to upgrade. Install pipx first if needed, e.g. `sudo apt install pipx`.
  * On distributions which still allow installing packages directly with pip, `pip3 install -U katrain` also works.
* Run the program by executing `katrain` in a terminal.

### <a name="LinuxSources"></a>Installation from sources 

This section describes how to install KaTrain from sources,
 in case you want to run it in a local directory or have more control over the process.
It assumes you have a working Python 3.11-3.13 installation.

* Open a terminal.
* Run the command `git clone https://github.com/sanderland/katrain.git` to download the repository and
  change directory using `cd katrain`.
* Run the command `pip install .` to install the package, or use `--user` to install for your user only.
* Run the program by typing `katrain` in the terminal.
    * If you prefer not to install, you can use [uv](https://docs.astral.sh/uv/): `uv run katrain` creates a virtual
      environment with the locked dependencies from `uv.lock` and starts the app from the local sources.

A binary for KataGo is included, but if you have compiled your own, press F8 to open general settings and change the
 KataGo executable path to the relevant KataGo binary (v1.17.0 or later for the included transformer model, see [ENGINE.md](ENGINE.md#Models)).

### <a name="LinuxTrouble"></a>Troubleshooting and advanced installation from sources

You can try to manually install dependencies to resolve some issues relating to missing dependencies,
 e.g. the binary 'wheel' is not provided, KataGo is not starting, or sounds are not working.
You can also follow these instructions if you don't want to install KaTrain, and just run it locally.

First install the following packages, which are either required for building Kivy, 
 or may help resolve missing dependencies for Kivy or KataGo.
```bash
sudo apt-get install python3-pip build-essential git python3 python3-dev ffmpeg libsdl2-dev libsdl2-image-dev\
    libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev\
    libgstreamer1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good libpulse-dev\
    pkg-config libgl-dev opencl-headers ocl-icd-opencl-dev libzip-dev
```
Then, try installing the python package dependencies into a virtual environment using [uv](https://docs.astral.sh/uv/):
```bash
pip3 install uv  # or see https://docs.astral.sh/uv/getting-started/installation/
uv sync
```
In case the sound is not working, or there is no available wheel for your OS or Python version, try building kivy locally using:
```bash
uv pip uninstall kivy
uv pip install kivy --no-binary kivy
```

You can now start KaTrain by running `uv run katrain`

In case KataGo does not start, an alternative is to go [here](https://github.com/lightvector/KataGo) and compile KataGo yourself.



## <a name="GPU"></a> Configuring the GPU(s) KataGo uses

In most cases KataGo detects your configuration correctly, automatically searching for OpenCL devices and selecting the highest scoring device.
However, if you have multiple GPUs or want to force a specific device you will need to edit the 'analysis_config.cfg' file in the KataGo folder.

To see which devices are available and which one KataGo is using, look for the following lines in the terminal after starting KaTrain:
```
    Found 3 device(s) on platform 0 with type CPU or GPU or Accelerator
    Found OpenCL Device 0: Intel(R) Core(TM) i9-9880H CPU @ 2.30GHz (Intel) (score 102)
    Found OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) (score 6000102)
    Found OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) (score 11000102)
    Using OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) OpenCL 1.2
```

The above devices were found on a 2019 MacBook Pro with both an on-motherboard graphics chip, and a separate AMD Radeon Pro video card.
As you can see it scores about twice as high as the Intel UHD chip and KataGo has selected
 it as its sole device. You can configure KataGo to use *both* the AMD and the Intel devices to get the best performance out of the system.

* Open the 'analysis_config.cfg' file in the `katrain/KataGo` folder in your python packages, or local sources.
  If you can't find it, turn on `debug_level=1` in general settings and look for the command that is used to start KataGo.
* Search for `numNNServerThreadsPerModel` (~line 108), uncomment the line by deleting the # and set the value to 2. The line should read `numNNServerThreadsPerModel = 2`.
* Search for `openclDeviceToUseThread` (~line 202), uncomment by deleting the # and set the values to the device ID numbers identified in the terminal.
  From the example above, we would want to use devices 1 and 2, for the Intel and AMD GPUs, but not device 0 (the CPU). In our case, the lines should read:
```
openclDeviceToUseThread0 = 1
openclDeviceToUseThread1 = 2
```
* Run `katrain` and confirm that KataGo is now using both devices, by 
 checking the output from the terminal, which should indicate two devices being used. For example:
```
    Found 3 device(s) on platform 0 with type CPU or GPU or Accelerator
    Found OpenCL Device 0: Intel(R) Core(TM) i9-9880H CPU @ 2.30GHz (Intel) (score 102)
    Found OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) (score 6000102)
    Found OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) (score 11000102)
    Using OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) OpenCL 1.2
    Using OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) OpenCL 1.2
```


## <a name="KataGo"></a> Troubleshooting and advanced KataGo settings

See [here](ENGINE.md) for an overview of how to resolve various issues with KataGo.
