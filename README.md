# Youtube downloader
This lighted app can download videos and audio flux. Great for DJ !! 
It uses pytube library and PyQT5 for graphical interface.

# Requirements

Having **python 3.11** or **above** installed.

# Installation

- Create virtual env
``` bash
python3 -m venv .venv
```
- Load the env and install requirements
    - **Windows** 
        ``` bash
        .\.venv\Scripts\activate 
        pip install -r requirements.txt
        ``` 
- _NB_: If it doesn't work, you need first to run Powershell in Administrator mode and run this command `Set-ExecutionPolicy RemoteSigned`
    - **Linux** 
        ``` bash 
        . .venv/bin/activate
        pip install -r requirements.txt
        ``` 

# Utilisation

``` bash
python main.py
```

- Copy paste youtube url
- Click on load
- Select the desire flux
- Choose download directory


# Miscellaneous

We can use pyinstaller to only have a build app.

``` bash
pyinstaller --onefile --windowed main.py --name ytdl
``` 
The exectuble file can be seen in dist folder once generated.

- **Windows** : Already executable file
- **Linux** : Open terminal where the file is located -> `chmod +x ytdl` and then run the file : `./ytdl`  
