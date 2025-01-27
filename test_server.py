from __future__ import annotations

import uvicorn
import asyncio
import threading
from fastapi import FastAPI, HTTPException



import asyncio
import logging
import aiohttp
from dotenv import load_dotenv
import json
import os
from time import perf_counter
from typing import Annotated
from livekit import rtc, api
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.multimodal import MultimodalAgent
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import deepgram, openai, silero


from livekit.protocol.sip import CreateSIPOutboundTrunkRequest,SIPOutboundTrunkInfo


"""

This test_Server.py using multi-threading concept in which both fastapi and livekit server are running in separate threads.
with their own event loop , which is not making the conflict with the main thread. but multi-threading should not be used in multi-threading.

"""


# load environment variables, this is optional, only used for local development

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

################################################################################
log_file = "outbound_caller.log"  # Define log file name
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Create a file handler
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)

# Create a console handler (optional, if you still want to see logs in the console)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

logger.info("Logging is now configured to write to a file.")
################## CONFIGURATION ################################################








outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
_default_instructions = (
    "You are a Helpful Customer Support Agent. "
    "You will provide the information about weather,"
)

address_single = "xyzjoma.pstn.singapore.twilio.com"

trunk_info = SIPOutboundTrunkInfo(
        name="MyTrunk",
        address="xyzjoma.pstn.twilio.com",
        numbers=["+15674093314"],
        auth_username="joma123",
        auth_password="H@malbro4567890",
    )

async def entrypoint(ctx: JobContext):

    global _default_instructions, outbound_trunk_id
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    user_identity = "phone_user"
    # the phone number to dial is provided in the job metadata
    phone_number = ctx.job.metadata
    logger.info(f"dialing {phone_number} to room {ctx.room.name}")

    # look up the user's phone number and appointment details
    instructions = (
        _default_instructions
        + "The customer's name is Jyotsan."
    )
    trunk_request = CreateSIPOutboundTrunkRequest(
        trunk = trunk_info
    )

    trunk = await ctx.api.sip.create_sip_outbound_trunk(trunk_request)
    print(f"Successfully created \n {trunk.sip_trunk_id} \n ---")
    
    outbound_trunk_id = trunk.sip_trunk_id
    # `create_sip_participant` starts dialing the user
    await ctx.api.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            room_name=ctx.room.name,
            sip_trunk_id=outbound_trunk_id,
            sip_call_to=phone_number,
            participant_identity=user_identity,
        )
    )

    # a participant is created as soon as we start dialing
    participant = await ctx.wait_for_participant(identity=user_identity)

    # start the agent, either a VoicePipelineAgent or MultimodalAgent
    # this can be started before the user picks up. The agent will only start
    # speaking once the user answers the call.
    # run_voice_pipeline_agent(ctx, participant, instructions)
    run_multimodal_agent(ctx, participant, instructions)

    # in addition, you can monitor the call status separately
    start_time = perf_counter()
    while perf_counter() - start_time < 30:
        call_status = participant.attributes.get("sip.callStatus")
        if call_status == "active":
            logger.info("user has picked up")
            return
        elif call_status == "automation":
            # if DTMF is used in the `sip_call_to` number, typically used to dial
            # an extension or enter a PIN.
            # during DTMF dialing, the participant will be in the "automation" state
            pass
        elif call_status == "hangup":
            # user hung up, we'll exit the job
            logger.info("user hung up, exiting job")
            break
        await asyncio.sleep(0.1)

    logger.info("session timed out, exiting job")
    ctx.shutdown()




