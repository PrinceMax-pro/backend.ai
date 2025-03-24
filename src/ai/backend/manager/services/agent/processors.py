from ai.backend.manager.actions.processor import ActionProcessor
from ai.backend.manager.services.agent.actions.get_watcher_status import (
    GetWatcherStatusAction,
    GetWatcherStatusActionResult,
)
from ai.backend.manager.services.agent.actions.watcher_agent_restart import (
    WatcherAgentRestartAction,
    WatcherAgentRestartActionResult,
)
from ai.backend.manager.services.agent.actions.watcher_agent_start import (
    WatcherAgentStartAction,
    WatcherAgentStartActionResult,
)
from ai.backend.manager.services.agent.actions.watcher_agent_stop import (
    WatcherAgentStopAction,
    WatcherAgentStopActionResult,
)
from ai.backend.manager.services.agent.service import AgentService


class AgentProcessors:
    get_watcher_status: ActionProcessor[GetWatcherStatusAction, GetWatcherStatusActionResult]
    watcher_agent_start: ActionProcessor[WatcherAgentStartAction, WatcherAgentStartActionResult]
    watcher_agent_restart: ActionProcessor[
        WatcherAgentRestartAction, WatcherAgentRestartActionResult
    ]
    watcher_agent_stop: ActionProcessor[WatcherAgentStopAction, WatcherAgentStopActionResult]

    def __init__(self, service: AgentService) -> None:
        self.get_watcher_status = ActionProcessor(service.get_watcher_status)
        self.watcher_agent_start = ActionProcessor(service.watcher_agent_start)
        self.watcher_agent_restart = ActionProcessor(service.watcher_agent_restart)
        self.watcher_agent_stop = ActionProcessor(service.watcher_agent_stop)
