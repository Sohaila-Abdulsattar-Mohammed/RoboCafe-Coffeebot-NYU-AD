#
# Copyright (c) 2024, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import sys
sys.path.append('/home/mmvc/Downloads/pipecat/src/pipecat')

import asyncio
import aiohttp
import os
import sys
import wave
import json
import subprocess
import time
from multiprocessing import Process
from typing import List

from openai._types import NotGiven, NOT_GIVEN
from openai.types.chat import ChatCompletionToolParam
from pipecat.frames.frames import AudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response import LLMUserContextAggregator, LLMAssistantContextAggregator
from pipecat.processors.logger import FrameLogger
from pipecat.processors.frame_processor import FrameDirection
from coqui_tts import TextToSpeechService
# from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.services.openai import OpenAILLMContext, OpenAILLMContextFrame, OpenAILLMService
from pipecat.services.ai_services import AIService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.vad.silero import SileroVADAnalyzer
from PIL import Image
from pipecat.frames.frames import (
    AudioRawFrame,
    ImageRawFrame,
    SpriteFrame,
    Frame,
    LLMMessagesFrame,
    TTSStoppedFrame
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from runner import configure
from loguru import logger
from dotenv import load_dotenv

load_dotenv(override=True)
logger.remove(0)
logger.add(sys.stderr, level="DEBUG")



#below section is for animation#

sprites = []
script_dir = os.path.dirname(__file__)

for i in range(1, 20):
    # Build the full path to the image file
    full_path = os.path.join(script_dir, f"assets/{i}.png")
    # Get the filename without the extension to use as the dictionary key
    # Open the image and convert it to bytes
    with Image.open(full_path) as img:
        sprites.append(ImageRawFrame(image=img.tobytes(), size=img.size, format=img.format))

flipped = sprites[::-1]
sprites.extend(flipped)

# When the bot isn't talking, show the static first image
quiet_frame = sprites[0]
talking_frame = SpriteFrame(images=sprites)

class TalkingAnimation(FrameProcessor):
    """
    This class starts a talking animation when it receives an first AudioFrame,
    and then returns to a "quiet" sprite when it sees a TTSStoppedFrame.
    """

    def __init__(self):
        super().__init__()
        self._is_talking = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, AudioRawFrame):
            if not self._is_talking:
                await self.push_frame(talking_frame)
                self._is_talking = True
        elif isinstance(frame, TTSStoppedFrame):
            await self.push_frame(quiet_frame)
            self._is_talking = False

        await self.push_frame(frame)



#below section is for sound effects#

sounds = {}
sound_files = [
    "clack-short.wav",
    "clack.wav",
    "clack-short-quiet.wav",
    "ding.wav",
    "ding2.wav",
]
for file in sound_files:
    # Build the full path to the sound file
    full_path = os.path.join(script_dir, "assets", file)
    # Get the filename without the extension to use as the dictionary key
    filename = os.path.splitext(os.path.basename(full_path))[0]
    # Open the sound and convert it to bytes
    with wave.open(full_path) as audio_file:
        sounds[file] = AudioRawFrame(audio_file.readframes(-1),
                                     audio_file.getframerate(), audio_file.getnchannels())
        

