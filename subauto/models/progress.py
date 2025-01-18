from typing import TypedDict

from rich.progress import Progress, TaskID


class ProgressTracker(TypedDict):
    app_steps_progress: Progress
    step_progress: Progress
    app_steps_task: TaskID
    step_task: TaskID

class ProgressTrackers(TypedDict):
    video_name: str
    progress_tracker: ProgressTracker
