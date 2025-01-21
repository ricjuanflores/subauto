# SubAuto
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Description

<p align="center">
  <a><img width="700" src="https://cdn.jsdelivr.net/gh/ricjuanflores/static@main/gifs/transcribe-workers-simple.gif" alt="Freeze code screenshot"></a>
</p>
Subauto CLI is a command-line application written in Python that automates the process of transcribing, translating, and embedding subtitles in videos. It leverages Google's Gemini AI for translation and OpenAI's Whisper for speech recognition.

## Features
- Automated video transcription using Whisper
- High-quality translations using Google Gemini AI
- SRT file generation in both source and target languages
- Automatic subtitle embedding in videos
- Concurrent processing support for multiple videos
- Real-time progress tracking with rich console interface

## Table of Contents

- [Subauto](#subauto)
  - [Description](#description)
  - [Features](#features)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Prerequisites
- Python 3.11+
- Install [ffmpeg](https://www.ffmpeg.org/)
- Get a [Gemini API key](https://ai.google.dev/gemini-api/docs/api-key?hl=es-419) 

## Installation

```zsh
pip install subauto
```


Check if installation is complete

```
subauto --version
```
If a version is displayed, then SubAuto is installed correctly.

<p align="left">
  <a><img width="700" src="https://cdn.jsdelivr.net/gh/ricjuanflores/static@main/gifs/_version.gif" alt="Freeze code screenshot"></a>
</p>


## Usage

### Set up Gemini API Key
First, you need to configure your Gemini API key:

```
subauto set-api-key 'YOUR-API-KEY'
```

### Basic Translation

Translate videos to Spanish (full command):
```
subauto --directory /path/to/videos --output-directory /path/to/output --output-lang "es"
```

Or use the short version:
```
subauto -d /path/to/videos -o /path/to/output -ol "es"
```

### Advanced Usage

#### Concurrent Processing
Process multiple videos simultaneously by configuring the number of workers:
```
subauto -d /path/to/videos -o /path/to/output -ol "es" -w 4
```

#### Optimize Transcription
Speed up the transcription process by specifying the source language:
```
subauto -d /path/to/videos -o /path/to/output -ol "es" -il "en" -w 4
```
> Note: If you don't specify the input language, SubAuto will automatically detect it.

<p align="left">
  <a><img width="700" src="https://cdn.jsdelivr.net/gh/ricjuanflores/static@main/gifs/transcribe-workers-i.gif" alt="Freeze code screenshot"></a>
</p>

## Do you enjoy SubAuto or does it save your time?

Then definitely consider [**supporting me on GitHub
Sponsors**](https://github.com/sponsors/ricjuanflores) or buy me a coffee:

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/ricjuanflores)

Your support will allow me to allocate time to properly maintain my projects
like this.

# Contributing
If you want to contribute to this project, please use the following steps:

1. Fork the project.
2. Create a new branch (git checkout -b feature/awesome-feature).
3. Commit your changes (git commit -m 'Add some feature').
4. Push to the branch (git push origin feature/awesome-feature).
5. Open a pull request.


# License
This project is licensed under the MIT License.