import aiohttp
import asyncio
from pipecat.frames.frames import AudioRawFrame, ErrorFrame
from pipecat.services.ai_services import TTSService
from loguru import logger
from typing import AsyncGenerator
import torch
import io

class TextToSpeechService(TTSService):
    def __init__(self, device: str = "cuda" if torch.cuda.is_available() else "cpu", *, aiohttp_session: aiohttp.ClientSession, api_url: str):
        super().__init__()
        self.device = device
        self.api_url = api_url
        self.session = aiohttp_session

    async def run_tts(self, text: str) -> AsyncGenerator[AudioRawFrame, None]:
        logger.debug(f"Sending TTS request for text: [{text}]")
        try:
            # Sending POST request to the TTS API
            response = await self.session.post(self.api_url, json={'text': text})
            if response.status != 200:
                error_msg = f"API request failed with status {response.status}: {await response.text()}"
                logger.error(error_msg)
                yield ErrorFrame(error_msg)
                return

            # Reading the audio data from the response
            audio_data = await response.content.read()
            sample_rate = 24000  
            chunk_size = 1024   
            for i in range(0, len(audio_data), chunk_size):
                end = i + chunk_size
                yield AudioRawFrame(audio_data[i:end], sample_rate, 1)

        except Exception as e:
            error_msg = f"Error during TTS generation: {str(e)}"
            logger.error(error_msg)
            yield ErrorFrame(error_msg)
