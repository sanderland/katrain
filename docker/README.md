Note: This docker file requires the host to have an NVIDIA GPU. It is not compatible with AMD GPUs as it uses tensorrt for inference.

1. To allow the container to access the host's X server, run the following command in the terminal:
    ```bash
    xhost +
    ```

2. Set the ```Path to KataGo executable``` as ```./katago``` in ```General & Engine Settings```.