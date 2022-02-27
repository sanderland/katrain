# KaTrain Installation

* [Quick install guide for MacOS](#MacQuick)
    * [Troubleshooting and installation from sources](#MacSources)
* [Quick install guide for Windows](#WindowsQuick)
    * [Troubleshooting and installation from sources](#WindowsSources)
* [Quick install guide for Linux](#LinuxQuick)
    * [Troubleshooting and installation from sources](#LinuxSources)
* [Configuring Multiple GPUS](#GPU)
* [Troubleshooting KataGo](#KataGo)

## <img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Apple_Logo.svg" alt="macOs" height="35"/> Installation for macOS users

### <a name="MacQuick"></a>Quick install guide

The easiest way to install is probably [brew](https://brew.sh/). Simply run `brew install katrain` and it will download and install the latest pre-built .app, and also install katago if needed.

You can also find downloadable .app files for macOS [here](https://github.com/sanderland/katrain/releases). 
Simply download, unzip the file, mount the .dmg and drag the .app file to your application folder, everything is included.
The first time launching the application you may need to [control-click in finder to give permission for the 'unidentified' app to launch](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unidentified-developer-mh40616/mac). This is simply a result of Apple charging $99/year to developers to be 'identified'.

Users with the last generation M1 macs with different architecture should then `brew install katago` in addition to this. KaTrain will automatically detect this KataGo binary.

### <a name="MacCommand"></a>Command line install guide

[Open a terminal](https://support.apple.com/guide/terminal/open-or-quit-terminal-apd5265185d-f365-44cb-8b09-71a064a42125/mac) and enter the following commands:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
brew install python3
brew install katago
pip3 install katrain
```

If you are using a M1 Mac, at the point of writing, the latest stable release of Kivy (2.0) does not support the new architecture, so we have to use a development snapshot and build it from source:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
brew install python3
brew install katago

# install dependencies: https://kivy.org/doc/stable/installation/installation-osx.html#install-source-osx
brew install pkg-config sdl2 sdl2_image sdl2_ttf sdl2_mixer gstreamer ffmpeg

# install Kivy from source: https://kivy.org/doc/stable/gettingstarted/installation.html#kivy-source-install
pip3 install "kivy[base] @ https://github.com/kivy/kivy/archive/master.zip" --no-binary kivy

pip3 install katrain
```

Now you can start KaTrain by simply typing `katrain` in a terminal.

These commands install [Homebrew](https://brew.sh), which simplifies installing packages,
 followed by the programming language Python, the KataGo AI, and KaTrain itself.
 
To upgrade to a newer version, simply run `pip3 install -U katrain`

### <a name="MacSources"></a>Troubleshooting and Installation from sources

Installation from sources is essentially the same as for Linux, see [here](#LinuxSources),
 note that you will still need to install your own KataGo, using brew or otherwise. 

If you encounter SSL errors on downloading model files, you may need to follow [these](https://stackoverflow.com/questions/52805115/certificate-verify-failed-unable-to-get-local-issuer-certificate) instructions to fix your certificates.

## <img src="https://upload.wikimedia.org/wikipedia/commons/5/5f/Windows_logo_-_2012.svg" alt="Windows" height="35"/> Installation for Windows users

### <a name="WindowsQuick"></a>Quick install guide

You can find downloadable .exe files for windows [here](https://github.com/sanderland/katrain/releases). 
Simply download and run, everything is included.

### <a name="WindowsSources"></a>Installation from sources

* Download the repository by clicking the green *Clone or download* on this page and *Download zip*. Extract the contents.
* Make sure you have a python installation, I will assume Anaconda (Python 3.7/3.8), available [here](https://www.anaconda.com/products/individual#download-section).
* Open 'Anaconda prompt' from the start menu and navigate to where you extracted the zip file using the `cd <folder>` command.
* Execute the command `pip3 install .`
* Start the app by running `katrain` in the command prompt. 

## <img src="https://upload.wikimedia.org/wikipedia/commons/a/ab/Linux_Logo_in_Linux_Libertine_Font.svg" alt="Linux" height="35"/> Installation for Linux users

### <a name="LinuxQuick"></a>Quick install guide

If you have a working Python 3.6-3.8 available, you should be able to simply:

* Run `pip3 install -U katrain`
* Run the program by executing `katrain` in a terminal.

### <a name="LinuxSources"></a>Installation from sources 

This section describes how to install KaTrain from sources,
 in case you want to run it in a local directory or have more control over the process. 
It assumes you have a working Python 3.6+ installation.

* Open a terminal.
* Run the command `git clone https://github.com/sanderland/katrain.git` to download the repository and 
  change directory using `cd katrain`
* Run the command `pip3 install .` to install the package globally, or use `--user` to install locally.
* Run the program by typing `katrain` in the terminal.
    * If you prefer not to install, run without installing using `python3 -m katrain` after installing the 
    dependencies from `requirements.txt`.

A binary for KataGo is included, but if you have compiled your own, press F8 to open general settings and change the 
 KataGo executable path to the relevant KataGo v1.4+ binary.

### <a name="LinuxTrouble"></a>Troubleshooting and advanced installation from sources

You can try to manually install dependencies to resolve some issues relating to missing dependencies,
 e.g. the binary 'wheel' is not provided, KataGo is not starting, or sounds are not working.
You can also follow these instructions if you don't want to install KaTrain, and just run it locally.

First install the following packages, which are either required for building Kivy, 
 or may help resolve missing dependencies for Kivy or KataGo.
```bash
sudo apt-get install python3-pip build-essential git python3 python3-dev ffmpeg libsdl2-dev libsdl2-image-dev\
    libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev\
    libgstreamer1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good libpulse\
    pkg-config libgl-dev opencl-headers ocl-icd-opencl-dev libzip-dev
```
Then, try installing python package dependencies using:
```bash
pip3 install -r requirements.txt
pip3 install screeninfo # Skip on MacOS, not working
```
In case the sound is not working, or there is no available wheel for your OS or Python version, try building kivy locally using:
```bash
pip3 uninstall kivy
pip3 install kivy --no-binary kivy
```

You can now start KaTrain by running `python3 -m katrain`

In case KataGo does not start, an alternative is to go [here](https://github.com/lightvector/KataGo) and compile KataGo yourself.



## <a name="GPU"></a> Configuring the GPU(s) KataGo uses

In most cases KataGo detects your configuration correctly, automatically searching for OpenCL devices and select the highest scoring device. 
However, if you have multiple GPUs or want to force a specific device you will need to edit the 'analysis_config.cfg' file in the KataGo folder.

To see what devices are available and which one KataGo is using. Look for the following lines in the terminal after starting KaTrain:
```
    Found 3 device(s) on platform 0 with type CPU or GPU or Accelerator
    Found OpenCL Device 0: Intel(R) Core(TM) i9-9880H CPU @ 2.30GHz (Intel) (score 102)
    Found OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) (score 6000102)
    Found OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) (score 11000102)
    Using OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) OpenCL 1.2
```

The above devices were found on a 2019 MacBook Pro with both an on-motherboard graphics chip, and a separate AMD Radeon Pro video card.
As you can see it scores about twice as high as the Intel UHD chip and KataGo has selected
 it as it's sole device. You can configure KataGo to use *both* the AMD and the Intel devices to get the best performance out of the system.

* Open the 'analysis_config.cfg' file in the `katrain/KataGo` folder in your python packages, or local sources.
  If you can't find it, turn on `debug_level=1` in general settings and look for the command that is used to start KataGo.
* Search for `numNNServerThreadsPerModel` (~line 108), uncomment the line by deleting the # and set the value to 2. The line should read `numNNServerThreadsPerModel = 2`.
* Search for `openclDeviceToUseThread` (~line 164), uncomment by deleting the # and set the values to the device ID numbers identified in the terminal.
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