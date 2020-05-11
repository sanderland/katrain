# Installation from source for Windows users

* Download the repository by clicking the green *Clone or download* on this page and *Download zip*. Extract the contents.
* Make sure you have a python installation, I will assume Anaconda (Python 3.7), available [here](https://www.anaconda.com/products/individual#download-section).
* Open 'Anaconda prompt' from the start menu and navigate to where you extracted the zip file using the `cd <folder>` command.
* Execute the command `pip install kivy_deps.glew kivy_deps.sdl2 kivy_deps.gstreamer kivy`
* Start the app by running `python katrain.py` in the directory where you downloaded the scripts. 
  * Note that the program can be slow to initialize the first time, due to KataGo's gpu tuning.

# Installation for Linux users

* This assumed you have a working Python 3.6/3.7 installation as a default. If your default is python 2, use pip3/python3. 
  Kivy currently does not have a release for Python 3.8.
* Open a terminal.
    * Run the command `git clone https://github.com/sanderland/katrain.git` to download the repository.
    * Run the command `pip install kivy`.
* A binary for KataGo is included, but if you have compiled your own, point the 'engine/katago' setting to the relevant KataGo v1.4+ binary.
* Start the app by changing directory using `cd katrain` and running `python katrain.py`.
  * Note that the program can be slow to initialize the first time, due to KataGo's GPU tuning.

# Installation for MacOS users

## Installation pre-requisites

* Download and install [Python 3.7.5](https://www.python.org/downloads/release/python-375/)
* Install [Homebrew](https://brew.sh) by running the following command in terminal:
  * ```
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"
    ```
* Run the command `pip3 install kivy` in the terminal.
* Install Katago using [Homebrew](https://brew.sh/)
   * Note that the version required for KaTrain is currently too new so we need to update the Homebrew script.
   * Run the command `brew edit katago` and replace lines 4-5 with
   * ```
     url "https://github.com/lightvector/KataGo/archive/v1.4.1.tar.gz"
     sha256 "b408086c7c973ddc6144e16156907556ae5f42921b9f29dc13e6909a9e9a4787"
     ```
    * You can also follow instructions [here](https://github.com/lightvector/KataGo) to compile KataGo yourself.

## Installation and running KaTrain

* Now that the dependencies are installed its time to Git clone or download the KaTrain repository
  * Run the command `git clone https://github.com/sanderland/katrain.git` this will clone KaTrain to your home folder.
* To run Katrain you need to first access the KaTrain folder.
  * If you used the 'git clone' command to download the repository then its located in your home folder.
   You can access it by typing `cd katrain` in the terminal. 
  * If you've moved the folder to another location the easiest way to navigate to it in terminal is to type `cd` and drag
   the KaTrain folder from the finder window into terminal. This will copy its full path to the command line.
* Now that we're in the KaTrain folder run the following command. `python3 katrain.py`
* The first time you run KaTrain you will see an error about initializing KataGo.
  * Open the settings dialog by clicking on the gear icon at the bottom right of the window and change the path of the 'katago'
   setting to `/usr/local/bin/katago` (or the path where you compiled KataGo) then click 'Apply and Save'.

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
* Run `python3 katrain.py` and confirm that KataGo is now using both devices, by 
 checking the output from the terminal, which should indicate two devices being used. For example:
```
  Found 3 device(s) on platform 0 with type CPU or GPU or Accelerator
  Found OpenCL Device 0: Intel(R) Core(TM) i9-9880H CPU @ 2.30GHz (Intel) (score 102)
  Found OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) (score 6000102)
  Found OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) (score 11000102)
  Using OpenCL Device 1: Intel(R) UHD Graphics 630 (Intel Inc.) OpenCL 1.2
  Using OpenCL Device 2: AMD Radeon Pro 5500M Compute Engine (AMD) OpenCL 1.2
```