class CallActions(llm.FunctionContext):
    """
    Detect user intent and perform actions
    """

    def __init__(
        self, *, api: api.LiveKitAPI, participant: rtc.RemoteParticipant, room: rtc.Room
    ):
        super().__init__()

        self.api = api
        self.participant = participant
        self.room = room

    async def hangup(self):
        try:
            await self.api.room.remove_participant(
                api.RoomParticipantIdentity(
                    room=self.room.name,
                    identity=self.participant.identity,
                )
            )
        except Exception as e:
            # it's possible that the user has already hung up, this error can be ignored
            logger.info(f"received error while ending call: {e}")

    @llm.ai_callable()
    async def end_call(self):
        """Called when the user wants to end the call"""
        logger.info(f"ending the call for {self.participant.identity}")
        await self.hangup()

    # @llm.ai_callable()
    # async def look_up_availability(
    #     self,
    #     date: Annotated[str, "The date of the appointment to check availability for"],
    # ):
    #     """Called when the user asks about alternative appointment availability"""
    #     logger.info(
    #         f"looking up availability for {self.participant.identity} on {date}"
    #     )
    #     asyncio.sleep(3)
    #     return json.dumps(
    #         {
    #             "available_times": ["1pm", "2pm", "3pm"],
    #         }
    #     )

    # @llm.ai_callable()
    # async def confirm_appointment(
    #     self,
    #     date: Annotated[str, "date of the appointment"],
    #     time: Annotated[str, "time of the appointment"],
    # ):
    #     """Called when the user confirms their appointment on a specific date. Use this tool only when they are certain about the date and time."""
    #     logger.info(
    #         f"confirming appointment for {self.participant.identity} on {date} at {time}"
    #     )
    #     return "reservation confirmed"

    @llm.ai_callable()
    async def detected_answering_machine(self):
        """Called when the call reaches voicemail. Use this tool AFTER you hear the voicemail greeting"""
        logger.info(f"detected answering machine for {self.participant.identity}")
        await self.hangup()
    
    @llm.ai_callable()
    async def get_weather(
        self,
        # by using the Annotated type, arg description and type are available to the LLM
        location: Annotated[
            str, llm.TypeInfo(description="The location to get the weather for")
        ],
    ):
        """Called when the user asks about the weather. This function will return the weather for the given location."""
        logger.info(f"getting weather for {location}")
        url = f"https://wttr.in/{location}?format=%C+%t"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    weather_data = await response.text()
                    # response from the function call is returned to the LLM
                    # as a tool response. The LLM's response will include this data
                    return f"The weather in {location} is {weather_data}."
                else:
                    raise f"Failed to get weather data, status code: {response.status}"


def run_voice_pipeline_agent(
    ctx: JobContext, participant: rtc.RemoteParticipant, instructions: str
):
    logger.info("starting voice pipeline agent")

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=instructions,
    )

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-2-phonecall"),
        llm=openai.LLM(),
        tts=openai.TTS(),
        chat_ctx=initial_ctx,
        fnc_ctx=CallActions(api=ctx.api, participant=participant, room=ctx.room),
    )

    agent.start(ctx.room, participant)


def run_multimodal_agent(
    ctx: JobContext, participant: rtc.RemoteParticipant, instructions: str
):
    logger.info("starting multimodal agent")

    model = openai.realtime.RealtimeModel(
        instructions=instructions,
        modalities=["audio", "text"],
        temperature=0.8,
        # turn_detection=openai.realtime.ServerVadOptions(
        #     threshold=0.6, prefix_padding_ms=200, silence_duration_ms=500
        # ),
        # voice="alloy"
    )
    agent = MultimodalAgent(
        model=model,
        fnc_ctx=CallActions(api=ctx.api, participant=participant, room=ctx.room),
    )
    agent.start(ctx.room, participant)
    

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


import threading

# Your worker function that requires asyncio.run()

    


app = FastAPI()
    
@app.post("/call")
async def dispatch_agent(phone_number: str):
    """
    Dispatch the outbound caller agent with the given phone number
    """
    try:
        # Initialize LiveKit API using environment variables
        lkapi = api.LiveKitAPI(
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        print(f"Dispatching agent with phone number: {phone_number}")
        # Generate a unique room name
        room_name = f"outbound-call-room"
        
        # Create dispatch request
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="outbound-caller",
                room=room_name,
                metadata=phone_number,
            )
        )
        
        await lkapi.aclose()
        
        return {
            "message": "Agent dispatched successfully",
            "room": room_name,
            "dispatch_id": dispatch.id
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Function to run FastAPI in a thread
def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000)


def worker():
    # signal.signal() is called , which only supports in main thread.
    import sys
    sys.argv.append("start")
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outbound-caller",
        )
    )

def start_fastapi_in_thread(): 
    worker_thread = threading.Thread(target=run_fastapi) 
    worker_thread.daemon = True  # This will allow the thread to exit when the main program exits
    worker_thread.start()
    
if __name__ == "__main__":
    start_fastapi_in_thread()
    # Run worker in the main thread
    worker()
