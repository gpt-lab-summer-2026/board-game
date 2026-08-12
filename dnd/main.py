import os
import keyboard
from listen import *
from llama_cpp import Llama

MAX_HISTORY = 20

llm = Llama(
    model_path="../models/gemma-3-4b-it-q4_k_m.gguf",
)

def llama_chat(prompt, history):
    trimmed_history = history[-MAX_HISTORY:]
    response = llm.create_chat_completion(
        messages= [
            {"role":"system", "content": "You are an gaming assistant that narrates a DnD game. User tells you what they are doing. Your job is only to narrate that scenery and what happens. Answerin maximum of two sentences"},
            *trimmed_history
        ]
    )
    history.append({"role": "assistant", "content": response["choices"][0]["message"]["content"]})
    print(response["choices"][0]["message"]["content"])
    return(response["choices"][0]["message"]["content"])

def speak(text):
    # Initialize the engine
    engine = KokoroEngine(voice="bf_lily")
    
    # Create stream and play
    stream = TextToAudioStream(engine)
    stream.feed(text).play()
    
    # Process text with pauses
    # for item in process_text_with_pauses(text, normalize=True):
    #     if isinstance(item, float):
    #         time.sleep(item)  # Pause
    #     else:
    #         stream.feed(item).play()  # Speak

def stop_program():
    print("'q' pressed, stopping.")
    os._exit(0)

def main():
    keyboard.add_hotkey('q', stop_program)

    history = []
    while True:
        #print("write message:")
        #user_input = input()
        user_input = listen_user()

        history.append({"role": "user", "content": user_input})
        print("history: ", history)
        output_text = llama_chat(prompt=user_input, history=history)
        speak(output_text)

if __name__=="__main__":
    main()