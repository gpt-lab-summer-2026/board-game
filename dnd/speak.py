from streaming_tts import TextToAudioStream, KokoroEngine

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

# testing
# speak("hello there! how are you? my day has started great.")