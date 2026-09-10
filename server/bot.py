#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#


import os

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.evals.transport import EvalTransportParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from system_tools import system_tools

load_dotenv(override=True)

# We use lambdas to defer transport parameter creation until the transport
# type is selected at runtime.
transport_params = {
    "eval": lambda: EvalTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info(f"Starting bot")

    stt = GroqSTTService(api_key=os.environ["GROQ_API_KEY"])

    llm = GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile",
            temperature=0,
        ),
    )

    # Cartesia is a separate provider from Groq — it needs its own API key
    # (and a voice_id, otherwise it falls back to a default voice).
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(voice=os.environ["CARTESIA_VOICE_ID"]),
    )

    # The system prompt lives in the context now (GroqLLMService.Settings has
    # no `system_instruction` field — that was raising a TypeError at startup).
    # `system_tools` (from system_tools.py) is passed in as `tools` so the LLM
    # actually knows the open_notepad/open_app functions exist and can call them.
    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant in a voice conversation. Your "
    "responses will be spoken aloud, so avoid emojis, bullet points, "
    "or other formatting that can't be spoken. Respond to what the "
    "user said in a creative, helpful, and brief way. When calling a "
    "function, call it directly - do not write out the function call "
    "as text, and do not narrate that you are about to call it. Just "
    "call it, then briefly confirm the result in your next spoken "
    "response.\n\n"
    "Tool selection rules, in priority order:\n"
    "1. If the user asks to search, look up, or google something "
    "(e.g. 'search Google for Python tutorials', 'look up SQL joins', "
    "'search the web for AI news'), call google_search. Never call "
    "open_app for these, even if the word Chrome or Google is mentioned.\n"
    "2. If the user names a specific website or domain to open "
    "(e.g. 'open github.com', 'open chatgpt.com'), call open_website.\n"
    "3. If the user asks to open a locally installed application by "
    "name with no search topic and no domain (e.g. 'open Chrome', "
    "'open Spotify'), call open_app."
                ),
            }
        ],
        tools=system_tools,
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            stt,
            user_aggregator,  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            assistant_aggregator,  # Assistant spoken responses
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected")
        # Kick off the conversation.
        context.add_message(
            {"role": "developer", "content": "Please introduce yourself to the user."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()