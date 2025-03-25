import pytest

from ai.backend.manager.services.groups.processors import GroupProcessors
from ai.backend.manager.services.groups.service import GroupService


@pytest.fixture
def processors(database_fixture, database_engine, storage_manager) -> GroupProcessors:
    group_service = GroupService(db=database_engine, storage_manager=storage_manager)
    return GroupProcessors(group_service)
