# Board games run by LLM

## Features

### Game 1: 
Completely digital 'Tampereen tuikahdus' -game that can be played handsfree via players' audio input. Software has build in LLM that handles moves and user audio input is given to LLM. Gmae build with react and backend with Python.

### Game 2: Dungeons and Dragons
Digital game board that can be projected onto a table, build with opensource PlanarAlly. Can be played hands-free with audio input. Connected LLM makes players' moves on the game board.

### Game 3: Cards Against Humanity
Card game in which LLM plays as a dealer which randomly chooses black card. Players choose white cards to fit the black card and the software detects the text in the cards and the LLM then chooses the funniest card.

## Hardware

## Software

Game 1 and 2: React frontend and python backend

Game 3: completetly done with pyhton

kokoro models: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0

gemma 3 4b it q4: https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/tree/005e437a164cd0ca77d29d0646c43bc5d29b6134


## Running program

Read RUN_NOTES.MD

install requirements wit ```pip install -r requirements.txt```


