from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import speech_recognition as sr
import os
import wave
import io

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Path to store the audio file
AUDIO_FILE_PATH = "recorded_audio.wav"

# Initialize the recognizer
recognizer = sr.Recognizer()
# Adjust recognition settings
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True
recognizer.dynamic_energy_adjustment_damping = 0.15
recognizer.dynamic_energy_ratio = 1.5
recognizer.pause_threshold = 0.8
recognizer.phrase_threshold = 0.3
recognizer.non_speaking_duration = 0.5

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_recording', methods=['POST'])
def start_recording():
    return jsonify(status="Recording started")

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    if 'audio_data' not in request.files:
        return jsonify(status="Error", error="No audio file received.")

    audio_file = request.files['audio_data']
    
    try:
        # Save the original file
        audio_file.save(AUDIO_FILE_PATH)
        
        # Use speech recognition with multiple attempts
        with sr.AudioFile(AUDIO_FILE_PATH) as source:
            # Adjust for ambient noise
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            
            # Record the entire audio file
            audio = recognizer.record(source)
            
            # Try recognition with different settings
            text = None
            exceptions = []
            
            # Attempt 1: Default settings
            try:
                text = recognizer.recognize_google(audio, language='en-US')
            except Exception as e:
                exceptions.append(str(e))
            
            # Attempt 2: Different pause threshold
            if text is None:
                try:
                    recognizer.pause_threshold = 1
                    text = recognizer.recognize_google(audio, language='en-US')
                except Exception as e:
                    exceptions.append(str(e))
            
            # Attempt 3: Different energy threshold
            if text is None:
                try:
                    recognizer.energy_threshold = 400
                    text = recognizer.recognize_google(audio, language='en-US')
                except Exception as e:
                    exceptions.append(str(e))
            
            if text is None:
                raise sr.UnknownValueError(f"Speech recognition failed after multiple attempts. Errors: {'; '.join(exceptions)}")
            
            return jsonify(status="Recording stopped", text=text)
            
    except sr.UnknownValueError as e:
        return jsonify(status="Error", error=f"Could not understand the audio. Please speak clearly and try again. Details: {str(e)}")
    except sr.RequestError as e:
        return jsonify(status="Error", error=f"Could not request results from Google Speech Recognition service; {e}")
    except Exception as e:
        return jsonify(status="Error", error=f"Error processing audio: {str(e)}")
    finally:
        # Clean up the audio file
        if os.path.exists(AUDIO_FILE_PATH):
            try:
                os.remove(AUDIO_FILE_PATH)
            except:
                pass

@app.route('/get_text', methods=['GET'])
def get_text():
    return jsonify(status="Error", error="This endpoint is no longer supported.")

if __name__ == '__main__':
    app.run(debug=True, port=5500)