from handlers.start_handler import get_start_handlers
from handlers.task_handler import get_task_handlers
from handlers.stats_handler import get_stats_handlers
from handlers.settings_handler import get_settings_handlers
from handlers.admin_handler import get_admin_handlers

__all__ = [
    "get_start_handlers",
    "get_task_handlers",
    "get_stats_handlers",
    "get_settings_handlers",
    "get_admin_handlers",
]
