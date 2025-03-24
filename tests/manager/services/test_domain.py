import uuid
from datetime import datetime
from typing import Any

import pytest
import sqlalchemy as sa

from ai.backend.common.types import ResourceSlot, VFolderHostPermissionMap
from ai.backend.manager.models.domain import DomainRow
from ai.backend.manager.models.user import UserRole
from ai.backend.manager.models.utils import ExtendedAsyncSAEngine
from ai.backend.manager.services.domain.actions.create_domain import (
    CreateDomainAction,
    CreateDomainActionResult,
)
from ai.backend.manager.services.domain.actions.create_domain_node import (
    CreateDomainNodeAction,
    CreateDomainNodeActionResult,
)
from ai.backend.manager.services.domain.actions.delete_domain import (
    DeleteDomainAction,
    DeleteDomainActionResult,
)
from ai.backend.manager.services.domain.actions.modify_domain import (
    ModifyDomainAction,
    ModifyDomainActionResult,
)
from ai.backend.manager.services.domain.actions.modify_domain_node import (
    ModifyDomainNodeAction,
    ModifyDomainNodeActionResult,
)
from ai.backend.manager.services.domain.actions.purge_domain import (
    PurgeDomainAction,
    PurgeDomainActionResult,
)
from ai.backend.manager.services.domain.processors import DomainProcessors
from ai.backend.manager.services.domain.service import DomainService
from ai.backend.manager.services.domain.types import DomainData, UserInfo

from .test_utils import TestScenario


@pytest.fixture
def processors(database_fixture, database_engine) -> DomainProcessors:
    domain_service = DomainService(database_engine)
    return DomainProcessors(domain_service)


@pytest.fixture
def admin_user() -> UserInfo:
    return UserInfo(
        id=uuid.UUID("f38dea23-50fa-42a0-b5ae-338f5f4693f4"),
        role=UserRole.ADMIN,
        domain_name="default",
    )


