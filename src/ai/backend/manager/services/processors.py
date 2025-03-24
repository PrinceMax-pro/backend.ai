from ai.backend.manager.services.agent.processors import AgentProcessors
from ai.backend.manager.services.agent.service import AgentService
from ai.backend.manager.services.container_registry.processors import ContainerRegistryProcessors
from ai.backend.manager.services.container_registry.service import ContainerRegistryService
from ai.backend.manager.services.resource.processors import ResourceProcessors
from ai.backend.manager.services.resource.service import ResourceService
from ai.backend.manager.services.resource_preset.processors import ResourcePresetProcessors
from ai.backend.manager.services.resource_preset.service import ResourcePresetService


class Processors:
    agent: AgentProcessors
    resource: ResourceProcessors
    resource_preset: ResourcePresetProcessors
    container_registry: ContainerRegistryProcessors

    def __init__(
        self,
        agent_service: AgentService,
        resource_service: ResourceService,
        resource_preset_service: ResourcePresetService,
        container_registry_service: ContainerRegistryService,
    ) -> None:
        self.agent = AgentProcessors(agent_service)
        self.resource = ResourceProcessors(resource_service)
        self.resource_preset = ResourcePresetProcessors(resource_preset_service)
        self.container_registry = ContainerRegistryProcessors(container_registry_service)
