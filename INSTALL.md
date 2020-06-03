
# Installation for MacOS users

## <a name="MacPrereq"></a>Installation pre-requisites
* Download and install [Python 3.7.5](https://www.python.org/downloads/release/python-375/)
* Install [Homebrew](https://brew.sh) by running the following command in terminal:
  * ```
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
    ```
* Install Katago using [Homebrew](https://brew.sh/) by executing `brew install katago`
* You can also follow instructions [here](https://github.com/lightvector/KataGo) to compile KataGo yourself.

## Installation and running KaTrain from PyPi
* Run `pip3 install katrain`
* Run the program by executing `katrain` in a terminal.
* If you see an error about initializing KataGo:
  * Open the settings dialog by clicking on the gear icon at the bottom right of the window and change the path of the 'katago'
   setting under 'engine' to `/usr/local/bin/katago`, or the path where you compiled KataGo.

## Installation from sources
* This is largely the same as for linux, see [here](#LinuxSources).

# Installation from sources for Windows users
* Download the repository by clicking the green *Clone or download* on this page and *Download zip*. Extract the contents.
* Make sure you have a python installation, I will assume Anaconda (Python 3.7), available [here](https://www.anaconda.com/products/individual#download-section).
* Open 'Anaconda prompt' from the start menu and navigate to where you extracted the zip file using the `cd <folder>` command.
* Execute the command `pip3 install .`
* Start the app by running `katrain` in the directory where you downloaded the scripts. 

# <a name="LinuxSources"></a>Installation from sources for Linux users

* This assumed you have a working Python 3.6/3.7 installation as a default. If your default is python 2, use pip3/python3. 
  Kivy currently does not have a release for Python 3.8.
* Open a terminal.
    * Run the command `git clone https://github.com/sanderland/katrain.git` to download the repository.
    * Changing directory using `cd katrain`
    * Run the command `pip3 install .` to install the package globally, or use `--user` to install locally, then run the program by typing `katrain` in the terminal.
    * If you prefer not to install, run without installing using `python3 -m katrain`
* A binary for KataGo is included, but if you have compiled your own, point the 'engine/katago' setting to the relevant KataGo v1.4+ binary.

## Troubleshooting 

Older linux machines may have trouble installing, you can try to manually install dependencies to resolve some issues.

The following packages may help resolve missing OS packages for Kivy or KataGo.
```
sudo apt-get install python3-pip build-essential git python3 python3-dev ffmpeg libsdl2-dev libsdl2-image-dev\
    libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev\
    libgstreamer1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good\
    pkg-config libgl-dev opencl-headers ocl-icd-opencl-dev python3-pygame
```
Then, try installing python package dependencies using:
```
pip3 install -U cython wheel setuptools
pip3 install kivy==2.0.0rc2 kivymd==1.104.1
```

In case KataGo does not start, an alternative is to go [here](https://github.com/lightvector/KataGo) and compile KataGo yourself.

# Configuring the GPU(s) KataGo uses

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

* Open the 'analysis_config.cfg' file in the KataGo folder.
* Search for `numNNServerThreadsPerModel` (~line 75), uncomment the line by deleting the # and set the value to 2. The line should read `numNNServerThreadsPerModel = 2`.
* Search for `openclDeviceToUseThread` (~line 117), uncomment by deleting the # and set the values to the device ID numbers identified in the terminal.
  From the example above, we would want to use devices 1 and 2, for the Intel and AMD GPU's, but not device 0 (the CPU). In our case, the lines should read:
```
openclDeviceToUseThread0 = 1
openclDeviceToUseThread1 = 2
```
* Run `python3 -m katrain` and confirm that KataGo is now using both devices, by 
 checking the output from the terminal, which should indicate two devices being used. For example:
```
  Found 3 device(s) on platform 0 with type CPU or GPU or Accelerator
  Found OpenCL Device 0: Intel(R) Core(TM) i9-9880H CPU @ 2.30GHz (Intel) (score 102)
  Found OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) (score 6000102)
  Found OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) (score 11000102)
  Using OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) OpenCL 1.2
  Using OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) OpenCL 1.2
```