# Dictionary of function definitions that are given as JSON Schema Objects (similar to OpenAI GPT function calls) that the LLM will be allowed to use
json_functions = {
    # This function takes the first piece of information for the coffee order, the coffee pod choice. Since the customer may provide other details along with the coffee pod choice, the function also accepts other input such as drink type, milk type, etc.
    "verify_coffee_pod_choice": {
        "type": "function",
        "function": {
            "name": "verify_coffee_pod_choice",
            "description": "Use this function to verify the user has provided their coffee pod choice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "coffee_pod_choice": {
                        "type": "string",
                        "enum":["light","medium","dark"],
                        "description": "The types of coffe pods available are light, medium, or dark roast pods. "
                    },
                    "drink_type": {
                        "type": "string",
                        "enum":["regular coffee","cappuccino","latte"],
                        "description": "The type of coffee drink the user can choose is regular coffee, cappuccino, or latte."
                    },
                    "milk_type": {
                        "type": "string",
                        "enum": ["fresh milk", "soy milk", "almond milk", "skimmed milk"],
                        "description": "The type of milk the user can choose is fresh milk, soy milk, almond milk, or skimmed milk."
                    },
                    "coffee_temperature": {
                        "type": "string",
                        "enum":["hot","cold"],
                        "description": "The user's preferred coffee temperature can be either hot or cold.",
                    },
                    "cup_size": {
                        "type": "string",
                        "description": "The cup sizes the user can choose from are 2, 6, 8, 10, or 12 ounces."
                    }
                },
                "required" : ["coffee_pod_choice"],
            },
        },
    },
    
    # This function will be called to record the coffee type the customer ordered. Since the customer may provide other details along with the coffee type, the function also accepts other input such as milk type, coffee, temperature, etc.
    "specify_coffee_type" : {
        "type": "function",
        "function": {
            "name": "specify_coffee_type",
            "description": "Once the user has provided their preferred coffee type, call this function.",
        "parameters": {
            "type": "object",
            "properties": {
                "drink_type": {
                    "type": "string",
                    "enum":["regular coffee","cappuccino","latte"],
                    "description": "The types of coffee pods available are light, medium, or dark roast pods."
                },
                "cup_size": {
                    "type": "string",
                    "description": "The cup sizes the user can choose from are 2, 6, 8, 10, or 12 ounces."
                },
                "milk_type": {
                    "type": "string",
                    "enum": ["fresh milk", "soy milk", "almond milk", "skimmed milk"],
                    "description": "The type of milk the user can choose is fresh milk, soy milk, almond milk, or skimmed milk."
                },
                "coffee_temperature": {
                    "type": "string",
                    "enum":["hot","cold"],
                    "description": "The user's preferred coffee temperature can be either hot or cold.",
                },
                
                },
            },
            "required" : ["drink_type"],
        },
    },
    "specify_milk_type": {
        "type": "function",
        "function": {
            "name": "specify_milk_type",
            "description": "Once the user has provided their preferred milk type, call this function.",
            "parameters": {
                "type": "object",
                "properties": {
                    "milk_type": {
                        "type": "string",
                        "enum": ["fresh milk", "soy milk", "almond milk", "skimmed milk"],
                        "description": "The type of milk the user can choose is fresh milk, soy milk, almond milk, or skimmed milk."
                    },
                    "coffee_temperature": {
                        "type": "string",
                        "enum": ["hot", "cold"],
                        "description": "The user's preferred coffee temperature can be either hot or cold."
                    }
                },
                "required": ["milk_type"]
            }
        }
    },

    "specify_coffee_temperature": {
        "type": "function",
        "function": {
            "name": "specify_coffee_temperature",
            "description": "Once the user has provided their preferred coffee temperature, call this function.",
            "parameters": {
                "type": "object",
                "properties": {
                    "coffee_temperature": {
                        "type": "string",
                        "enum": ["hot", "cold"],
                        "description": "The user's preferred coffee temperature can be either hot or cold."
                    }
                },
                "required": ["coffee_temperature"]
            }
        }
    },

    "specify_coffee_size" : {
        "type": "function",
        "function": {
            "name": "specify_coffee_size",
            "description": "Once the user has provided their preferred coffee size, call this function.",
            "parameters": {
                    "type": "object",
                    "properties": {
                        "cup_size": {
                            "type": "string",
                            "description": "The cup sizes the user can choose from are 2, 6, 8, 10, or 12 ounces."
                        }
                    },
                }
        },
    },
    "confirm_order": {
        "type": "function",
        "function": {
            "name": "confirm_order",
            "description": "Once the user has confirmed their order, call this function.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation": {
                        "type": "string",
                        "enum": ["yes", "no"],
                        "description": "Confirmation of order is yes or no."
                    }
                },
                "required": ["confirmation"]
            }
        }
    }
}


