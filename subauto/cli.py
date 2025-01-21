import json
import os
import warnings
from multiprocessing import Pipe, Pool, cpu_count
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Dict, List, Optional

import typer
import whisper
from click import UsageError
from click.exceptions import MissingParameter
from google import genai
from google.genai import errors, types
from rich.console import Console, Group
from rich.live import Live
from rich.padding import Padding
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column
from typing_extensions import Annotated
from whisper.utils import get_writer

from subauto.config.api_manager import APIKeyManager
from subauto.config.settings import VideoConfig
from subauto.models.progress import ProgressTracker
from subauto.utils.logging import (
    get_log_directory,
    get_process_logger,
    init_session,
    init_worker_logging,
)
from subauto.utils.utils import (
    embed_subtitles,
    filename,
    get_language,
    get_package_name,
    get_version,
    json_to_srt,
    srt_to_json,
)

os.environ["OMP_DISPLAY_ENV"] = "FALSE"
os.environ["KMP_WARNINGS"] = "0"

app = typer.Typer()
console = Console()
key_manager = APIKeyManager()

def version_callback(*, value: bool) -> None:
    if value:
        package_name = get_package_name()
        version = get_version(package_name=package_name)
        typer.echo(f"{package_name} {version}")
        raise typer.Exit()

def translate_batch_with_gemini(datos: list, input_language: str, output_language: str) -> Optional[List]:
    
    logger_base = get_process_logger()
    api_key = key_manager.get_api_key()
    client = genai.Client(api_key=api_key)

    input_language = get_language(input_language)
    target_language = get_language(output_language)
    formatted_data = json.dumps(datos, indent=4, separators=(",", ": "), ensure_ascii=False)

    prompt_v10 = f"""
Translate the following {len(datos)} {input_language} segments into {target_language}.  The JSON response must contain a "translation" array with exactly {len(datos)} elements. Each element should be the {target_language} translation of the corresponding {input_language} segment. Translate only up to the punctuation mark; do not translate beyond it.

Segments: {formatted_data}

Output Format (MUST have {len(datos)} elements in the "translation" array):
```json
{{
"translation": [
        // ... {len(datos)} elements here
    ]
}}
"""

    resp_count_tokens = client.models.count_tokens(
        model="gemini-2.0-flash-exp",
        contents=prompt_v10,
    )
    logger_base.debug(f"resp_count_tokens: {resp_count_tokens}")
    logger_base.debug(f"prompt_v10: {prompt_v10}")
    num_characters = len(prompt_v10)
    logger_base.debug(f"num_characters: {num_characters}")

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=prompt_v10,
            config=types.GenerateContentConfig(
                safety_settings= [
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_CIVIC_INTEGRITY', threshold='BLOCK_NONE')
                ],
                temperature= 0.3,
                top_p=1,
                top_k=1,
            ),
        )
        response_text = response.text
        logger_base.debug(f"response_text: {response_text}")
        logger_base.debug(f"usage_metadata: {response.usage_metadata}")

        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        json_str = response_text[json_start:json_end]
        translated_texts = json.loads(json_str)

        return translated_texts['translation']
            
    except Exception as e:
        logger_base.debug(f"Batch translation error: {str(e)}")
        return None

