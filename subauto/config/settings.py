from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from click import MissingParameter, UsageError
from typer import BadParameter

from ..utils.utils import get_language


@dataclass
class VideoConfig:
    
    directory: Path
    output_directory: Path
    input_language: Optional[str] = None
    output_language: str = 'en'
    workers: int = 2
    video_extensions: Set[str] = field(default_factory=lambda: {".mp4", ".avi", ".mkv", ".mov"})
    videos: List[Path] = field(default_factory=list)
    
    def validate(self) -> None:

        if not self.directory:
            raise MissingParameter(
                param_hint="'--directory' / '-d'", param_type="option"
            )
        
        if not self.directory.exists() and not self.directory.is_dir():
            raise BadParameter(
                message=f"The input directory '{self.directory}' does not exist or is not a directory.",
                param_hint="'--directory' / '-d'",
            )
        
        if not self.directory.name:
            raise BadParameter(
                message="The input directory cannot be empty.",
            )
        
        self.find_videos()
        if not self.videos:
            raise BadParameter(
                message="No videos found in the input directory.",
                param_hint="'--directory' / '-d'",
            )

        if not self.output_directory:
            raise MissingParameter(
                param_hint="'--output-directory' / '-o'", param_type="option"
            )

        if not self.output_directory.exists() and not self.output_directory.is_dir():
            raise BadParameter(
                message=f"The output directory '{self.output_directory}' does not exist or is not a directory.",
                param_hint="'--output-directory' / '-o'",
            )
        
        if not self.output_directory.name:
            raise BadParameter(
                message="The output directory cannot be empty.",
                param_hint="'--output-directory' / '-o'",
            )

        if not self.output_language:
            raise MissingParameter(
                param_hint="'--output-lang' / '-ol'", param_type="option"
            )

        if not get_language(self.output_language):
            raise BadParameter(
                message=f"Invalid output language: '{self.output_language}'.",
                param_hint="'--output-lang' / '-ol'",
            )
        
        if self.input_language == '':
            raise MissingParameter(
                param_hint="'--input-lang' / '-il'", param_type="option"
            )
        
        if self.input_language and not get_language(self.input_language):
            raise BadParameter(
                message=f"Invalid input language: '{self.input_language}'.",
                param_hint="'--input-lang' / '-il'",
            )
        
        if self.input_language and self.input_language == self.output_language:
            raise UsageError(
                message=f"The output language: '{self.output_language}' cannot be the same as the input language: '{self.input_language}'.",
            )

        if self.workers < 1:
            raise BadParameter(
                message=f"There must be at least one worker: '{self.workers}'.",
                param_hint="'--workers' / '-w'",
            )        
    
    def find_videos(self) -> List[Path]:
        video_extensions_lower = {ext.lower() for ext in self.video_extensions}
        videos = (
            f
            for f in self.directory.rglob("*")
            if f.is_file() and f.suffix.lower() in video_extensions_lower
        )
        self.videos = list(videos)
        return self.videos
    

    
    