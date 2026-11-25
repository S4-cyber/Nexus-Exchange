"""Pure task pagination for the dashboard; no task execution."""
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class TaskPage:
    page: int
    pages: int
    task_ids: tuple[str, ...]

def task_page(task_ids, page=1):
    if type(task_ids) not in (list, tuple):
        raise ValueError("ordered task IDs required")
    if any(type(x) is not str or not x.strip() or len(x)>128 for x in task_ids):
        raise ValueError("invalid task ID")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("duplicate task ID")
    pages = max(1, (len(task_ids)+9)//10)
    if type(page) is not int or not 1 <= page <= pages:
        raise ValueError("invalid page")
    return TaskPage(page,pages,tuple(task_ids[(page-1)*10:page*10]))