def process_single_video(video_data: tuple[str, whisper.Whisper, Connection], config: VideoConfig) -> bool:
    """
    Process a single video with progress tracking via pipe
    
    :param video_data: Tuple containing (video_path, model, parent_pipe)
    :return: Processing result
    """    
    input_language = config.input_language
    output_language = config.output_language
    directory = config.directory
    output_directory = config.output_directory

    video_path, model, parent_pipe = video_data
    
    logger_base = get_process_logger()
    logger_base.debug(f"In a worker process: {os.getpid()}")

    try:
        warnings.filterwarnings("ignore")
        current_step = 0

        # Transcribe
        transcribe_args = {
            "audio": video_path,
            "fp16": False,
            "verbose": None,
            "word_timestamps": True,
        }

        if input_language:
            transcribe_args["language"] = input_language

        result = model.transcribe(**transcribe_args)
        current_step += 1
        parent_pipe.send((video_path, current_step))
        logger_base.debug(f"Transcription completed for {video_path}")

        language = result["language"]
        logger_base.info(f"Detected language: {language}")

        if language == output_language:
            raise typer.Exit(1)

        # Create SRT
        word_options = {
            "max_line_count": 2,
            "max_line_width": 38,
            "max_words_per_line": 9,
        }

        format_directory = os.path.normpath(directory)
        relative_dir = os.path.relpath(os.path.dirname(video_path), format_directory)


        logger_base.info(f"format_directory: {format_directory}")
        logger_base.info(f"relative_dir: {relative_dir}")
        logger_base.info(f"filename(path): {filename(video_path)}")
        logger_base.info(f"output_directory: {output_directory}")

        srt_path = os.path.join(output_directory, relative_dir, f"{filename(video_path)} - {language.upper()}.srt")  

        logger_base.info(f"srt_path: {srt_path}")
        
        test_var = os.path.join(output_directory, relative_dir)
        os.makedirs(test_var, exist_ok=True)
        srt_writer = get_writer("srt", test_var)
        srt_writer(result, srt_path, word_options)
        current_step += 1
        parent_pipe.send((str(video_path), current_step))
        logger_base.debug(f"SRT file created: {srt_path}")

        # Convert to JSON
        json_data = srt_to_json(srt_path)
        
        # Translate
        texts_to_translate = [segment["text"].lstrip() for segment in json_data["segments"]]
        num_texts = len(texts_to_translate)
        logger_base.debug(f"num_texts: {num_texts}")
        max_items = 150
        sublists = [texts_to_translate[i:i + max_items] for i in range(0, num_texts, max_items)]
        final_results = []

        for sublist in sublists:            
            translated_segments = translate_batch_with_gemini(sublist, language, output_language)
            
            if not translated_segments:
                logger_base.error("Error while translating")
                raise typer.Exit(1)
            final_results.extend(translated_segments)

        if not final_results:
            logger_base.error("The list final_results is empty")
            raise typer.Exit(1)
        
        for segment, translated_text in zip(json_data['segments'], final_results):
            segment["text"] = translated_text
        
        # Create Translated SRT
        nombre_archivo_srt = os.path.join(output_directory, relative_dir, f"{filename(video_path)} - {output_language.upper()}.srt")
        json_to_srt(json_data, nombre_archivo_srt)
        
        current_step += 1
        parent_pipe.send((str(video_path), current_step))
        logger_base.info(f"Translation completed for {video_path}")

        # Burning
        srt_paths = { f'{language}': f'{srt_path}', f'{output_language}': f'{nombre_archivo_srt}'}
        logger_base.info(f"srt_paths: {srt_paths}")
        output_path = os.path.join(output_directory, relative_dir, f"{filename(video_path)}.mp4")
        embed_subtitles(video_path=video_path, srt_paths=srt_paths, output_path=output_path)

        current_step += 1
        parent_pipe.send((str(video_path), current_step))
        logger_base.info(f"Burning completed for {video_path}")
        logger_base.info(f"Processing completed for {video_path}")
        return True

    except errors.ClientError as e:
        logger_base.error(
            f"ClientError {video_path} | step {current_step}: {str(e)}",
            exc_info=True,
        )
        if e.message:
            error_msg = "API key not valid"
            if error_msg in e.message:
                parent_pipe.send(("API_KEY_ERROR", -1))
                parent_pipe.close()
                return False

        parent_pipe.send((str(video_path), -1))
        parent_pipe.close()
        return False
    
    except Exception as e:
        logger_base.error(
            f"Exception {video_path} | step {current_step}: {str(e)}",
            exc_info=True,
        )
        parent_pipe.send((str(video_path), -1))
        parent_pipe.close()
        return False 

