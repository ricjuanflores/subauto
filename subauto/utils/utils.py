import inspect
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import ffmpeg
import srt

from ..exceptions.conversion import SRTConversionError

languages = {
    "en": "English",
    "es": "Spanish Latin America",
    "pt": "Portuguese",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ar": "Arabic",
    "ru": "Russian",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "it": "Italian",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "nl": "Dutch",
    "tl": "Tagalog",
    "he": "Hebrew",
    "pl": "Polish",
    "sv": "Swedish",
    "id": "Indonesian",
}


def embed_subtitles(video_path: str, srt_paths: Dict, output_path: str) -> None:
    """
    Embeds SRT subtitles as tracks in a video file.

    Args:
        video_path (str): Path to the input video file.
        srt_paths (Dict): Dictionary containing paths to input and output subtitle files.
            Keys should represent language codes (e.g., 'en', 'es'), and values should be
            the corresponding SRT file paths.
        output_path (str): Path to the output video file with embedded subtitles.
    """

    video_input = ffmpeg.input(video_path)
    lng_input, lng_output = srt_paths.keys()
    srt_input, srt_output = srt_paths.values()
    subt_language_input = ffmpeg.input(srt_input)
    subt_language_output = ffmpeg.input(srt_output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
   
    try:
        stream = ffmpeg.output(
            video_input,
            subt_language_input,
            subt_language_output,
            output_path,
            **{
                "c": "copy",
                "c:s": "mov_text",
                "metadata:s:s:1": f"language={lng_output}",
                "metadata:s:s:1": f"title={get_language(lng_output)}",  # noqa: F601
                "metadata:s:s:0": f"language={lng_input}",
                "metadata:s:s:0": f"title={get_language(lng_input)}",  # noqa: F601
                "disposition:s:1": "default",
            }
        )
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
    except ffmpeg.Error as e:
        raise e
    


def get_language(abbr: str) -> Optional[str]:
    lang = languages.get(abbr, None)
    return lang


def load_json_file(path_file: str) -> Optional[Dict]:
    """
    Loads and parses a JSON file.

    Args:
        path_file: The path to the JSON file (including the extension).

    Returns:
        A dictionary with the JSON data if the file exists and is valid.
        None if the file does not exist or if there is an error reading it.
    """
    path = Path(path_file)
    try:
        with open(path, 'r', encoding='utf-8') as f:  # UTF-8 encoding handling
            data = json.load(f)
            return data
    except FileNotFoundError:
        raise FileNotFoundError(f"Error: The file '{path.name}' was not found in the directory.")
    except json.JSONDecodeError as e:
        raise ValueError(f"Error: The file '{path.name}' contains invalid JSON. Details: {e}")

def filename(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def format_timestamp(seconds: float) -> str:
    """
    Format a time duration in seconds into an SRT-compatible timestamp.

    Args:
        seconds (float): The time duration in seconds.

    Returns:
        str: The formatted timestamp in the format HH:MM:SS,mmm.
    """

    if not isinstance(seconds, (int, float)):
        raise TypeError("Input must be a float or an int.")
    if seconds < 0:
        raise ValueError("Input must be a non-negative number.")
    
    milliseconds = int(round(seconds * 1000))
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def json_to_srt(data: Dict, outpath_srt: str) -> None:
    """
    Converts JSON data to SRT format.
    
    Args:
        data: Dictionary containing transcription segments
        outpath_srt: Path where to save the SRT file
    """
    if not data or "segments" not in data:
        raise ValueError("Invalid input data: no segments to process")

    try:
        path = Path(outpath_srt)

        with open(path, 'w', encoding='utf-8') as srt_file:
            for i, segment in enumerate(data["segments"], 1):
                if not all(key in segment for key in ["start", "end", "text"]):
                    raise ValueError(f"Segment {i} is missing required fields")
                
                start = format_timestamp(segment["start"])
                end = format_timestamp(segment["end"])
                text = segment["text"].strip()

                srt_file.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    except (OSError, IOError) as e:
        raise SRTConversionError(f"I/O error while writing SRT file: {outpath_srt}", e)
    except Exception as e:
        raise SRTConversionError("Unexpected error during SRT conversion", e)
    

def srt_to_json(path_srt: srt) -> Dict[str, Any]:
    """
    Convert an SRT file to JSON format with transcription segments.
    
    Args:
        path_srt: Path to the SRT file
        
    Returns:
        Dict containing:
            - text: Complete transcript text
            - segments: List of segments with timing and text
            - language: Language code
    """
    try:
        with open(path_srt, "r", encoding="utf-8") as file:
            srt_content = file.read()

        if not srt_content.strip():
            raise ValueError("The SRT file is empty.")

        subs = srt.parse(srt_content)

        if not subs:
            raise ValueError("The SRT file contains no valid segments.")

        segments = []
        text = ""

        for i, sub in enumerate(subs):
            cleaned_text = sub.content.replace("\n", " ").strip()
            text += cleaned_text + " "
            segments.append({
                "id": i,
                "start": sub.start.total_seconds(),
                "end": sub.end.total_seconds(),
                "text": cleaned_text
            })

        json_data = {
            "text": text.strip(),
            "segments": segments,
            "language": "en"
        }
        return json_data
    
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {path_srt} does not exist.")
    except PermissionError:
        raise PermissionError(f"Insufficient permissions to read the file {path_srt}.")
    except srt.SRTParseError as e:
        raise ValueError(f"Error parsing the SRT file: {e}")
    except Exception as e:
        raise Exception(f"An unexpected error occurred: {e}")
    


def mask_api_key(api_key: str) -> str:
    """
    Masks all but the last 4 characters of an API key.
    """
    if len(api_key) <= 4:
        return api_key  # If the key has 4 or fewer characters, it is not masked.
    return f"{'*' * (len(api_key) - 4)}{api_key[-4:]}"



def get_package_name() -> str:
    frame = inspect.currentframe()
    f_back = frame.f_back if frame is not None else None
    f_globals = f_back.f_globals if f_back is not None else None
    # break reference cycle
    # https://docs.python.org/3/library/inspect.html#the-interpreter-stack
    del frame

    package_name: str | None = None
    if f_globals is not None:
        package_name = f_globals.get("__name__")

        if package_name == "__main__":
            package_name = f_globals.get("__package__")

        if package_name:
            package_name = package_name.partition(".")[0]
    if package_name is None:
        raise RuntimeError("Could not determine the package name automatically.")
    return package_name


def get_version(*, package_name: str) -> str:
    import importlib.metadata

    version: str | None = None
    try:
        version = importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        raise RuntimeError(f"{package_name!r} is not installed.") from None

    if version is None:
        raise RuntimeError(
            f"Could not determine the version for {package_name!r} automatically."
        )

    return version


