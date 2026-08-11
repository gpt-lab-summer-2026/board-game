from audio import *
from llama_cpp import Llama

llm = Llama(
    model_path="../models/gemma-3-4b-it-q4_k_m.gguf",
)

def llama_chat(prompt, history):
    response = llm.create_chat_completion(
        messages= [
            {"role":"system", "content": "You are an gaming assistant that narrates a DnD game. User tells you what they are doing. Your job is only to narrate that scenery and what happens. Answerin maximum of two sentences"},
            *history
        ]
    )
    history.append({"role": "assistant", "content": response["choices"][0]["message"]["content"]})
    print(response["choices"][0]["message"]["content"])
    return(response["choices"][0]["message"]["content"])

def main():
    #
    gameOn = True
    history = []
    while ( gameOn):
        #print("write message:")
        #user_input = input()
        user_input = listen_user()

        history.append({"role": "user", "content": user_input})
        print("history: ", history)
        output_text = llama_chat(prompt=user_input, history=history)
        speak(output_text)

if __name__=="__main__":
    main()