class IntakeProcessor:
    def __init__(
        self,
        context: OpenAILLMContext,
        llm: AIService,
        tools: List[ChatCompletionToolParam] | NotGiven = NOT_GIVEN,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._context: OpenAILLMContext = context
        self._llm = llm
        self.current_order = {}
        print(f"Initializing context from IntakeProcessor")
        
        self._context.set_tools([json_functions["verify_coffee_pod_choice"]])

        instructions = (
            "You are a virtual barista at Robo-Cafe. "
            "Your task is to take coffee orders by presenting specific choices and following the system's instructions EXACTLY. Avoid being redundant and keep your responses creative and diverse. "
            "You are ONLY allowed to call the functions that you are instructed to call. DO NOT attempt to call other functions or to call two functions at once. Also, DO NOT assume input values for the functions you will call; this is STRICTLY FORBIDDEN. The arguments for the functions you will call should be strictly based on the user's responses. "
            "Begin by welcoming the user to the shop. Then, if you know the user's preferred coffee pod (light, medium, or dark roast pod), you MUST immediately call the verify_coffee_pod_choice function. Otherwise, you need to ask the user first for their preferred coffee pod. DO NOT ASSUME INPUT VALUES FOR THE FUNCTION OR THE USER'S CHOICES. "
            "Your output will be converted to audio so DO NOT include special characters in your answers. "
        )
        self._context.add_message({"role": "system", "content": instructions})
        
        # create an allowlist of functions that the LLM can call
        self._functions = [
            "verify_coffee_pod_choice",
            "specify_coffee_type",
            "specify_milk_type",
            "specify_coffee_size",
            "specify_coffee_temperature",
            "confirm_order",
        ]

        # dictionary of instructions associated with every function the llm can call
        self._function_messages = {
           
            "specify_coffee_type": "Next, complement the user for their choice, then ask the user if they want a regular coffee, cappuccino, or latte and WAIT for their response. Once the user specifies what coffee type they want, you MUST call the specify_coffee_type function. DO NOT ASSUME INPUT VALUES FOR THE FUNCTION. ",

            "specify_milk_type": "Next, ask the user for their preferred milk type. Once they have specified their preferred milk type, call the specify_milk_type function. DO NOT ASSUME INPUT VALUES FOR THE FUNCTION. ",

            "specify_coffee_temperature": "Next, ask the user if they want their coffee hot or cold. Once they have specified their preferred coffee temperature (hot or cold), call the specify_coffee_temperature function. DO NOT ASSUME INPUT VALUES FOR THE FUNCTION. ",

            "specify_coffee_size": "Next, ask the user for their preferred coffee size. Once they have specified their preferred coffee size (2, 6, 8, 10, or 12 ounces), call the specify_coffee_size function. DO NOT ASSUME INPUT VALUES FOR THE FUNCTION. ",

            "confirm_order": "Now, you MUST repeat the FULL order to the user and ask the user to confirm the order. Once you get the user's confirmation, call the 'confirm_order' function. "
        }


    def determine_next_function(self):
        if not self.current_order.get("drink_type"):
            return "specify_coffee_type"
        if self.current_order["drink_type"] == "regular coffee":
            if not self.current_order.get("cup_size"):
                return "specify_coffee_size"
        else:
            if not self.current_order.get("milk_type"):
                return "specify_milk_type"
            if not self.current_order.get("coffee_temperature"):
                return "specify_coffee_temperature"
        return "confirm_order"
    

    
    def update_context(self, function_name):
        print(f"the determined function is {function_name}")
        if function_name in self._function_messages:
            message_content = self._function_messages[function_name]
            self._context.set_tools([json_functions[function_name]])
            self._context.add_message({"role": "system", "content": message_content})
            print(f"Context after update: {self._context}")

            


    async def verify_coffee_pod_choice(self, llm, args):
            
            print(f"the args in VERIFY COFFEE POD CHOICE are {args}")

            self.current_order.update({
                "coffee_pod_choice": args.get("coffee_pod_choice"),
                "drink_type": args.get("drink_type"),
                "milk_type": args.get("milk_type"),
                "coffee_temperature": args.get("coffee_temperature"),
                "cup_size": args.get("cup_size")
            })

            next_function = self.determine_next_function()

            if next_function:
                self.update_context(next_function)
                await self._llm.process_frame(OpenAILLMContextFrame(self._context), FrameDirection.DOWNSTREAM)


        
    async def process_coffee_type(self, llm, args):
        print(f"the args in PROCESS COFFEE TYPE are {args}")
        
        self.current_order.update({
            "drink_type": args.get("drink_type"),
            "milk_type": args.get("milk_type"),
            "coffee_temperature": args.get("coffee_temperature"),
            "cup_size": args.get("cup_size")
        })

        next_function = self.determine_next_function()
        if next_function:
            self.update_context(next_function)
            await self._llm.process_frame(OpenAILLMContextFrame(self._context), FrameDirection.DOWNSTREAM)
        
            

    async def process_coffee_details(self, llm, args):
        print(f"the args in PROCESS COFFEE DETAILS are {args}")
        
        self.current_order.update({
            "milk_type": args.get("milk_type"),
            "coffee_temperature": args.get("coffee_temperature")
        })

        next_function = self.determine_next_function()
        if next_function:
            self.update_context(next_function)
            await self._llm.process_frame(OpenAILLMContextFrame(self._context), FrameDirection.DOWNSTREAM)




    async def process_coffee_order(self, llm, args):
        print(f"the args in PROCESS COFFEE ORDER are {args}")

        self.current_order.update({
            "cup_size": args.get("cup_size"),
            "coffee_temperature": args.get("coffee_temperature")
        })

        next_function = self.determine_next_function()
        if next_function:
            self.update_context(next_function)
            await self._llm.process_frame(OpenAILLMContextFrame(self._context), FrameDirection.DOWNSTREAM)


        

    async def process_confirm_order(self, llm, args):
        print(f"the args in PROCESS CONFIRM ORDER are {args}")
        
        self.current_order["confirmation"] = args.get("confirmation")
        await self.save_data(self.current_order)
        # move to finish call
        self._context.set_tools([])
        await llm.push_frame(sounds["ding2.wav"], FrameDirection.DOWNSTREAM)
        self._context.add_message({"role": "system", "content": "Now, thank the user and end the conversation."})
        await llm.process_frame(OpenAILLMContextFrame(self._context), FrameDirection.DOWNSTREAM)


    async def save_data(self, order_data):
        # This function saves the completed order to the JSON file
        try:
            with open('data.json', 'r') as file:
                existing_data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            existing_data = []

        existing_data.append(order_data)  # Append the new order

        with open('data.json', 'w') as file:
            json.dump(existing_data, file, indent=4)  # Save back to the file

        print("Order saved:", order_data)



async def main(room_url: str, token):
    async with aiohttp.ClientSession() as session:
        transport = DailyTransport(
            room_url,
            token,
            "Chatbot",
            DailyParams(
                audio_out_enabled=True,
                audio_out_sample_rate=24_000,
                camera_out_enabled=True,
                camera_out_width=576,
                camera_out_height=576,
                camera_out_bitrate=1000000,  # Increased bitrate for better quality
                camera_out_framerate=20,     # Standard frame rate for smooth motion
                camera_out_color_format="RGBA",  # Assuming transparency needs to be handled
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                transcription_enabled=True,
            )
        )

        

        #cailab 1: 10.224.35.95
        #cailab 2: 10.224.35.92

        # format:
        # http://10.224.35.92:5000/tts for tts
        # http://10.224.35.95:5001/v1 for llm

        tts = TextToSpeechService(api_url='http://10.224.35.92:5000/tts', aiohttp_session=session) #edit link as needed

        # tts = ElevenLabsTTSService(
        #     aiohttp_session=session,
        #     api_key=os.getenv("ELEVENLABS_API_KEY"),
        #     #
        #     # English
        #     #
        #     voice_id="pNInz6obpgDQGcFmaJgB",
        # )

        # llm = OpenAILLMService(
        #     api_key=os.getenv("OPENAI_API_KEY"),
        #     model="gpt-4o")

        llm = OpenAILLMService(
            name="LLM",
            api_key="functionary",
            model="meetkai/functionary-small-v2.5",
            base_url="http://10.224.35.95:5001/v1"
        )

        # llm = OpenAILLMService(
        #     name="LLM",
        #     api_key="token-abc123",
        #     model="fireworks-ai/llama-3-firefunction-v2",
        #     base_url="http://10.224.35.95:5001/v1"
        # )

        messages = []
        context = OpenAILLMContext(messages=messages)
        user_context = LLMUserContextAggregator(context)
        assistant_context = LLMAssistantContextAggregator(context)


        # register_function takes the name of the function as it will be referred to in the LLM service, and the method in the IntakeProcessor that implements the logic for that function
        intake = IntakeProcessor(context, llm)
        llm.register_function(
            "verify_coffee_pod_choice",
            intake.verify_coffee_pod_choice)
        llm.register_function(
            "specify_coffee_type",
            intake.process_coffee_type)
        # process_coffee_type(args)
        llm.register_function(
            "specify_milk_type",
            intake.process_coffee_details)
        llm.register_function(
            "specify_coffee_temperature",
            intake.process_coffee_order)
        llm.register_function(
            "specify_coffee_size",
            intake.process_coffee_order)
        llm.register_function(
            "confirm_order",
            intake.process_confirm_order)

        fl = FrameLogger("LLM Output")

        ta = TalkingAnimation()

        pipeline = Pipeline([
            transport.input(),   # Transport input
            user_context,        # User responses
            llm,                 # LLM
            fl,                  # Frame logger
            tts,                 # TTS
            ta,
            transport.output(),  # Transport output
            assistant_context,   # Assistant responses
        ])

        task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            transport.capture_participant_transcription(participant["id"])
            print(f"Context is: {context}")
            await task.queue_frames([OpenAILLMContextFrame(context)])
            print("Frames queued, check for further processing") 

        runner = PipelineRunner()

        await runner.run(task)


if __name__ == "__main__":
    (url, token) = configure()
    asyncio.run(main(url, token))
