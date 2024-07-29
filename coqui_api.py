from flask import Flask, request, send_file
import torch
from TTS.api import TTS
from loguru import logger

app = Flask(__name__)

#Getting device
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Device set to: {device}")

#Initializing the TTS model
tts = TTS("tts_models/en/ljspeech/tacotron2-DDC_ph").to(device)
logger.info("TTS model loaded and configured.")

@app.route('/tts', methods=['POST'])
def generate_tts():
    text = request.json.get('text')
    if not text:
        logger.error("No text provided in the request.")
        return "No text provided", 400

    try:
        #Defining the path for the output file
        output_file = "output.wav"

        #Generating speech and saving it to a file directly
        tts.tts_to_file(text=text, file_path=output_file)
        logger.info(f"Generated audio saved to {output_file}")

        #Sending the file
        return send_file(output_file, as_attachment=True, download_name='output.wav')

    except Exception as e:
        logger.error(f"Error during TTS generation: {str(e)}")
        return "Internal Server Error", 500

    finally:
        #Cleaning up to free memory
        torch.cuda.empty_cache()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
