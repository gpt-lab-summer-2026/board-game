# Board game

## Features

Version 1: completely digital 'Tampereen tuikahdus' -game that can be played via players' audio input. Software has build in LLM that handles moves and user audio input is given to LLM.

Version 2: DnD game, game board is projected to a table, which has been generated with a model. Player's play as normally DnD would be played but LLM narrates the stroy?? and generates the sceneray for players. Option for playing completely via audio input, for example for disabled people.

## Hardware

## Software

kokoro models: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0

gemma 3 4b it q4: https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/tree/005e437a164cd0ca77d29d0646c43bc5d29b6134

## Supported Languages

## Running program

run with commands:
`npm run llm`
`npm run dev`
`python -m voice.play_game`

## Possible improvements / additions
