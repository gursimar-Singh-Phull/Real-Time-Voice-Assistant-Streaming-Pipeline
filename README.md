# Nova AI

> A real-time voice assistant built for natural, hands-free interaction with AI.

Nova AI is a voice-based personal assistant that can understand spoken commands, process them using an AI model, and respond through natural speech.

The project is currently under active development. The core voice-assistant functionality is working, while additional capabilities and integrations are being developed.

## Current Status

**Status: Active Development**

### Currently Working

* Voice input and speech recognition
* AI-powered conversational responses
* Voice output
* Real-time interaction
* Ability to open applications through voice commands
* Basic assistant command handling
* Interrupting the assistant during responses
* Modular architecture for adding new tools and capabilities

### Under Development

* YouTube voice search

  * Search for a specific video using a voice command
  * Example: *"Nova, find the latest Python tutorial on YouTube."*
* More application controls
* Web search capabilities
* Additional tool integrations
* Improved conversational memory
* More reliable command detection
* Performance and latency improvements

## Example

You can interact with Nova using natural voice commands such as:

> "Open Chrome."

> "Open Spotify."

> "What is the weather today?"

> "Search for something on the web."

More commands and integrations are being added as development continues.

## Architecture

Nova AI uses a real-time voice pipeline connecting speech recognition, AI processing, and speech synthesis.

```text
User Voice
    ↓
Speech-to-Text
    ↓
AI / Command Processing
    ↓
Tool Execution
    ↓
Text-to-Speech
    ↓
Voice Response
```

## Tech Stack

* Python
* Pipecat
* Gemini
* Deepgram
* Cartesia
* Real-time voice communication
* API-based tool integrations

## Roadmap

* [x] Basic voice interaction
* [x] AI responses
* [x] Voice output
* [x] Application launching
* [x] Real-time interruption handling
* [ ] YouTube video search
* [ ] Advanced web search
* [ ] Expanded application controls
* [ ] Persistent memory
* [ ] Additional tools and integrations
* [ ] Performance optimization

## Development

Nova AI is an ongoing personal project. Features marked as **under development** may change as the architecture evolves.

The goal is to gradually turn Nova into a more capable real-time voice assistant with the ability to understand natural commands and interact with external applications and services.

## Project Status

**Active development — core functionality working, additional features in progress.**

## Project Status

**Status: Active Development**

This project is currently being developed incrementally. Core real-time voice interaction and desktop control features are working, while additional capabilities are actively being implemented.

### Currently Working
- Real-time voice conversation
- Speech-to-text processing
- LLM-powered responses
- Text-to-speech responses
- Windows application control
- System controls such as locking and sleep
- Voice-triggered browser actions

### In Progress
- More advanced Google and YouTube voice search
- File and folder management
- System volume controls
- Persistent memory
- Vision and screen understanding




