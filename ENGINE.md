# KataGo troubleshooting

* [General](#General)
    * [GPU vs CPU](#CPU)
    * [Multiple GPU settings](#GPU)
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


### <a name="GPU"></a> Configuring the GPU(s) KataGo uses

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


## <a name="Mac"></a><img src="https://upload.wikimedia.org/wikipedia/commons/8/8a/Apple_Logo.svg" alt="macOs" height="35"/> For macOS users

### New macs with M1 architecture

Make sure you `brew install katago` as the provided executable does not work on rosetta.

### Getting more information about errors

On macOS, the .app distributable will not show a console, so you will need install using `pip` to see the console window.

##  <a name="Windows"></a><img src="https://upload.wikimedia.org/wikipedia/commons/5/5f/Windows_logo_-_2012.svg" alt="Windows" height="35"/> For Windows users

### Getting more information about errors

Run DebugKaTrain.exe, which is released in the .zip file distributable in releases. This will show a console window
 which typically tells you more.


## <a name="Linux"></a><img src="https://upload.wikimedia.org/wikipedia/commons/a/ab/Linux_Logo_in_Linux_Libertine_Font.svg" alt="Linux" height="35"/> For Linux users

### libzip compatibility

The most common KataGo issue relates to different libzip versions in the provided executables.
Although the provided executables should work on the latest versions of Ubuntu, various other versions and distros differ in their libzip version. 

* First, try `sudo apt-get install libzip-dev` to 
* Next, try installing all packages mentioned [here](INSTALL.md#LinuxTrouble).
* A final alternative is to go [here](https://github.com/lightvector/KataGo) and compile KataGo yourself.

### Getting more information about errors

Check the terminal output around startup time.