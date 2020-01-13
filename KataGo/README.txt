KataGo v1.3
https://github.com/lightvector/KataGo

-----------------------------------------------------
USAGE:
-----------------------------------------------------

FIRST: run this to make sure KataGo is working, with a neural net file. 
katago.exe benchmark -model <NEURALNET>.txt.gz -config gtp_example.cfg

(download neural nets here if you don't have one: https://d3dndmfyhecmj0.cloudfront.net/g170/neuralnets/index.html)
On OpenCL, it should also cause KataGo to tune for your GPU. Then, the benchmark will report stats about speed and threads. You can configure gtp_example.cfg to use that many numSearchThreads to get good performance.

Next: This command will run the KataGo engine proper. Feed this command to any program GUI program to launch KataGo's engine:
katago.exe gtp -model <NEURALNET>.txt.gz -config gtp_example.cfg

KataGo should be able to work with any GUI program that supports GTP, as well as any analysis program that supports Leela Zero's `lz-analyze` command, such as Lizzie (https://github.com/featurecat/lizzie) or Sabaki (https://sabaki.yichuanshen.de/).

NOTE:
If you encounter errors due to a missing "msvcp140.dll" or "msvcp140_1.dll" or "msvcp140_2.dll" or "vcruntime140.dll" or similar, you need to download and install the Microsoft Visual C++ Redistributable, here:
https://www.microsoft.com/en-us/download/details.aspx?id=48145
If this is for a 64-bit Windows version of KataGo, these dll files have already been included for you, otherwise you will need to install them yourself. On a 64-bit Windows version, there is a rare chance that you may need to delete them if you already have it installed yourself separately and the pre-included files are actually causing problems running KataGo.

-----------------------------------------------------
OPENCL VS CUDA:
-----------------------------------------------------
Depending on hardware and settings, in practice the OpenCL version seems to range from anywhere to several times slower to a little faster than the CUDA version. More optimization work may happen in the future though - the OpenCL version has definitely not reached the limit of how well it can be optimized. It also has not been tested for self-play training with extremely large batch sizes to run hundreds of games in parallel, all of KataGo's main training runs so far have been performed with the CUDA implementation.

Extensive testing across different OSs and versions and compilers has not been done, so if you encounter issues, feel free to open an issue.

-----------------------------------------------------
TUNING FOR PERFORMANCE:
You will very likely want to tune some of the parameters in `gtp_example.cfg` for your system for good performance, including the number of threads, fp16 usage (CUDA only), NN cache size, pondering settings, and so on. You can also adjust things like KataGo's resign threshold or utility function. Most of the relevant parameters should be be reasonably well documented directly inline in that config.

There are other a few notes about usage and performance at : https://github.com/lightvector/KataGo
