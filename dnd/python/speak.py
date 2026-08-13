from streaming_tts import TextToAudioStream, KokoroEngine

engine = KokoroEngine(voice="bf_lily")

def speak(text):
    # Create stream and play
    stream = TextToAudioStream(engine)
    stream.feed(text).play()
    
    # Process text with pauses
    # for item in process_text_with_pauses(text, normalize=True):
    #     if isinstance(item, float):
    #         time.sleep(item)  # Pause
    #     else:
    #         stream.feed(item).play()  # Speak
