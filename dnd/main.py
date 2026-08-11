from listen import *
from speak import *
from llama_cpp import Llama

def llama_chat():
    llm = Llama(
        model_path="../models/gemma-3-4b-it-q4_k_m.gguf",
        chat_format="llama-2",
        n_ctx=2048, # Uncomment to increase the context window
    )
    response = llm.create_chat_completion(
        messages= [
            {"role":"system", "content": "You are an gaming assistant that narrates the game."},
            {"role":"user","content":"I'm attacking a dwarf with axe, describe it."}
        ]
    )
    print(response["choices"][0]["message"]["content"])
    return(response["choices"][0]["message"]["content"])

def main():
    output_text = llama_chat()
    speak(output_text)

if __name__=="__main__":
    main()