def process_videos_concurrently(model:whisper.Whisper, config:VideoConfig) -> Dict[str, int]:
    """
    Process videos in parallel with individual progress tracking
    
    :param model: Whisper model
    :param config: Config
    """
    logger_base = get_process_logger()
    videos = config.videos
    workers = config.workers

    current_session_id = init_session()

    console.print(f"[green]Found {len(videos)} videos ready for processing [/]")
    logger_base.info(f"Init {len(videos)} videos")
    nro_workers = 1
    if workers:
        if workers >= cpu_count():
            nro_workers = min(len(videos), cpu_count() - 1)
        else:
            nro_workers = min(len(videos), workers)
    
    # Configure workers
    logger_base.info(f"CPU COUNT: {cpu_count()}")
    console.print(f"[green]Workers: {nro_workers}[/]")
    console.print()
    
    # Create pipes for each video
    pipes = [Pipe() for _ in videos]
    parent_pipes = [p[0] for p in pipes]
    child_pipes = [p[1] for p in pipes]

    # Prepare video processing data
    video_processing_data = [(str(video), model, child_pipe) for video, child_pipe in zip(videos, child_pipes)]
    
    # Create pool and processes
    pool = Pool(processes=nro_workers, initializer=init_worker_logging, initargs=(current_session_id,))    

    for video_data in video_processing_data:
        pool.apply_async(
            process_single_video,
            args=(video_data, config),
        )

    video_groups = []
    progress_trackers: Dict[str, ProgressTracker] = {}

    for video in videos:
        video_name = str(video)
        app_steps_progress = Progress(
            TextColumn(
                text_format = "[#03a9f4]File:[/] [bold blue]{task.fields[name]}[/]",
                table_column=Column(width=35, overflow="ellipsis", no_wrap=True),
            ),
            BarColumn(),
            TextColumn("[bold blue]{task.percentage:.0f}%[/] ({task.completed}/{task.total} steps done)"),
        )

        step_progress = Progress(
            TextColumn("  "),
            TimeElapsedColumn(),
            TextColumn("[bold orchid]{task.fields[action]}"),
            SpinnerColumn("simpleDots"),
        )

        app_steps_task = app_steps_progress.add_task("", total=4, name=video.name)
        step_task = step_progress.add_task("", action="Transcribing", total=4, name=video.name)

        progress_trackers[video_name] = {
            'app_steps_progress': app_steps_progress,
            'step_progress': step_progress,
            'app_steps_task': app_steps_task,
            'step_task': step_task
        }

    video_groups = [
        Group(tracker['app_steps_progress'], tracker['step_progress']) 
        for tracker in progress_trackers.values()
    ]

    overall_progress = Progress(
        TimeElapsedColumn(), 
        BarColumn(), 
        TextColumn("[bold #AAAAAA]({task.fields[success_videos]} out of {task.total} videos processed)")
    )

    progress_group = Group(Group(*video_groups), Padding(overall_progress, (1, 0, 0, 0)))
    failed_videos = 0
    success_videos = 0

    overall_task_id = overall_progress.add_task("", total=len(videos), success_videos=0)

    with Live(progress_group):
        completed_workers = {str(video): 0 for video in videos}

        while sum(completed_workers.values()) < len(videos) * 4:

            for parent_pipe, video in zip(parent_pipes, videos):
                
                if not parent_pipe.closed and parent_pipe.poll():
                    task_id, completed = parent_pipe.recv()
                    
                    if task_id == "API_KEY_ERROR":
                        
                        for video_name, tracker in progress_trackers.items():
                            app_steps_progress = tracker['app_steps_progress']
                            step_progress = tracker['step_progress']
                            app_steps_task = tracker['app_steps_task']
                            step_task = tracker['step_task']
                            
                            app_steps_progress.update(
                                tracker["app_steps_task"],
                                description=f"[red]Error processing {Path(video_name).name}",
                            )
                            step_progress.update(
                                tracker["step_task"],
                                action="[red]Error[/red]",
                                completed=4,
                            )
                            completed_workers[video_name] = 4
                            failed_videos += 1
                        
                        parent_pipe.close()


                    # Verificar si el task_id existe en los trackers
                    if task_id in progress_trackers:
                        tracker = progress_trackers[task_id]
                        
                        if completed == -1:  # Error
                            tracker['app_steps_progress'].update(
                                tracker['app_steps_task'], 
                                description = f"[red]Error processing {Path(task_id).name}"
                            )
                            tracker['step_progress'].update(
                                tracker['step_task'], 
                                action="[red]Error[/red]",
                                completed = 4 
                            )
                            
                            completed_workers[task_id] = 4
                            parent_pipe.close()        
                            failed_videos += 1                    
                        else:

                            action = ""
                            if completed == 1:
                                action = "Creating SRT"
                            elif completed == 2:
                                action = "Translating"
                            elif completed == 3:
                                action = "Burning"  
                            elif completed >= 4:
                                action = "Completed"  

                            tracker['app_steps_progress'].update(
                                tracker['app_steps_task'], 
                                completed=completed,
                            )
                            
                            tracker['step_progress'].update(
                                tracker['step_task'], 
                                action=action,
                                completed=completed,
                            )
                            tracker['step_progress'].stop_task(tracker['step_task'])
                            
                            if completed >= 4:
                                completed_workers[task_id] = 4
                                parent_pipe.close()
                                success_videos += 1

                                overall_progress.update(overall_task_id, success_videos=success_videos, advance=1)
        
    # Close pool
    pool.close()
    pool.join()
        
    # After processing
    processed_videos = len(videos)

    summary = {
        'total_videos': processed_videos,
        'success_videos': success_videos,
        'failed_videos': failed_videos
    }

    logger_base.info(f"Processing summary: {summary}")

    if failed_videos > 0:
        logger_base.warning(f"Warning: {failed_videos} videos were not processed correctly")

    return summary