@pytest.fixture
async def create_domain(
    database_engine: ExtendedAsyncSAEngine,
):
    async def _create_domain(name: str = "test-domain") -> str:
        async with database_engine.begin() as conn:
            domain_name = name
            domain_data: dict[str, Any] = {
                "name": domain_name,
                "description": f"Test Domain for {name}",
                "is_active": True,
                "total_resource_slots": {},
                "allowed_vfolder_hosts": {},
                "allowed_docker_registries": [],
                "integration_id": None,
            }
            await conn.execute(sa.insert(DomainRow).values(domain_data).returning(DomainRow))
            return domain_name

    return _create_domain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_scenario",
    [
        TestScenario.success(
            "Create a domain node",
            CreateDomainNodeAction(
                name="test-create-domain-node",
                description="Test domain",
                scaling_groups=None,
                user_info=UserInfo(
                    id=uuid.UUID("f38dea23-50fa-42a0-b5ae-338f5f4693f4"),
                    role=UserRole.ADMIN,
                    domain_name="default",
                ),
            ),
            CreateDomainNodeActionResult(
                domain_data=DomainData(
                    name="test-create-domain-node",
                    description="Test domain",
                    is_active=True,
                    created_at=datetime.now(),
                    # created_at 같이 정확한 값을 테스트하기 어려운 경우 어떻게 해야 할지 (현재 모든 필드가 다 매치되어야 테스트 통과)
                    modified_at=datetime.now(),
                    total_resource_slots=ResourceSlot.from_user_input({}, None),
                    allowed_vfolder_hosts=VFolderHostPermissionMap({}),
                    allowed_docker_registries=[],
                    dotfiles=b"\x90",
                    integration_id=None,
                ),
                status="success",
                description="domain test-create-domain-node created",
            ),
        ),
        TestScenario.failure(
            "Create domain node with duplicated name",
            CreateDomainNodeAction(
                name="default",
                description="Test domain",
                scaling_groups=None,
                user_info=UserInfo(
                    id=uuid.UUID("f38dea23-50fa-42a0-b5ae-338f5f4693f4"),
                    role=UserRole.ADMIN,
                    domain_name="default",
                ),
            ),
            ValueError,
        ),
    ],
)
async def test_create_domain_node(
    processors: DomainProcessors,
    test_scenario: TestScenario[CreateDomainNodeAction, CreateDomainNodeActionResult],
):
    await test_scenario.test(processors.create_domain_node.wait_for_complete)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_scenario",
    [
        TestScenario.success(
            "Modify a domain node",
            ModifyDomainNodeAction(
                name="test-modify-domain-node",
                user_info=UserInfo(
                    id=uuid.UUID("f38dea23-50fa-42a0-b5ae-338f5f4693f4"),
                    role=UserRole.SUPERADMIN,
                    domain_name="default",
                ),
                description="Domain Description Modified",
            ),
            ModifyDomainNodeActionResult(
                domain_data=DomainData(
                    name="test-modify-domain-node",
                    description="Domain Description Modified",
                    is_active=True,
                    created_at=datetime.now(),
                    modified_at=datetime.now(),
                    total_resource_slots=ResourceSlot.from_user_input({}, None),
                    allowed_vfolder_hosts=VFolderHostPermissionMap({}),
                    allowed_docker_registries=[],
                    dotfiles=b"\x90",
                    integration_id=None,
                ),
                status="success",
                description="domain test-modify-domain-node modified",
            ),
        ),
        TestScenario.failure(
            "Modify a domain not exists",
            ModifyDomainNodeAction(
                name="not-exist-domain",
                user_info=UserInfo(
                    id=uuid.UUID("f38dea23-50fa-42a0-b5ae-338f5f4693f4"),
                    role=UserRole.SUPERADMIN,
                    domain_name="default",
                ),
                description="Domain Description Modified",
            ),
            ValueError,
        ),
        TestScenario.failure(
            "Modify a domain without enough permission",
            ModifyDomainNodeAction(
                name="not-exist-domain",
                user_info=UserInfo(
                    id=uuid.UUID("dfa9da54-4b28-432f-be29-c0d680c7a412"),
                    role=UserRole.USER,
                    domain_name="default",
                ),
                description="Domain Description Modified",
            ),
            ValueError,
        ),
    ],
)
async def test_modify_domain_node(
    processors: DomainProcessors,
    test_scenario: TestScenario[ModifyDomainNodeAction, ModifyDomainNodeActionResult],
    create_domain,
):
    _ = await create_domain("test-modify-domain-node")
    await test_scenario.test(processors.modify_domain_node.wait_for_complete)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_scenario",
    [
        TestScenario.success(
            "Create a domain",
            CreateDomainAction(
                name="test-create-domain",
                description="Test domain",
            ),
            CreateDomainActionResult(
                domain_data=DomainData(
                    name="test-create-domain",
                    description="Test domain",
                    is_active=True,
                    created_at=datetime.now(),
                    modified_at=datetime.now(),
                    total_resource_slots=ResourceSlot.from_user_input({}, None),
                    allowed_vfolder_hosts=VFolderHostPermissionMap({}),
                    allowed_docker_registries=[],
                    dotfiles=b"\x90",
                    integration_id=None,
                ),
                status="success",
                description="domain creation succeed",
            ),
        ),
        # 현재 실패에 대해 Exception raise가 아니라 None을 반환하고 있는 상황
        TestScenario.success(
            "Create a domain with duplicated name, return none",
            CreateDomainAction(
                name="default",
                description="Test domain",
            ),
            CreateDomainActionResult(
                domain_data=None,
                status="fail",
                description="integrity error",
            ),
        ),
    ],
)
async def test_create_domain(
    processors: DomainProcessors,
    test_scenario: TestScenario[CreateDomainAction, CreateDomainActionResult],
):
    await test_scenario.test(processors.create_domain.wait_for_complete)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_scenario",
    [
        TestScenario.success(
            "Modify domain",
            ModifyDomainAction(
                name="test-modify-domain",
                description="Domain Description Modified",
            ),
            ModifyDomainActionResult(
                domain_data=DomainData(
                    name="test-modify-domain",
                    description="Domain Description Modified",
                    is_active=True,
                    created_at=datetime.now(),
                    modified_at=datetime.now(),
                    total_resource_slots=ResourceSlot.from_user_input({}, None),
                    allowed_vfolder_hosts=VFolderHostPermissionMap({}),
                    allowed_docker_registries=[],
                    dotfiles=b"\x90",
                    integration_id=None,
                ),
                status="success",
                description="domain modification succeed",
            ),
        ),
        TestScenario.success(
            "Modify a domain not exists",
            ModifyDomainAction(
                name="not-exist-domain",
                description="Domain Description Modified",
            ),
            ModifyDomainActionResult(
                domain_data=None,
                status="failed",
                description="domain not found",
            ),
        ),
    ],
)
async def test_modify_domain(
    processors: DomainProcessors,
    test_scenario: TestScenario[ModifyDomainAction, ModifyDomainActionResult],
    create_domain,
):
    _ = await create_domain("test-modify-domain")
    await test_scenario.test(processors.modify_domain.wait_for_complete)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_scenario",
    [
        TestScenario.success(
            "Delete a domain",
            DeleteDomainAction(
                name="test-delete-domain",
            ),
            DeleteDomainActionResult(
                status="success",
                description="domain test-delete-domain deleted successfully",
            ),
        ),
        TestScenario.success(
            "Delete a domain not exists",
            DeleteDomainAction(
                name="not-exist-domain",
            ),
            DeleteDomainActionResult(
                status="failed",
                description="no matching not-exist-domain",
            ),
        ),
    ],
)
async def test_delete_domain(
    processors: DomainProcessors,
    test_scenario: TestScenario[DeleteDomainAction, DeleteDomainActionResult],
    create_domain,
):
    _ = await create_domain("test-delete-domain")
    await test_scenario.test(processors.delete_domain.wait_for_complete)
    # TODO: soft delete 되었는지 직접 DB에 조회해야 하는지 확인 필요


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_scenario",
    [
        TestScenario.success(
            "Purge a domain",
            PurgeDomainAction(
                name="test-purge-domain",
            ),
            PurgeDomainActionResult(
                status="success",
                description="domain test-purge-domain purged successfully",
            ),
        ),
        TestScenario.success(
            "Purge a domain not exists",
            PurgeDomainAction(
                name="not-exist-domain",
            ),
            PurgeDomainActionResult(
                status="failed",
                description="no matching not-exist-domain domain to purge",
            ),
        ),
    ],
)
async def test_purge_domain(
    processors: DomainProcessors,
    test_scenario: TestScenario[PurgeDomainAction, PurgeDomainActionResult],
    create_domain,
):
    _ = await create_domain("test-purge-domain")
    await test_scenario.test(processors.purge_domain.wait_for_complete)
    # TODO: hard delete 되었는지 직접 DB에 조회해야 하는지 확인 필요
