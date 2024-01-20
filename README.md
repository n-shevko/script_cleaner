## How to Install

Install docker https://docs.docker.com/desktop/install/mac-install/

Then:
    git clone https://github.com/n-shevko/script_cleaner.git
    cd script_cleaner
    pip install -r packages

    for mac os:
    brew install python-tk 
    
    for ubuntu:
    sudo apt-get install python3-tk 
    
    python3 install.py

The last command will:
1. Download whisper ml model ggml-base.en.bin in sources folder
2. Ask your OpenAI API key

After installation, you can start using app by running:

     python3 main.py


## Intermediate and result files

For example if you pick videofile:
/path/to/videofile.mp4

then extracted audio will be in file:
/path/to/videofile.wav

extracted text with timecodes will be in file:
/path/to/videofile.txt

extracted text without timecodes will be in file:
/path/to/videofile_text_only.txt

processed text by ChatGPT will be in file:
/path/to/videofile_out_2024_01_20_16_01_08.txt


Check the 'Use existing files' checkbox if you only want to redo the ChatGPT step (with a different prompt) 
without repeating the audio and text extraction steps.

If you want redo all steps then uncheck 'Use existing files' checkbox.

All settings are stored in config.json file.