@app.command()
def set_api_key(

    api_key: Annotated[str, typer.Argument(help="Gemini API Key to store")],
) -> None:
    """Set the Gemini API key in the configuration file."""
    logger_base = get_process_logger()
    try:
        api_key = key_manager.get_api_key(api_key)
    except key_manager.ApiManagerError as e:
        logger_base.error(f"ApiManagerError: {e}", exc_info=True)
        raise UsageError(message=e.message)
    

@app.callback(invoke_without_command=True)
def process_videos(
    ctx: typer.Context,
    directory: Annotated[Optional[Path], typer.Option("--directory", "-d", help="Input directory containing the videos to process")]= None,
    output_directory: Annotated[Optional[Path], typer.Option("--output-directory", "-o", help="Output directory where the processed videos will be saved")]= None,
    output_language: Annotated[Optional[str], typer.Option("--output-lang", "-ol", help="Output language for translation")]= None,
    input_language: Annotated[Optional[str], typer.Option("--input-lang", "-il", help="Video language (ex. 'es', 'en', 'fr')")] = None,
    workers: Annotated[Optional[int], typer.Option("--workers", "-w", help="Number of processes (default 2)")] = 2,
    version: Annotated[Optional[bool], typer.Option("--version", "-v", callback=version_callback, is_eager=True)] = None,
) -> None:
    
    if ctx.invoked_subcommand:
        return
    
    logger_base = get_process_logger()


    try:
        key_manager.get_api_key()
        config = VideoConfig(
            directory=directory,
            output_directory=output_directory,
            input_language=input_language,
            output_language=output_language,
            workers=workers
        )
        config.validate()

        #console.print("[yellow]Cargando modelo de Whisper...[/yellow]")
        warnings.filterwarnings("ignore")
        model = whisper.load_model("medium")
        warnings.filterwarnings("default")
        summary = process_videos_concurrently(model, config)
    except MissingParameter as e:
        logger_base.error(f"MissingParameter Config: {e}", exc_info=True)
        raise e
    except key_manager.ApiManagerError as e:
        logger_base.error(f"ApiManagerError: {e}", exc_info=True)
        raise typer.Exit(1)
    except UsageError as e:
        logger_base.error(f"UsageError Config: {e}", exc_info=True)
        raise e
    except key_manager.ApiManagerError as e:
        logger_base.error(f"ApiManagerError: {e}", exc_info=True)
        raise typer.Exit(1)

    console.print()
    console.print("[green]Summary: [/]")
    console.print(f"[green]✅ Completed videos: {summary['success_videos']} [/]")

    log_message = (
        f"(For more details, check the log files at: {str(get_log_directory())})"
        if summary["failed_videos"]
        else ""
    )

    console.print(
        f"[red]❌ Failed videos: {summary['failed_videos']} {log_message} [/]"
    )


if __name__ == "__main__":
    app()