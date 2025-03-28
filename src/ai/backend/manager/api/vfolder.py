from __future__ import annotations

import asyncio
import functools
import json
import logging
import math
import stat
import textwrap
import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Awaitable,
    Callable,
    Concatenate,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    ParamSpec,
    Sequence,
    Tuple,
    TypeAlias,
    cast,
)

import aiohttp
import aiohttp_cors
import aiotools
import attrs
import sqlalchemy as sa
import trafaret as t
from aiohttp import web
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
)
from sqlalchemy.ext.asyncio import AsyncSession as SASession
from sqlalchemy.orm import load_only, selectinload

from ai.backend.common import msgpack, redis_helper
from ai.backend.common import typed_validators as tv
from ai.backend.common import validators as tx
from ai.backend.common.defs import VFOLDER_GROUP_PERMISSION_MODE
from ai.backend.common.types import (
    QuotaScopeID,
    QuotaScopeType,
    RedisConnectionInfo,
    VFolderHostPermission,
    VFolderHostPermissionMap,
    VFolderID,
    VFolderUsageMode,
)
from ai.backend.logging import BraceStyleAdapter
from ai.backend.manager.models.storage import StorageSessionManager

from ..models import (
    ACTIVE_USER_STATUSES,
    HARD_DELETED_VFOLDER_STATUSES,
    AgentStatus,
    EndpointLifecycle,
    EndpointRow,
    GroupRow,
    KernelStatus,
    ProjectResourcePolicyRow,
    ProjectType,
    UserResourcePolicyRow,
    UserRole,
    UserRow,
    UserStatus,
    VFolderCloneInfo,
    VFolderDeletionInfo,
    VFolderInvitationState,
    VFolderOperationStatus,
    VFolderOwnershipType,
    VFolderPermission,
    VFolderPermissionSetAlias,
    VFolderPermissionValidator,
    VFolderStatusSet,
    agents,
    ensure_host_permission_allowed,
    filter_host_allowed_permission,
    get_allowed_vfolder_hosts_by_group,
    get_allowed_vfolder_hosts_by_user,
    initiate_vfolder_clone,
    initiate_vfolder_deletion,
    kernels,
    keypair_resource_policies,
    keypairs,
    query_accessible_vfolders,
    query_owned_dotfiles,
    update_vfolder_status,
    users,
    verify_vfolder_name,
    vfolder_invitations,
    vfolder_permissions,
    vfolder_status_map,
    vfolders,
)
from ..models.utils import execute_with_retry, execute_with_txn_retry
from ..models.vfolder import (
    VFolderPermissionRow,
    delete_vfolder_relation_rows,
    is_unmanaged,
)
from ..models.vfolder import VFolderRow as VFolderDBRow
from .auth import admin_required, auth_required, superadmin_required
from .exceptions import (
    BackendAgentError,
    GenericForbidden,
    GroupNotFound,
    InsufficientPrivilege,
    InternalServerError,
    InvalidAPIParameters,
    ModelServiceDependencyNotCleared,
    ObjectNotFound,
    TooManyVFoldersFound,
    VFolderAlreadyExists,
    VFolderCreationFailed,
    VFolderFilterStatusFailed,
    VFolderFilterStatusNotAvailable,
    VFolderNotFound,
    VFolderOperationFailed,
)
from .manager import ALL_ALLOWED, READ_ALLOWED, server_status_required
from .resource import get_watcher_info
from .utils import (
    BaseResponseModel,
    check_api_params,
    get_user_scopes,
    pydantic_params_api_handler,
)

if TYPE_CHECKING:
    from .context import RootContext

log = BraceStyleAdapter(logging.getLogger(__spec__.name))

VFolderRow: TypeAlias = Mapping[str, Any]
P = ParamSpec("P")


class SuccessResponseModel(BaseResponseModel):
    success: bool = Field(default=True)


async def check_vfolder_status(
    folder_row: VFolderRow,
    status: VFolderStatusSet,
) -> None:
    """
    Checks if the target vfolder status matches one of the status sets aliased by `status` VFolderStatusSet,
    and when check fails, raises VFolderFilterStatusFailed.
    This function should prevent user from accessing VFolders which are performing critical operations
    (e.g. VFolder cloning, removal, ...).
    This helper can be combined with `resolve_vfolders
    """

    available_vf_statuses = vfolder_status_map.get(status)
    if not available_vf_statuses:
        raise VFolderFilterStatusNotAvailable
    if folder_row["status"] not in available_vf_statuses:
        raise VFolderFilterStatusFailed


def with_vfolder_status_checked(
    status: VFolderStatusSet,
) -> Callable[
    [Callable[Concatenate[web.Request, VFolderRow, P], Awaitable[web.Response]]],
    Callable[Concatenate[web.Request, Sequence[VFolderRow], P], Awaitable[web.Response]],
]:
    """
    Checks if the target vfolder status matches one of the status sets aliased by `status` VFolderStatusSet.
    This function should prevent user from accessing VFolders which are performing critical operations
    (e.g. VFolder being cloned, being removed, ...).
    This helper can be combined with `resolve_vfolders
    """

    def _wrapper(
        handler: Callable[Concatenate[web.Request, VFolderRow, P], Awaitable[web.Response]],
    ) -> Callable[Concatenate[web.Request, Sequence[VFolderRow], P], Awaitable[web.Response]]:
        @functools.wraps(handler)
        async def _wrapped(
            request: web.Request,
            folder_rows: Sequence[VFolderRow],
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> web.Response:
            if len(folder_rows) > 1:
                raise TooManyVFoldersFound(folder_rows)
            if len(folder_rows) == 0:
                raise VFolderNotFound()
            row = folder_rows[0]
            await check_vfolder_status(row, status)
            return await handler(request, row, *args, **kwargs)

        return _wrapped

    return _wrapper


async def resolve_vfolder_rows(
    request: web.Request,
    perm: VFolderPermissionSetAlias | VFolderPermission | str,
    folder_id_or_name: str | uuid.UUID,
    *,
    allowed_status_set: VFolderStatusSet | None = None,
    allow_privileged_access: bool = False,
) -> Sequence[VFolderRow]:
    """
    Checks if the target VFolder exists and is either:
    - owned by requester, or
    - original owner (of target VFolder) has granted certain level of access to the requester

    When requester passes VFolder name to `folder_id_or_name` parameter then there is a possibility for
    this helper to return multiple entries of VFolder rows which are considered deleted,
    since Backend.AI also is aware of both deleted and purged VFolders. Resolving VFolder row by ID
    will not fall in such cases as it is guaranted by DB side that every VFolder ID is unique across whole table.
    To avoid such behavior, either do not consider VFolder name as an index to resolve VFolder row or
    pass every returned elements of this helper to a separate check_vfolder_status() call, so that
    the handler can figure out which row is the actual row that is aware of.
    """

    root_ctx: RootContext = request.app["_root.context"]
    domain_name = request["user"]["domain_name"]
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    vf_user_cond = None
    vf_group_cond = None

    match perm:
        case VFolderPermissionSetAlias():
            invited_perm_cond = vfolder_permissions.c.permission.in_(list(perm.value))
            if not request["is_admin"]:
                vf_group_cond = vfolders.c.permission.in_(list(perm.value))
        case _:
            # Otherwise, just compare it as-is (for future compatibility).
            invited_perm_cond = vfolder_permissions.c.permission == perm
            if not request["is_admin"]:
                vf_group_cond = vfolders.c.permission == perm

    match folder_id_or_name:
        case str():
            extra_vf_conds = vfolders.c.name == folder_id_or_name
        case uuid.UUID():
            extra_vf_conds = vfolders.c.id == folder_id_or_name
        case _:
            raise RuntimeError(f"Unsupported VFolder index type {type(folder_id_or_name)}")

    async with root_ctx.db.begin_readonly() as conn:
        entries = await query_accessible_vfolders(
            conn,
            user_uuid,
            allow_privileged_access=allow_privileged_access,
            user_role=user_role,
            domain_name=domain_name,
            allowed_vfolder_types=allowed_vfolder_types,
            extra_vf_conds=extra_vf_conds,
            extra_invited_vf_conds=invited_perm_cond,
            extra_vf_user_conds=vf_user_cond,
            extra_vf_group_conds=vf_group_cond,
            allowed_status_set=allowed_status_set,
        )
        if len(entries) == 0:
            raise VFolderNotFound(extra_data=folder_id_or_name)
        return entries


def with_vfolder_rows_resolved(
    perm: VFolderPermissionSetAlias | VFolderPermission,
    *,
    allow_privileged_access: bool = False,
) -> Callable[
    [Callable[Concatenate[web.Request, Sequence[VFolderRow], P], Awaitable[web.Response]]],
    Callable[Concatenate[web.Request, P], Awaitable[web.Response]],
]:
    """
    Decorator to pass result of `resolve_vfolder_rows()` to request handler. Index of VFolder is
    extracted from `name` path parameter. When multiple VFolder entries share same name, this decorator
    will pass every rows matching with the name and it is up to `with_vfolder_status_checked` decorator
    to filter out only row with its status matching the intention of the handler.
    Check documentation of `resolve_vfolder_rows()` for more information.
    """

    def _wrapper(
        handler: Callable[
            Concatenate[web.Request, Sequence[VFolderRow], P], Awaitable[web.Response]
        ],
    ) -> Callable[Concatenate[web.Request, P], Awaitable[web.Response]]:
        @functools.wraps(handler)
        async def _wrapped(request: web.Request, *args: P.args, **kwargs: P.kwargs) -> web.Response:
            folder_name_or_id: str | uuid.UUID
            piece = request.match_info["name"]
            try:
                folder_name_or_id = uuid.UUID(piece)
            except ValueError:
                folder_name_or_id = piece
            return await handler(
                request,
                await resolve_vfolder_rows(
                    request,
                    perm,
                    folder_name_or_id,
                    allow_privileged_access=allow_privileged_access,
                ),
                *args,
                **kwargs,
            )

        return _wrapped

    return _wrapper


def vfolder_check_exists(
    handler: Callable[Concatenate[web.Request, VFolderRow, P], Awaitable[web.Response]],
) -> Callable[Concatenate[web.Request, P], Awaitable[web.Response]]:
    """
    Checks if the target vfolder exists and is owned by the current user.

    The decorated handler should accept an extra "row" argument
    which contains the matched VirtualFolder table row.
    """

    @functools.wraps(handler)
    async def _wrapped(request: web.Request, *args: P.args, **kwargs: P.kwargs) -> web.Response:
        root_ctx: RootContext = request.app["_root.context"]
        user_uuid = request["user"]["uuid"]
        folder_name = request.match_info["name"]
        async with root_ctx.db.begin() as conn:
            j = sa.join(
                vfolders,
                vfolder_permissions,
                vfolders.c.id == vfolder_permissions.c.vfolder,
                isouter=True,
            )
            query = (
                sa.select("*")
                .select_from(j)
                .where(
                    ((vfolders.c.user == user_uuid) | (vfolder_permissions.c.user == user_uuid))
                    & (vfolders.c.name == folder_name)
                )
            )
            try:
                result = await conn.execute(query)
            except sa.exc.DataError:
                raise InvalidAPIParameters
            row = result.first()
            if row is None:
                raise VFolderNotFound()
        return await handler(request, row, *args, **kwargs)

    return _wrapped


class CreateRequestModel(BaseModel):
    name: tv.VFolderName = Field(
        description="Name of the vfolder",
    )
    folder_host: str | None = Field(
        validation_alias=AliasChoices("host", "folder_host"),
        default=None,
    )
    usage_mode: VFolderUsageMode = Field(default=VFolderUsageMode.GENERAL)
    permission: VFolderPermission = Field(default=VFolderPermission.READ_WRITE)
    unmanaged_path: str | None = Field(
        validation_alias=AliasChoices("unmanaged_path", "unmanagedPath"),
        default=None,
    )
    group: str | uuid.UUID | None = Field(
        validation_alias=AliasChoices("group", "groupId", "group_id"),
        default=None,
    )
    cloneable: bool = Field(
        default=False,
    )


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(CreateRequestModel)
async def create(request: web.Request, params: CreateRequestModel) -> web.Response:
    resp: Dict[str, Any] = {}
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    user_role = request["user"]["role"]
    user_uuid: uuid.UUID = request["user"]["uuid"]
    keypair_resource_policy = request["keypair"]["resource_policy"]
    domain_name = request["user"]["domain_name"]
    group_id_or_name = params.group
    log.info(
        "VFOLDER.CREATE (email:{}, ak:{}, vf:{}, vfh:{}, umod:{}, perm:{})",
        request["user"]["email"],
        access_key,
        params.name,
        params.folder_host,
        params.usage_mode.value,
        params.permission.value,
    )
    folder_host = params.folder_host
    unmanaged_path = params.unmanaged_path
    # Resolve host for the new virtual folder.
    if not folder_host:
        folder_host = await root_ctx.shared_config.etcd.get("volumes/default_host")
        if not folder_host:
            raise InvalidAPIParameters(
                "You must specify the vfolder host because the default host is not configured."
            )
    # Check if user is trying to created unmanaged vFolder
    if unmanaged_path:
        # Approve only if user is Admin or Superadmin
        if user_role not in (UserRole.ADMIN, UserRole.SUPERADMIN):
            raise GenericForbidden("Insufficient permission")
            # Assign ghost host to unmanaged vfolder

    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()

    if params.name.startswith(".") and params.name != ".local":
        if params.group is not None:
            raise InvalidAPIParameters("dot-prefixed vfolders cannot be a group folder.")

    group_uuid: uuid.UUID | None = None
    group_type: ProjectType | None = None
    max_vfolder_count: int
    max_quota_scope_size: int
    container_uid: Optional[int] = None

    async with root_ctx.db.begin_session() as sess:
        match group_id_or_name:
            case str():
                # Convert the group name to group uuid.
                log.debug("group_id_or_name(str):{}", group_id_or_name)
                query = (
                    sa.select(GroupRow)
                    .where(
                        (GroupRow.domain_name == domain_name) & (GroupRow.name == group_id_or_name)
                    )
                    .options(selectinload(GroupRow.resource_policy_row))
                )
                result = await sess.execute(query)
                group_row = cast(GroupRow | None, result.scalar())
                if group_row is None:
                    raise GroupNotFound(extra_data=group_id_or_name)
                _gid, max_vfolder_count, max_quota_scope_size = (
                    cast(uuid.UUID | None, group_row.id),
                    cast(int, group_row.resource_policy_row.max_vfolder_count),
                    cast(int, group_row.resource_policy_row.max_quota_scope_size),
                )
                if _gid is None:
                    raise GroupNotFound(extra_data=group_id_or_name)
                group_uuid = _gid
                group_type = cast(ProjectType, group_row.type)
            case uuid.UUID():
                # Check if the group belongs to the current domain.
                log.debug("group_id_or_name(uuid):{}", group_id_or_name)
                query = (
                    sa.select(GroupRow)
                    .where(
                        (GroupRow.domain_name == domain_name) & (GroupRow.id == group_id_or_name)
                    )
                    .options(selectinload(GroupRow.resource_policy_row))
                )
                result = await sess.execute(query)
                group_row = cast(GroupRow | None, result.scalar())
                if group_row is None:
                    raise GroupNotFound(extra_data=group_id_or_name)
                _gid, max_vfolder_count, max_quota_scope_size = (
                    group_row.id,
                    cast(int, group_row.resource_policy_row.max_vfolder_count),
                    cast(int, group_row.resource_policy_row.max_quota_scope_size),
                )
                if _gid is None:
                    raise GroupNotFound(extra_data=group_id_or_name)
                group_uuid = group_id_or_name
                group_type = cast(ProjectType, group_row.type)
            case None:
                query = (
                    sa.select(UserRow)
                    .where(UserRow.uuid == user_uuid)
                    .options(selectinload(UserRow.resource_policy_row))
                )
                result = await sess.execute(query)
                user_row = result.scalar()
                max_vfolder_count, max_quota_scope_size = (
                    cast(int, user_row.resource_policy_row.max_vfolder_count),
                    cast(int, user_row.resource_policy_row.max_quota_scope_size),
                )
                container_uid = cast(Optional[int], user_row.container_uid)
            case _:
                raise GroupNotFound(extra_data=group_id_or_name)

        vfolder_permission_mode = (
            VFOLDER_GROUP_PERMISSION_MODE if container_uid is not None else None
        )

        # Check if group exists when it's given a non-empty value.
        if group_id_or_name and group_uuid is None:
            raise GroupNotFound(extra_data=group_id_or_name)

        # Determine the ownership type and the quota scope ID.
        if group_uuid is not None:
            ownership_type = "group"
            quota_scope_id = QuotaScopeID(QuotaScopeType.PROJECT, group_uuid)
            if not request["is_admin"] and group_type != ProjectType.MODEL_STORE:
                raise GenericForbidden("no permission")
        else:
            ownership_type = "user"
            quota_scope_id = QuotaScopeID(QuotaScopeType.USER, user_uuid)
        if ownership_type not in allowed_vfolder_types:
            raise InvalidAPIParameters(
                f"{ownership_type}-owned vfolder is not allowed in this cluster"
            )

    if group_type == ProjectType.MODEL_STORE:
        if params.permission != VFolderPermission.READ_WRITE:
            raise InvalidAPIParameters(
                "Setting custom permission is not supported for model store vfolder"
            )
        if params.usage_mode != VFolderUsageMode.MODEL:
            raise InvalidAPIParameters(
                "Only Model VFolder can be created under the model store project"
            )

    async with root_ctx.db.begin() as conn:
        await ensure_host_permission_allowed(
            conn,
            folder_host,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=keypair_resource_policy,
            domain_name=domain_name,
            group_id=group_uuid,
            permission=VFolderHostPermission.CREATE,
        )

        # Check resource policy's max_vfolder_count
        if max_vfolder_count > 0:
            if ownership_type == "user":
                query = (
                    sa.select([sa.func.count()])
                    .select_from(vfolders)
                    .where(
                        (vfolders.c.user == user_uuid)
                        & (vfolders.c.status.not_in(HARD_DELETED_VFOLDER_STATUSES))
                    )
                )
            else:
                assert group_uuid is not None
                query = (
                    sa.select([sa.func.count()])
                    .select_from(vfolders)
                    .where(
                        (vfolders.c.group == group_uuid)
                        & (vfolders.c.status.not_in(HARD_DELETED_VFOLDER_STATUSES))
                    )
                )
            result = cast(int, await conn.scalar(query))
            if result >= max_vfolder_count:
                raise InvalidAPIParameters("You cannot create more vfolders.")

        # DEPRECATED: Limit vfolder size quota if it is larger than max_vfolder_size of the resource policy.
        # max_vfolder_size = resource_policy.get("max_vfolder_size", 0)
        # if max_vfolder_size > 0 and (
        #     params["quota"] is None or params["quota"] <= 0 or params["quota"] > max_vfolder_size
        # ):
        #     params["quota"] = max_vfolder_size

        # Prevent creation of vfolder with duplicated name on all hosts.
        extra_vf_conds = [
            (vfolders.c.name == params.name),
            (vfolders.c.status.not_in(HARD_DELETED_VFOLDER_STATUSES)),
        ]
        entries = await query_accessible_vfolders(
            conn,
            user_uuid,
            user_role=user_role,
            domain_name=domain_name,
            allowed_vfolder_types=allowed_vfolder_types,
            extra_vf_conds=(sa.and_(*extra_vf_conds)),
        )
        if len(entries) > 0:
            raise VFolderAlreadyExists(extra_data=params.name)
        try:
            folder_id = uuid.uuid4()
            vfid = VFolderID(quota_scope_id, folder_id)
            if not unmanaged_path:
                # Create the vfolder only when it is a managed one
                # TODO: Create the quota scope with an unlimited quota config if not exists
                #       The quota may be set later by the admin...
                # TODO: Introduce "default quota config" for users and projects (which cannot be
                #       modified by users)
                # async with root_ctx.storage_manager.request(
                #     folder_host,
                #     "POST",
                #     "quota-scope",
                #     json={
                #         "volume": root_ctx.storage_manager.split_host(folder_host)[1],
                #         "qsid": str(quota_scope_id),
                #         "options": None,
                #     },
                # ):
                #     pass
                options = {}
                if max_quota_scope_size and max_quota_scope_size > 0:
                    options["initial_max_size_for_quota_scope"] = max_quota_scope_size
                body_data: dict[str, Any] = {
                    "volume": root_ctx.storage_manager.get_proxy_and_volume(
                        folder_host, is_unmanaged(unmanaged_path)
                    )[1],
                    "vfid": str(vfid),
                    "options": options,
                }
                if vfolder_permission_mode is not None:
                    body_data["mode"] = vfolder_permission_mode
                async with root_ctx.storage_manager.request(
                    folder_host,
                    "POST",
                    "folder/create",
                    json=body_data,
                ):
                    pass
        except aiohttp.ClientResponseError as e:
            raise VFolderCreationFailed from e

        # By default model store VFolder should be considered as read only for every users but without the creator
        if group_type == ProjectType.MODEL_STORE:
            params.permission = VFolderPermission.READ_ONLY

        # TODO: include quota scope ID in the database
        # TODO: include quota scope ID in the API response
        insert_values = {
            "id": vfid.folder_id.hex,
            "name": params.name,
            "domain_name": domain_name,
            "quota_scope_id": str(quota_scope_id),
            "usage_mode": params.usage_mode,
            "permission": params.permission,
            "last_used": None,
            "host": folder_host,
            "creator": request["user"]["email"],
            "ownership_type": VFolderOwnershipType(ownership_type),
            "user": user_uuid if ownership_type == "user" else None,
            "group": group_uuid if ownership_type == "group" else None,
            "unmanaged_path": unmanaged_path,
            "cloneable": params.cloneable,
            "status": VFolderOperationStatus.READY,
        }
        resp = {
            "id": vfid.folder_id.hex,
            "name": params.name,
            "quota_scope_id": str(quota_scope_id),
            "host": folder_host,
            "usage_mode": params.usage_mode.value,
            "permission": params.permission.value,
            "max_size": 0,  # migrated to quota scopes, no longer valid
            "creator": request["user"]["email"],
            "ownership_type": ownership_type,
            "user": str(user_uuid) if ownership_type == "user" else None,
            "group": str(group_uuid) if ownership_type == "group" else None,
            "cloneable": params.cloneable,
            "status": VFolderOperationStatus.READY,
        }
        if unmanaged_path:
            resp["unmanaged_path"] = unmanaged_path
        try:
            query = sa.insert(vfolders, insert_values)
            result = await conn.execute(query)

            # Here we grant creator the permission to alter VFolder contents
            if group_type == ProjectType.MODEL_STORE:
                query = sa.insert(vfolder_permissions).values({
                    "user": request["user"]["uuid"],
                    "vfolder": vfid.folder_id.hex,
                    "permission": VFolderPermission.OWNER_PERM,
                })
                await conn.execute(query)
        except sa.exc.DataError:
            raise InvalidAPIParameters
        assert result.rowcount == 1
    return web.json_response(resp, status=201)


@auth_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("all", default=False): t.ToBool,
        tx.AliasedKey(["group_id", "groupId"], default=None): tx.UUID | t.String | t.Null,
        tx.AliasedKey(["owner_user_email", "ownerUserEmail"], default=None): t.Email | t.Null,
    }),
)
async def list_folders(request: web.Request, params: Any) -> web.Response:
    resp = []
    root_ctx: RootContext = request.app["_root.context"]
    domain_name = request["user"]["domain_name"]
    log.info(
        "VFOLDER.LIST (email:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    entries: List[Mapping[str, Any]] | Sequence[Mapping[str, Any]]
    owner_user_uuid, owner_user_role = await get_user_scopes(request, params)
    async with root_ctx.db.begin_readonly() as conn:
        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        if params["all"]:
            raise InvalidAPIParameters("Deprecated use of 'all' option")
        else:
            extra_vf_conds = None
            if params["group_id"] is not None:
                # Note: user folders should be returned even when group_id is specified.
                extra_vf_conds = (vfolders.c.group == params["group_id"]) | (
                    vfolders.c.user.isnot(None)
                )
            entries = await query_accessible_vfolders(
                conn,
                owner_user_uuid,
                user_role=owner_user_role,
                domain_name=domain_name,
                allowed_vfolder_types=allowed_vfolder_types,
                extra_vf_conds=extra_vf_conds,
            )
        for entry in entries:
            resp.append({
                "name": entry["name"],
                "id": entry["id"].hex,
                "quota_scope_id": str(entry["quota_scope_id"]),
                "host": entry["host"],
                "status": entry["status"],
                "usage_mode": entry["usage_mode"].value,
                "created_at": str(entry["created_at"]),
                "is_owner": entry["is_owner"],
                "permission": entry["permission"].value,
                "user": str(entry["user"]) if entry["user"] else None,
                "group": str(entry["group"]) if entry["group"] else None,
                "creator": entry["creator"],
                "user_email": entry["user_email"],
                "group_name": entry["group_name"],
                "ownership_type": entry["ownership_type"].value,
                "type": entry["ownership_type"].value,  # legacy
                "cloneable": entry["cloneable"],
                "max_files": entry["max_files"],
                "max_size": entry["max_size"],
                "cur_size": entry["cur_size"],
            })
    return web.json_response(resp, status=200)


class ExposedVolumeInfoField(StrEnum):
    percentage = "percentage"
    used_bytes = "used_bytes"
    capacity_bytes = "capacity_bytes"


async def fetch_exposed_volume_fields(
    storage_manager: StorageSessionManager,
    redis_connection: RedisConnectionInfo,
    proxy_name: str,
    volume_name: str,
) -> Dict[str, int | float]:
    volume_usage = {}

    show_percentage = ExposedVolumeInfoField.percentage in storage_manager._exposed_volume_info
    show_used = ExposedVolumeInfoField.used_bytes in storage_manager._exposed_volume_info
    show_total = ExposedVolumeInfoField.capacity_bytes in storage_manager._exposed_volume_info

    if show_percentage or show_used or show_total:
        volume_usage_cache = await redis_helper.execute(
            redis_connection,
            lambda r: r.get(f"volume.usage.{proxy_name}.{volume_name}"),
        )

        if volume_usage_cache:
            volume_usage = msgpack.unpackb(volume_usage_cache)
        else:
            async with storage_manager.request(
                proxy_name,
                "GET",
                "folder/fs-usage",
                json={
                    "volume": volume_name,
                },
            ) as (_, storage_resp):
                storage_reply = await storage_resp.json()
                storage_used_bytes = storage_reply[ExposedVolumeInfoField.used_bytes]
                storage_capacity_bytes = storage_reply[ExposedVolumeInfoField.capacity_bytes]

                if show_used:
                    volume_usage["used"] = storage_used_bytes

                if show_total:
                    volume_usage["total"] = storage_capacity_bytes

                if show_percentage:
                    try:
                        volume_usage["percentage"] = (
                            storage_used_bytes / storage_capacity_bytes
                        ) * 100
                    except ZeroDivisionError:
                        volume_usage["percentage"] = 0

            await redis_helper.execute(
                redis_connection,
                lambda r: r.set(
                    f"volume.usage.{proxy_name}.{volume_name}",
                    msgpack.packb(volume_usage),
                    ex=60,
                ),
            )

    return volume_usage


@auth_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        tx.AliasedKey(["group_id", "groupId"], default=None): tx.UUID | t.String | t.Null,
    }),
)
async def list_hosts(request: web.Request, params: Any) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.LIST_HOSTS (emai:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    domain_name = request["user"]["domain_name"]
    group_id = params["group_id"]
    domain_admin = request["user"]["role"] == UserRole.ADMIN
    resource_policy = request["keypair"]["resource_policy"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    async with root_ctx.db.begin() as conn:
        allowed_hosts = VFolderHostPermissionMap()
        if "user" in allowed_vfolder_types:
            allowed_hosts_by_user = await get_allowed_vfolder_hosts_by_user(
                conn, resource_policy, domain_name, request["user"]["uuid"], group_id
            )
            allowed_hosts = allowed_hosts | allowed_hosts_by_user
        if "group" in allowed_vfolder_types:
            allowed_hosts_by_group = await get_allowed_vfolder_hosts_by_group(
                conn, resource_policy, domain_name, group_id, domain_admin=domain_admin
            )
            allowed_hosts = allowed_hosts | allowed_hosts_by_group
    all_volumes = await root_ctx.storage_manager.get_all_volumes()
    all_hosts = {f"{proxy_name}:{volume_data['name']}" for proxy_name, volume_data in all_volumes}
    allowed_hosts = VFolderHostPermissionMap({
        host: perms for host, perms in allowed_hosts.items() if host in all_hosts
    })
    default_host = await root_ctx.shared_config.get_raw("volumes/default_host")
    if default_host not in allowed_hosts:
        default_host = None

    volumes = [
        (proxy_name, volume_data)
        for proxy_name, volume_data in all_volumes
        if f"{proxy_name}:{volume_data['name']}" in allowed_hosts
    ]

    fetch_exposed_volume_fields_tasks = [
        fetch_exposed_volume_fields(
            storage_manager=root_ctx.storage_manager,
            redis_connection=root_ctx.redis_stat,
            proxy_name=proxy_name,
            volume_name=volume_data["name"],
        )
        for proxy_name, volume_data in volumes
    ]
    get_sftp_scaling_groups_tasks = [
        root_ctx.storage_manager.get_sftp_scaling_groups(proxy_name)
        for proxy_name, volume_data in volumes
    ]

    fetch_exposed_volume_fields_results, get_sftp_scaling_groups_results = await asyncio.gather(
        asyncio.gather(*fetch_exposed_volume_fields_tasks),
        asyncio.gather(*get_sftp_scaling_groups_tasks),
    )

    volume_info = {
        f"{proxy_name}:{volume_data['name']}": {
            "backend": volume_data["backend"],
            "capabilities": volume_data["capabilities"],
            "usage": usage,
            "sftp_scaling_groups": sftp_scaling_groups,
        }
        for (proxy_name, volume_data), usage, sftp_scaling_groups in zip(
            volumes, fetch_exposed_volume_fields_results, get_sftp_scaling_groups_results
        )
    }
    resp = {
        "default": default_host,
        "allowed": sorted(allowed_hosts),
        "volume_info": volume_info,
    }
    return web.json_response(resp, status=200)


@superadmin_required
@server_status_required(READ_ALLOWED)
async def list_all_hosts(request: web.Request) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.LIST_ALL_HOSTS (email:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    all_volumes = await root_ctx.storage_manager.get_all_volumes()
    all_hosts = {f"{proxy_name}:{volume_data['name']}" for proxy_name, volume_data in all_volumes}
    default_host = await root_ctx.shared_config.get_raw("volumes/default_host")
    if default_host not in all_hosts:
        default_host = None
    resp = {
        "default": default_host,
        "allowed": sorted(all_hosts),
    }
    return web.json_response(resp, status=200)


@superadmin_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("folder_host"): t.String,
    })
)
async def get_volume_perf_metric(request: web.Request, params: Any) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.VOLUME_PERF_METRIC (email:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(params["folder_host"])
    async with root_ctx.storage_manager.request(
        proxy_name,
        "GET",
        "volume/performance-metric",
        json={
            "volume": volume_name,
        },
    ) as (_, storage_resp):
        storage_reply = await storage_resp.json()
    return web.json_response(storage_reply, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
async def list_allowed_types(request: web.Request) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.LIST_ALLOWED_TYPES (email:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    return web.json_response(allowed_vfolder_types, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.READABLE)
@with_vfolder_status_checked(VFolderStatusSet.READABLE)
async def get_info(request: web.Request, row: VFolderRow) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    resp: Dict[str, Any] = {}
    log.info(
        "VFOLDER.GETINFO (email:{}, ak:{}, vf:{} (resolved-from:{!r}))",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
    )
    if row["permission"] is None:
        is_owner = True
        permission = VFolderPermission.OWNER_PERM
    else:
        is_owner = row["is_owner"]
        permission = row["permission"]
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        row["host"], is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "GET",
        "folder/usage",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID.from_row(row)),
        },
    ) as (_, storage_resp):
        usage = await storage_resp.json()
    resp = {
        "name": row["name"],
        "id": row["id"].hex,
        "host": row["host"],
        "quota_scope_id": str(row["quota_scope_id"]),
        "status": row["status"],
        "numFiles": usage["file_count"],  # legacy
        "num_files": usage["file_count"],
        "used_bytes": usage["used_bytes"],  # added in v20.09
        "created": str(row["created_at"]),  # legacy
        "created_at": str(row["created_at"]),
        "last_used": str(row["created_at"]),
        "user": str(row["user"]) if row["user"] else None,
        "group": str(row["group"]) if row["group"] else None,
        "type": "user" if row["user"] is not None else "group",
        "is_owner": is_owner,
        "permission": permission,
        "usage_mode": row["usage_mode"],
        "cloneable": row["cloneable"],
        "max_size": row["max_size"],
        "cur_size": row["cur_size"],
    }
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("folder_host"): t.String,
        t.Key("id"): tx.UUID,
    })
)
async def get_quota(request: web.Request, params: Any) -> web.Response:
    vfolder_row = (
        await resolve_vfolder_rows(request, VFolderPermissionSetAlias.READABLE, params["id"])
    )[0]
    await check_vfolder_status(vfolder_row, VFolderStatusSet.READABLE)
    root_ctx: RootContext = request.app["_root.context"]
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        params["folder_host"], is_unmanaged(vfolder_row["unmanaged_path"])
    )
    log.info(
        "VFOLDER.GET_QUOTA (email:{}, volume_name:{}, vf:{})",
        request["user"]["email"],
        volume_name,
        params["id"],
    )

    # Permission check for the requested vfolder.
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    if user_role == UserRole.SUPERADMIN:
        pass
    else:
        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        async with root_ctx.db.begin_readonly() as conn:
            extra_vf_conds = [vfolders.c.id == params["id"]]
            entries = await query_accessible_vfolders(
                conn,
                user_uuid,
                user_role=user_role,
                domain_name=domain_name,
                allowed_vfolder_types=allowed_vfolder_types,
                extra_vf_conds=(sa.and_(*extra_vf_conds)),
            )
        if len(entries) == 0:
            raise VFolderNotFound(extra_data=params["id"])

    async with root_ctx.storage_manager.request(
        proxy_name,
        "GET",
        "volume/quota",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID.from_row(vfolder_row)),
        },
    ) as (_, storage_resp):
        storage_reply = await storage_resp.json()
    return web.json_response(storage_reply, status=200)


@auth_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("folder_host"): t.String,
        t.Key("id"): tx.UUID,
        t.Key("input"): t.Mapping(t.String, t.Any),
    }),
)
async def update_quota(request: web.Request, params: Any) -> web.Response:
    vfolder_row = (
        await resolve_vfolder_rows(request, VFolderPermissionSetAlias.READABLE, params["id"])
    )[0]
    await check_vfolder_status(vfolder_row, VFolderStatusSet.READABLE)
    root_ctx: RootContext = request.app["_root.context"]
    folder_host = params["folder_host"]
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        folder_host, is_unmanaged(vfolder_row["unmanaged_path"])
    )
    quota = int(params["input"]["size_bytes"])
    log.info(
        "VFOLDER.UPDATE_QUOTA (email:{}, volume_name:{}, quota:{}, vf:{})",
        request["user"]["email"],
        volume_name,
        quota,
        params["id"],
    )

    # Permission check for the requested vfolder.
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    resource_policy = request["keypair"]["resource_policy"]

    if user_role == UserRole.SUPERADMIN:
        pass
    else:
        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        async with root_ctx.db.begin_readonly() as conn:
            await ensure_host_permission_allowed(
                conn,
                folder_host,
                allowed_vfolder_types=allowed_vfolder_types,
                user_uuid=user_uuid,
                resource_policy=resource_policy,
                domain_name=domain_name,
                permission=VFolderHostPermission.MODIFY,
            )
            extra_vf_conds = [vfolders.c.id == params["id"]]
            entries = await query_accessible_vfolders(
                conn,
                user_uuid,
                user_role=user_role,
                domain_name=domain_name,
                allowed_vfolder_types=allowed_vfolder_types,
                extra_vf_conds=(sa.and_(*extra_vf_conds)),
            )
        if len(entries) == 0:
            raise VFolderNotFound(extra_data=params["id"])

    # Limit vfolder size quota if it is larger than max_quota_scope_size of the resource policy.
    max_quota_scope_size = resource_policy.get("max_quota_scope_size", 0)
    if max_quota_scope_size > 0 and (quota <= 0 or quota > max_quota_scope_size):
        quota = max_quota_scope_size

    async with root_ctx.storage_manager.request(
        proxy_name,
        "PATCH",
        "volume/quota",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID.from_row(vfolder_row)),
            "size_bytes": quota,
        },
    ):
        pass

    # Update the quota for the vfolder in DB.
    async with root_ctx.db.begin() as conn:
        query = (
            sa.update(vfolders)
            .values(max_size=math.ceil(quota / 2**20))  # in Mbytes
            .where(vfolders.c.id == params["id"])
        )
        result = await conn.execute(query)
        assert result.rowcount == 1

    return web.json_response({"size_bytes": quota}, status=200)


@superadmin_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("folder_host"): t.String,
        t.Key("id"): tx.UUID,
    })
)
async def get_usage(request: web.Request, params: Any) -> web.Response:
    vfolder_row = (
        await resolve_vfolder_rows(request, VFolderPermissionSetAlias.READABLE, params["id"])
    )[0]
    await check_vfolder_status(vfolder_row, VFolderStatusSet.READABLE)
    root_ctx: RootContext = request.app["_root.context"]
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        params["folder_host"], is_unmanaged(vfolder_row["unmanaged_path"])
    )
    log.info(
        "VFOLDER.GET_USAGE (email:{}, volume_name:{}, vf:{})",
        request["user"]["email"],
        volume_name,
        params["id"],
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "GET",
        "folder/usage",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(vfolder_row["quota_scope_id"], params["id"])),
        },
    ) as (_, storage_resp):
        usage = await storage_resp.json()
    return web.json_response(usage, status=200)


@superadmin_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("folder_host"): t.String,
        t.Key("id"): tx.UUID,
    })
)
async def get_used_bytes(request: web.Request, params: Any) -> web.Response:
    vfolder_row = (
        await resolve_vfolder_rows(request, VFolderPermissionSetAlias.READABLE, params["id"])
    )[0]
    await check_vfolder_status(vfolder_row, VFolderStatusSet.READABLE)
    root_ctx: RootContext = request.app["_root.context"]
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        params["folder_host"], is_unmanaged(vfolder_row["unmanaged_path"])
    )
    log.info("VFOLDER.GET_USED_BYTES (volume_name:{}, vf:{})", volume_name, params["id"])
    async with root_ctx.storage_manager.request(
        proxy_name,
        "GET",
        "folder/used-bytes",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(vfolder_row["quota_scope_id"], params["id"])),
        },
    ) as (_, storage_resp):
        usage = await storage_resp.json()
    return web.json_response(usage, status=200)


class RenameRequestModel(BaseModel):
    new_name: tv.VFolderName = Field(
        description="Name of the vfolder",
    )


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(RenameRequestModel)  # type: ignore  # FIXME: remove after vfolder refactoring
@with_vfolder_rows_resolved(VFolderPermission.OWNER_PERM)
@with_vfolder_status_checked(VFolderStatusSet.READABLE)
async def rename_vfolder(
    request: web.Request,
    row: VFolderRow,
    params: RenameRequestModel,
) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    domain_name = request["user"]["domain_name"]
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    resource_policy = request["keypair"]["resource_policy"]
    old_name = row["name"]
    new_name = params.new_name
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    log.info(
        "VFOLDER.RENAME (email:{}, ak:{}, vf:{} (resolved-from:{!r}), new-name:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        new_name,
    )
    async with root_ctx.db.begin() as conn:
        entries = await query_accessible_vfolders(
            conn,
            user_uuid,
            user_role=user_role,
            domain_name=domain_name,
            allowed_vfolder_types=allowed_vfolder_types,
        )
        for entry in entries:
            if entry["name"] == new_name:
                raise InvalidAPIParameters(
                    "One of your accessible vfolders already has the name you requested."
                )
        for entry in entries:
            if entry["name"] == old_name:
                if not entry["is_owner"]:
                    raise InvalidAPIParameters(
                        "Cannot change the name of a vfolder that is not owned by myself."
                    )
                await ensure_host_permission_allowed(
                    conn,
                    entry["host"],
                    allowed_vfolder_types=allowed_vfolder_types,
                    user_uuid=user_uuid,
                    resource_policy=resource_policy,
                    domain_name=domain_name,
                    permission=VFolderHostPermission.MODIFY,
                )
                query = (
                    sa.update(vfolders).values(name=new_name).where(vfolders.c.id == entry["id"])
                )
                await conn.execute(query)
                break
    return web.Response(status=201)


@auth_required
@server_status_required(ALL_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermission.OWNER_PERM)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("cloneable", default=None): t.Bool | t.Null,
        t.Key("permission", default=None): tx.Enum(VFolderPermission) | t.Null,
    })
)
async def update_vfolder_options(
    request: web.Request, params: Any, row: VFolderRow
) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    resource_policy = request["keypair"]["resource_policy"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    log.info(
        "VFOLDER.UPDATE_OPTIONS (email:{}, ak:{}, vf:{} (resolved-from:{!r}))",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
    )
    async with root_ctx.db.begin_readonly() as conn:
        query = sa.select([vfolders.c.host]).select_from(vfolders).where(vfolders.c.id == row["id"])
        folder_host = await conn.scalar(query)
        await ensure_host_permission_allowed(
            conn,
            folder_host,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.MODIFY,
        )

    updated_fields = {}
    if params["cloneable"] is not None and params["cloneable"] != row["cloneable"]:
        updated_fields["cloneable"] = params["cloneable"]
    if params["permission"] is not None and params["permission"] != row["permission"]:
        updated_fields["permission"] = params["permission"]
    if not row["is_owner"]:
        raise InvalidAPIParameters(
            "Cannot change the options of a vfolder that is not owned by myself."
        )

    if len(updated_fields) > 0:
        async with root_ctx.db.begin() as conn:
            query = sa.update(vfolders).values(**updated_fields).where(vfolders.c.id == row["id"])
            await conn.execute(query)
    return web.Response(status=201)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.WRITABLE)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("path"): t.String | t.List(t.String),
        t.Key("parents", default=True): t.ToBool,
        t.Key("exist_ok", default=False): t.ToBool,
    })
)
async def mkdir(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    if isinstance(params["path"], list) and len(params["path"]) > 50:
        raise InvalidAPIParameters("Too many directories specified.")
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.MKDIR (email:{}, ak:{}, vf:{} (resolved-from:{!r}), paths:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["path"],
    )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        row["host"], is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/mkdir",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "relpath": params["path"],
            "parents": params["parents"],
            "exist_ok": params["exist_ok"],
        },
    ) as (_, storage_resp):
        storage_reply = await storage_resp.json()
        match storage_resp.status:
            case 200 | 207:
                return web.json_response(storage_reply, status=storage_resp.status)
            # 422 will be wrapped as VFolderOperationFailed by storage_manager
            case _:
                raise RuntimeError("should not reach here")


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.READABLE)
@with_vfolder_status_checked(VFolderStatusSet.READABLE)
@check_api_params(
    t.Dict({
        tx.AliasedKey(["path", "file"]): t.String,
        t.Key("archive", default=False): t.ToBool,
    })
)
async def create_download_session(
    request: web.Request, params: Any, row: VFolderRow
) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.CREATE_DOWNLOAD_SESSION(email:{}, ak:{}, vf:{} (resolved-from:{!r}), path:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["path"],
    )
    unmanaged_path = row["unmanaged_path"]
    user_uuid = request["user"]["uuid"]
    folder_host = row["host"]
    domain_name = request["user"]["domain_name"]
    resource_policy = request["keypair"]["resource_policy"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    async with root_ctx.db.begin_readonly() as conn:
        await ensure_host_permission_allowed(
            conn,
            folder_host,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.DOWNLOAD_FILE,
        )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        folder_host, is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/download",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "relpath": params["path"],
            "archive": params["archive"],
            "unmanaged_path": unmanaged_path if unmanaged_path else None,
        },
    ) as (client_api_url, storage_resp):
        storage_reply = await storage_resp.json()
        resp = {
            "token": storage_reply["token"],
            "url": str(client_api_url / "download"),
        }
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.WRITABLE)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("path"): t.String,
        t.Key("size"): t.ToInt,
    })
)
async def create_upload_session(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.CREATE_UPLOAD_SESSION (email:{}, ak:{}, vf:{} (resolved-from:{!r}), path:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["path"],
    )
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    folder_host = row["host"]
    resource_policy = request["keypair"]["resource_policy"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    async with root_ctx.db.begin_readonly() as conn:
        await ensure_host_permission_allowed(
            conn,
            folder_host,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.UPLOAD_FILE,
        )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        folder_host, is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/upload",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "relpath": params["path"],
            "size": params["size"],
        },
    ) as (client_api_url, storage_resp):
        storage_reply = await storage_resp.json()
        resp = {
            "token": storage_reply["token"],
            "url": str(client_api_url / "upload"),
        }
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.WRITABLE)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("target_path"): t.String,
        t.Key("new_name"): t.String,
        t.Key("is_dir", default=False): t.ToBool,  # ignored since 22.03
    })
)
async def rename_file(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    folder_host = row["host"]
    resource_policy = request["keypair"]["resource_policy"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    async with root_ctx.db.begin_readonly() as conn:
        await ensure_host_permission_allowed(
            conn,
            folder_host,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.MODIFY,
        )
    log.info(
        "VFOLDER.RENAME_FILE (email:{}, ak:{}, vf:{} (resolved-from:{!r}), target_path:{}, new_name:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["target_path"],
        params["new_name"],
    )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        folder_host, is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/rename",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "relpath": params["target_path"],
            "new_name": params["new_name"],
        },
    ):
        pass
    return web.json_response({}, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.WRITABLE)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("src"): t.String,
        t.Key("dst"): t.String,
    })
)
async def move_file(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.MOVE_FILE (email:{}, ak:{}, vf:{} (resolved-from:{!r}), src:{}, dst:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["src"],
        params["dst"],
    )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        row["host"], is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/move",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "src_relpath": params["src"],
            "dst_relpath": params["dst"],
        },
    ):
        pass
    return web.json_response({}, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.WRITABLE)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("files"): t.List(t.String),
        t.Key("recursive", default=False): t.ToBool,
    })
)
async def delete_files(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    recursive = params["recursive"]
    log.info(
        "VFOLDER.DELETE_FILES (email:{}, ak:{}, vf:{} (resolved-from:{!r}), path:{}, recursive:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["files"],
        recursive,
    )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        row["host"], is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/delete",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "relpaths": params["files"],
            "recursive": recursive,
        },
    ):
        pass
    return web.json_response({}, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.READABLE)
@with_vfolder_status_checked(VFolderStatusSet.READABLE)
@check_api_params(
    t.Dict({
        t.Key("path", default=""): t.String(allow_blank=True),
    })
)
async def list_files(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    # we can skip check_vfolder_status() guard here since the status is already verified by
    # vfolder_permission_required() decorator
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.LIST_FILES (email:{}, ak:{}, vf:{} (resolved-from:{!r}), path:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["path"],
    )
    proxy_name, volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        row["host"], is_unmanaged(row["unmanaged_path"])
    )
    async with root_ctx.storage_manager.request(
        proxy_name,
        "POST",
        "folder/file/list",
        json={
            "volume": volume_name,
            "vfid": str(VFolderID(row["quota_scope_id"], row["id"])),
            "relpath": params["path"],
        },
    ) as (_, storage_resp):
        result = await storage_resp.json()
        resp = {
            "items": [
                {
                    "name": item["name"],
                    "type": item["type"],
                    "size": item["stat"]["size"],  # humanize?
                    "mode": oct(item["stat"]["mode"])[2:][-3:],
                    "created": item["stat"]["created"],
                    "modified": item["stat"]["modified"],
                }
                for item in result["items"]
            ],
            "files": json.dumps([  # for legacy (to be removed in 21.03)
                {
                    "filename": item["name"],
                    "size": item["stat"]["size"],
                    "mode": stat.filemode(item["stat"]["mode"]),
                    "ctime": datetime.fromisoformat(item["stat"]["created"]).timestamp(),
                    "atime": 0,
                    "mtime": datetime.fromisoformat(item["stat"]["modified"]).timestamp(),
                }
                for item in result["items"]
            ]),
        }
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(READ_ALLOWED)
async def list_sent_invitations(request: web.Request) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.LIST_SENT_INVITATIONS (email:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    async with root_ctx.db.begin() as conn:
        j = sa.join(vfolders, vfolder_invitations, vfolders.c.id == vfolder_invitations.c.vfolder)
        query = (
            sa.select([vfolder_invitations, vfolders.c.name])
            .select_from(j)
            .where(
                (vfolder_invitations.c.inviter == request["user"]["email"])
                & (vfolder_invitations.c.state == VFolderInvitationState.PENDING),
            )
        )
        result = await conn.execute(query)
        invitations = result.fetchall()
    invs_info = []
    for inv in invitations:
        invs_info.append({
            "id": str(inv.id),
            "inviter": inv.inviter,
            "invitee": inv.invitee,
            "perm": inv.permission,
            "state": inv.state.value,
            "created_at": str(inv.created_at),
            "modified_at": str(inv.modified_at),
            "vfolder_id": str(inv.vfolder),
            "vfolder_name": inv.name,
        })
    resp = {"invitations": invs_info}
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        tx.AliasedKey(["perm", "permission"]): VFolderPermissionValidator,
    }),
)
async def update_invitation(request: web.Request, params: Any) -> web.Response:
    """
    Update sent invitation's permission. Other fields are not allowed to be updated.
    """
    root_ctx: RootContext = request.app["_root.context"]
    inv_id = request.match_info["inv_id"]
    perm = params["perm"]
    log.info(
        "VFOLDER.UPDATE_INVITATION (email:{}, ak:{}, inv:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        inv_id,
    )
    async with root_ctx.db.begin() as conn:
        query = (
            sa.update(vfolder_invitations)
            .values(permission=perm)
            .where(
                (vfolder_invitations.c.id == inv_id)
                & (vfolder_invitations.c.inviter == request["user"]["email"])
                & (vfolder_invitations.c.state == VFolderInvitationState.PENDING),
            )
        )
        await conn.execute(query)
    resp = {"msg": f"vfolder invitation updated: {inv_id}."}
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(ALL_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermission.OWNER_PERM)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        tx.AliasedKey(["perm", "permission"], default="rw"): VFolderPermissionValidator,
        tx.AliasedKey(["emails", "user_ids", "userIDs"]): t.List(t.String),
    }),
)
async def invite(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    folder_name = row["name"]
    access_key = request["keypair"]["access_key"]
    user_uuid = request["user"]["uuid"]
    perm = params["perm"]
    invitee_emails = params["emails"]
    log.info(
        "VFOLDER.INVITE (email:{}, ak:{}, vf:{} (resolved-from:{!r}), inv.users:{})",
        request["user"]["email"],
        access_key,
        row["id"],
        request.match_info["name"],
        ",".join(invitee_emails),
    )
    domain_name = request["user"]["domain_name"]
    resource_policy = request["keypair"]["resource_policy"]
    if folder_name.startswith("."):
        raise GenericForbidden("Cannot share private dot-prefixed vfolders.")

    rows = await resolve_vfolder_rows(request, VFolderPermission.OWNER_PERM, folder_name)
    for row in rows:
        try:
            await check_vfolder_status(row, VFolderStatusSet.READABLE)
            break
        except VFolderFilterStatusFailed:
            continue
    else:
        raise VFolderFilterStatusFailed
    source_vfolder = row

    async with root_ctx.db.begin_readonly() as conn:
        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        await ensure_host_permission_allowed(
            conn,
            source_vfolder["host"],
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.INVITE_OTHERS,
        )
    async with root_ctx.db.begin() as conn:
        # Get invited user's keypairs except vfolder owner.
        # Add filter on keypair in `ACTIVE` status
        query = (
            sa.select([keypairs.c.user_id, keypairs.c.user])
            .select_from(keypairs)
            .where(
                (keypairs.c.user_id.in_(invitee_emails))
                & (keypairs.c.user_id != request["user"]["email"])
                & (keypairs.c.is_active.is_(True))
            )
        )
        try:
            result = await conn.execute(query)
        except sa.exc.DataError:
            raise InvalidAPIParameters
        kps = result.fetchall()
        if len(kps) < 1:
            raise ObjectNotFound(object_name="vfolder invitation")

        # Prevent inviting user who already share the target folder.
        invitee_uuids = [kp.user for kp in kps]
        j = sa.join(vfolders, vfolder_permissions, vfolders.c.id == vfolder_permissions.c.vfolder)
        query = (
            sa.select([sa.func.count()])
            .select_from(j)
            .where(
                (vfolders.c.user.in_(invitee_uuids) | vfolder_permissions.c.user.in_(invitee_uuids))
                & (vfolders.c.id == source_vfolder["id"]),
            )
        )
        result = await conn.execute(query)
        if result.scalar() > 0:
            raise VFolderAlreadyExists(
                extra_msg="Invitation to this VFolder already sent out to target user"
            )

        # Create invitation.
        invitees = [kp.user_id for kp in kps]
        invited_ids = []
        for invitee in set(invitees):
            inviter = request["user"]["id"]
            # Do not create invitation if already exists.
            query = (
                sa.select([sa.func.count()])
                .select_from(vfolder_invitations)
                .where(
                    (vfolder_invitations.c.inviter == inviter)
                    & (vfolder_invitations.c.invitee == invitee)
                    & (vfolder_invitations.c.vfolder == source_vfolder["id"])
                    & (vfolder_invitations.c.state == VFolderInvitationState.PENDING),
                )
            )
            result = await conn.execute(query)
            if result.scalar() > 0:
                continue

            # TODO: insert multiple values with one query.
            #       insert().values([{}, {}, ...]) does not work:
            #       sqlalchemy.exc.CompileError: The 'default' dialect with current
            #       database version settings does not support in-place multirow
            #       inserts.
            query = sa.insert(
                vfolder_invitations,
                {
                    "id": uuid.uuid4().hex,
                    "permission": perm,
                    "vfolder": source_vfolder["id"],
                    "inviter": inviter,
                    "invitee": invitee,
                    "state": VFolderInvitationState.PENDING,
                },
            )
            try:
                await conn.execute(query)
                invited_ids.append(invitee)
            except sa.exc.DataError:
                pass
    resp = {"invited_ids": invited_ids}
    return web.json_response(resp, status=201)


@auth_required
@server_status_required(READ_ALLOWED)
async def invitations(request: web.Request) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.INVITATIONS (email:{}, ak:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
    )
    async with root_ctx.db.begin() as conn:
        j = sa.join(vfolders, vfolder_invitations, vfolders.c.id == vfolder_invitations.c.vfolder)
        query = (
            sa.select([vfolder_invitations, vfolders.c.name])
            .select_from(j)
            .where(
                (vfolder_invitations.c.invitee == request["user"]["id"])
                & (vfolder_invitations.c.state == VFolderInvitationState.PENDING),
            )
        )
        result = await conn.execute(query)
        invitations = result.fetchall()
    invs_info = []
    for inv in invitations:
        invs_info.append({
            "id": str(inv.id),
            "inviter": inv.inviter,
            "invitee": inv.invitee,
            "perm": inv.permission,
            "state": inv.state,
            "created_at": str(inv.created_at),
            "modified_at": str(inv.modified_at),
            "vfolder_id": str(inv.vfolder),
            "vfolder_name": inv.name,
        })
    resp = {"invitations": invs_info}
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("inv_id"): t.String,
    }),
)
async def accept_invitation(request: web.Request, params: Any) -> web.Response:
    """Accept invitation by invitee.

    * `inv_ak` parameter is removed from 19.06 since virtual folder's ownership is
    moved from keypair to a user or a group.

    :param inv_id: ID of vfolder_invitations row.
    """
    root_ctx: RootContext = request.app["_root.context"]
    user_uuid = request["user"]["uuid"]
    inv_id = params["inv_id"]
    log.info(
        "VFOLDER.ACCEPT_INVITATION (email:{}, ak:{}, inv:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        inv_id,
    )
    async with root_ctx.db.begin() as conn:
        # Get invitation.
        query = (
            sa.select([vfolder_invitations])
            .select_from(vfolder_invitations)
            .where(
                (vfolder_invitations.c.id == inv_id)
                & (vfolder_invitations.c.state == VFolderInvitationState.PENDING),
            )
        )
        result = await conn.execute(query)
        invitation = result.first()
        if invitation is None:
            raise ObjectNotFound(object_name="vfolder invitation")

        # Get target virtual folder.
        query = (
            sa.select([vfolders.c.name])
            .select_from(vfolders)
            .where(vfolders.c.id == invitation.vfolder)
        )
        result = await conn.execute(query)
        target_vfolder = result.first()
        if target_vfolder is None:
            raise VFolderNotFound

        # Prevent accepting vfolder with duplicated name.
        j = sa.join(
            vfolders,
            vfolder_permissions,
            vfolders.c.id == vfolder_permissions.c.vfolder,
            isouter=True,
        )
        query = (
            sa.select([sa.func.count()])
            .select_from(j)
            .where(
                ((vfolders.c.user == user_uuid) | (vfolder_permissions.c.user == user_uuid))
                & (vfolders.c.name == target_vfolder.name)
                & (vfolders.c.status.not_in(vfolder_status_map[VFolderStatusSet.INACCESSIBLE])),
            )
        )
        result = await conn.execute(query)
        if result.scalar() > 0:
            raise VFolderAlreadyExists

        # Create permission relation between the vfolder and the invitee.
        query = sa.insert(
            vfolder_permissions,
            {
                "permission": VFolderPermission(invitation.permission),
                "vfolder": invitation.vfolder,
                "user": user_uuid,
            },
        )
        await conn.execute(query)

        # Clear used invitation.
        query = (
            sa.update(vfolder_invitations)
            .where(vfolder_invitations.c.id == inv_id)
            .values(state=VFolderInvitationState.ACCEPTED)
        )
        await conn.execute(query)
    return web.json_response({})


@auth_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("inv_id"): t.String,
    })
)
async def delete_invitation(request: web.Request, params: Any) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]
    request_email = request["user"]["email"]
    inv_id = params["inv_id"]
    log.info(
        "VFOLDER.DELETE_INVITATION (email:{}, ak:{}, inv:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        inv_id,
    )
    try:
        async with root_ctx.db.begin() as conn:
            query = (
                sa.select([
                    vfolder_invitations.c.inviter,
                    vfolder_invitations.c.invitee,
                ])
                .select_from(vfolder_invitations)
                .where(
                    (vfolder_invitations.c.id == inv_id)
                    & (vfolder_invitations.c.state == VFolderInvitationState.PENDING),
                )
            )
            result = await conn.execute(query)
            row = result.first()
            if row is None:
                raise ObjectNotFound(object_name="vfolder invitation")
            if request_email == row.inviter:
                state = VFolderInvitationState.CANCELED
            elif request_email == row.invitee:
                state = VFolderInvitationState.REJECTED
            else:
                raise GenericForbidden("Cannot change other user's invitaiton")
            query = (
                sa.update(vfolder_invitations)
                .values(state=state)
                .where(vfolder_invitations.c.id == inv_id)
            )
            await conn.execute(query)
    except sa.exc.IntegrityError as e:
        raise InternalServerError(f"integrity error: {e}")
    except (asyncio.CancelledError, asyncio.TimeoutError):
        raise
    except Exception as e:
        raise InternalServerError(f"unexpected error: {e}")
    return web.json_response({})


@admin_required
@server_status_required(ALL_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermission.READ_ONLY)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("permission", default="rw"): VFolderPermissionValidator,
        t.Key("emails"): t.List(t.String),
    }),
)
async def share(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    """
    Share a group folder to users with overriding permission.

    This will create vfolder_permission(s) relation directly without
    creating invitation(s). Only group-type vfolders are allowed to
    be shared directly.
    """
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.SHARE (email:{}, ak:{}, vf:{} (resolved-from:{!r}), perm:{}, users:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        params["permission"],
        ",".join(params["emails"]),
    )
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    resource_policy = request["keypair"]["resource_policy"]
    if row["ownership_type"] != VFolderOwnershipType.GROUP:
        raise VFolderNotFound("Only project folders are directly sharable.")
    async with root_ctx.db.begin() as conn:
        from ..models import association_groups_users as agus

        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        await ensure_host_permission_allowed(
            conn,
            row["host"],
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.SET_USER_PERM,
        )

        # Convert users' emails to uuids and check if user belong to the group of vfolder.
        j = users.join(agus, users.c.uuid == agus.c.user_id)
        query = (
            sa.select([users.c.uuid, users.c.email])
            .select_from(j)
            .where(
                (users.c.email.in_(params["emails"]))
                & (users.c.email != request["user"]["email"])
                & (agus.c.group_id == row["group"])
                & (users.c.status.in_(ACTIVE_USER_STATUSES)),
            )
        )
        result = await conn.execute(query)
        user_info = result.fetchall()
        users_to_share = [u["uuid"] for u in user_info]
        emails_to_share = [u["email"] for u in user_info]
        if len(user_info) < 1:
            raise ObjectNotFound(object_name="user")
        if len(user_info) < len(params["emails"]):
            users_not_invfolder_group = list(set(params["emails"]) - set(emails_to_share))
            raise ObjectNotFound(
                "Some users do not belong to folder's group:"
                f" {','.join(users_not_invfolder_group)}",
                object_name="user",
            )

        # Do not share to users who have already been shared the folder.
        query = (
            sa.select([vfolder_permissions])
            .select_from(vfolder_permissions)
            .where(
                (vfolder_permissions.c.user.in_(users_to_share))
                & (vfolder_permissions.c.vfolder == row["id"]),
            )
        )
        result = await conn.execute(query)
        users_not_to_share = [u.user for u in result.fetchall()]
        users_to_share = list(set(users_to_share) - set(users_not_to_share))

        # Create vfolder_permission(s).
        for _user in users_to_share:
            query = sa.insert(
                vfolder_permissions,
                {
                    "permission": params["permission"],
                    "vfolder": row["id"],
                    "user": _user,
                },
            )
            await conn.execute(query)
        # Update existing vfolder_permission(s).
        for _user in users_not_to_share:
            query = (
                sa.update(vfolder_permissions)
                .values(permission=params["permission"])
                .where(vfolder_permissions.c.vfolder == row["id"])
                .where(vfolder_permissions.c.user == _user)
            )
            await conn.execute(query)

        return web.json_response({"shared_emails": emails_to_share}, status=201)


@admin_required
@server_status_required(ALL_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermission.READ_ONLY)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("emails"): t.List(t.String),
    }),
)
async def unshare(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    """
    Unshare a group folder from users.
    """
    root_ctx: RootContext = request.app["_root.context"]
    log.info(
        "VFOLDER.UNSHARE (email:{}, ak:{}, vf:{} (resolved-from:{!r}), users:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        request.match_info["name"],
        ",".join(params["emails"]),
    )
    user_uuid = request["user"]["uuid"]
    domain_name = request["user"]["domain_name"]
    resource_policy = request["keypair"]["resource_policy"]
    if row["ownership_type"] != VFolderOwnershipType.GROUP:
        raise VFolderNotFound("Only project folders are directly unsharable.")
    async with root_ctx.db.begin() as conn:
        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        await ensure_host_permission_allowed(
            conn,
            row["host"],
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.SET_USER_PERM,
        )

        # Convert users' emails to uuids.
        query = (
            sa.select([users.c.uuid]).select_from(users).where(users.c.email.in_(params["emails"]))
        )
        result = await conn.execute(query)
        users_to_unshare = [u["uuid"] for u in result.fetchall()]
        if len(users_to_unshare) < 1:
            raise ObjectNotFound(object_name="user(s).")

        # Delete vfolder_permission(s).
        query = sa.delete(vfolder_permissions).where(
            (vfolder_permissions.c.vfolder == row["id"])
            & (vfolder_permissions.c.user.in_(users_to_unshare)),
        )
        await conn.execute(query)
        return web.json_response({"unshared_emails": params["emails"]}, status=200)


async def _delete(
    root_ctx: RootContext,
    vfolder_row: VFolderRow,
    user_uuid: uuid.UUID,
    user_role: UserRole,
    domain_name: str,
    resource_policy: Mapping[str, Any],
) -> None:
    # Only the effective folder owner can delete the folder.
    if not vfolder_row["is_owner"]:
        raise InvalidAPIParameters("Cannot delete the vfolder that is not owned by myself.")
    await check_vfolder_status(vfolder_row, VFolderStatusSet.DELETABLE)
    async with root_ctx.db.begin_readonly_session() as db_session:
        # perform extra check to make sure records of alive model service not removed by foreign key rule
        if vfolder_row["usage_mode"] == VFolderUsageMode.MODEL:
            live_endpoints = await EndpointRow.list_by_model(db_session, vfolder_row["id"])
            if (
                len([e for e in live_endpoints if e.lifecycle_stage == EndpointLifecycle.CREATED])
                > 0
            ):
                raise ModelServiceDependencyNotCleared
        folder_host = vfolder_row["host"]
        allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
        await ensure_host_permission_allowed(
            db_session.bind,
            folder_host,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
            permission=VFolderHostPermission.DELETE,
        )

    vfolder_row_ids = (vfolder_row["id"],)
    async with root_ctx.db.connect() as db_conn:
        await delete_vfolder_relation_rows(db_conn, root_ctx.db.begin_session, vfolder_row_ids)
    await update_vfolder_status(
        root_ctx.db,
        vfolder_row_ids,
        VFolderOperationStatus.DELETE_PENDING,
    )


class DeleteRequestModel(BaseModel):
    vfolder_id: uuid.UUID = Field(
        validation_alias=AliasChoices("vfolder_id", "vfolderId", "id"),
        description="Target vfolder id to soft-delete, to go to trash bin",
    )


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(DeleteRequestModel)
async def delete_by_id(request: web.Request, params: DeleteRequestModel) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]

    domain_name = request["user"]["domain_name"]
    user_uuid = request["user"]["uuid"]
    user_role = request["user"]["role"]
    resource_policy = request["keypair"]["resource_policy"]
    folder_id = params.vfolder_id

    rows = await resolve_vfolder_rows(
        request,
        VFolderPermissionSetAlias.READABLE,
        folder_id,
        allow_privileged_access=True,
    )
    assert len(rows) == 1
    row = rows[0]
    log.info(
        "VFOLDER.DELETE_BY_ID (email:{}, ak:{}, vf:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        folder_id,
    )
    await _delete(
        root_ctx,
        row,
        user_uuid,
        user_role,
        domain_name,
        resource_policy,
    )
    return web.Response(status=204)


@auth_required
@server_status_required(ALL_ALLOWED)
async def delete_by_name(request: web.Request) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]

    domain_name = request["user"]["domain_name"]
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    resource_policy = request["keypair"]["resource_policy"]
    folder_name = request.match_info["name"]

    rows = await resolve_vfolder_rows(
        request,
        VFolderPermissionSetAlias.READABLE,
        folder_name,
        allow_privileged_access=True,
    )
    if len(rows) > 1:
        raise TooManyVFoldersFound(rows)
    row = rows[0]
    log.info(
        "VFOLDER.DELETE_BY_NAME (email:{}, ak:{}, vf:{} (resolved-from:{!r}))",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        folder_name,
    )
    await _delete(
        root_ctx,
        row,
        user_uuid,
        user_role,
        domain_name,
        resource_policy,
    )
    return web.Response(status=204)


class IDRequestModel(BaseModel):
    name: str = Field(
        validation_alias=AliasChoices("vfolder_name", "vfolderName", "name"),
        description="Target vfolder name",
    )


class CompactVFolderInfoModel(BaseResponseModel):
    id: uuid.UUID = Field(description="Unique ID referencing the vfolder.")
    name: str = Field(description="Name of the vfolder.")


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(IDRequestModel)
async def get_vfolder_id(request: web.Request, params: IDRequestModel) -> CompactVFolderInfoModel:
    folder_name = params.name
    rows = await resolve_vfolder_rows(
        request,
        VFolderPermissionSetAlias.READABLE,
        folder_name,
        allow_privileged_access=True,
    )
    if len(rows) > 1:
        raise TooManyVFoldersFound(rows)
    row = rows[0]
    log.info(
        "VFOLDER.GET_ID (email:{}, ak:{}, vf:{} (resolved-from:{!r}))",
        request["user"]["email"],
        request["keypair"]["access_key"],
        row["id"],
        folder_name,
    )
    return CompactVFolderInfoModel(id=row["id"], name=folder_name)


class DeleteFromTrashRequestModel(BaseModel):
    vfolder_id: uuid.UUID = Field(
        validation_alias=AliasChoices("vfolder_id", "vfolderId", "id"),
        description="Target vfolder id to hard-delete, permanently remove from storage",
    )


@auth_required
@pydantic_params_api_handler(DeleteFromTrashRequestModel)
async def delete_from_trash_bin(
    request: web.Request, params: DeleteFromTrashRequestModel
) -> web.Response:
    """
    Delete `delete-pending` vfolders in storage proxy
    """
    root_ctx: RootContext = request.app["_root.context"]
    app_ctx: PrivateContext = request.app["folders.context"]
    folder_id = params.vfolder_id
    domain_name = request["user"]["domain_name"]
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()

    log.info(
        "VFOLDER.DELETE_FROM_TRASH_BIN (email:{}, ak:{}, vf:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        folder_id,
    )

    # TODO: replace with @with_vfolder_rows_resolved + @with_vfolder_status_checked
    # --- from here ---
    row = (
        await resolve_vfolder_rows(
            request, VFolderPermission.OWNER_PERM, folder_id, allow_privileged_access=True
        )
    )[0]
    await check_vfolder_status(row, VFolderStatusSet.PURGABLE)

    async with root_ctx.db.begin_readonly() as conn:
        entries = await query_accessible_vfolders(
            conn,
            user_uuid,
            allow_privileged_access=True,
            user_role=user_role,
            domain_name=domain_name,
            allowed_vfolder_types=allowed_vfolder_types,
            extra_vf_conds=(vfolders.c.id == folder_id),
        )
        if len(entries) > 1:
            log.error(
                "VFOLDER.DELETE_FROM_TRASH_BIN(folder id:{}, hosts:{}",
                folder_id,
                [entry["host"] for entry in entries],
            )
            raise TooManyVFoldersFound(entries)
        elif len(entries) == 0:
            raise InvalidAPIParameters("No such vfolder.")
        row = entries[0]
    # --- until here ---

    # fs-level deletion may fail or take longer time
    await initiate_vfolder_deletion(
        root_ctx.db,
        [VFolderDeletionInfo(VFolderID.from_row(row), row["host"], row["unmanaged_path"])],
        root_ctx.storage_manager,
        app_ctx.storage_ptask_group,
    )
    return web.Response(status=204)


@auth_required
@server_status_required(ALL_ALLOWED)
async def force_delete(request: web.Request) -> web.Response:
    root_ctx: RootContext = request.app["_root.context"]

    piece = request.match_info["name"]
    try:
        folder_id = uuid.UUID(piece)
    except ValueError:
        log.error(f"Not allowed UUID type value ({piece})")
        return web.Response(status=400)

    row = (
        await resolve_vfolder_rows(
            request, VFolderPermission.OWNER_PERM, folder_id, allow_privileged_access=True
        )
    )[0]
    try:
        await check_vfolder_status(row, VFolderStatusSet.PURGABLE)
    except VFolderFilterStatusFailed:
        await check_vfolder_status(row, VFolderStatusSet.DELETABLE)
    log.info(
        "VFOLDER.FORCE_DELETE (email:{}, ak:{}, vf:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        folder_id,
    )
    await initiate_vfolder_deletion(
        root_ctx.db,
        [VFolderDeletionInfo(VFolderID.from_row(row), row["host"], row["unmanaged_path"])],
        root_ctx.storage_manager,
        force=True,
    )

    return web.Response(status=204)


class PurgeRequestModel(BaseModel):
    vfolder_id: uuid.UUID = Field(
        validation_alias=AliasChoices("vfolder_id", "vfolderId", "id"),
        description="Target vfolder id to purge, permanently remove from DB",
    )


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(PurgeRequestModel)
async def purge(request: web.Request, params: PurgeRequestModel) -> web.Response:
    """
    Delete `delete-complete`d vfolder rows in DB
    """
    root_ctx: RootContext = request.app["_root.context"]
    folder_id = params.vfolder_id
    log.info(
        "VFOLDER.PURGE (email:{}, ak:{}, vf:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        folder_id,
    )
    if request["user"]["role"] not in (
        UserRole.ADMIN,
        UserRole.SUPERADMIN,
    ):
        raise InsufficientPrivilege("You are not allowed to purge vfolders")

    async with root_ctx.db.begin_session() as db_session:
        row = await db_session.scalar(sa.select(VFolderDBRow).where(VFolderDBRow.id == folder_id))
        row = cast(VFolderDBRow | None, row)
        if row is None:
            raise VFolderNotFound(extra_data=folder_id)
        await check_vfolder_status({"status": row.status}, VFolderStatusSet.PURGABLE)
        delete_stmt = sa.delete(VFolderDBRow).where(VFolderDBRow.id == folder_id)
        await db_session.execute(delete_stmt)

    return web.Response(status=204)


class RestoreRequestModel(BaseModel):
    vfolder_id: uuid.UUID = Field(
        validation_alias=AliasChoices("vfolder_id", "vfolderId", "id"),
        description="Target vfolder id to restore",
    )


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(RestoreRequestModel)
async def restore(request: web.Request, params: RestoreRequestModel) -> web.Response:
    """
    Recover vfolder from trash bin, by changing status.
    """
    root_ctx: RootContext = request.app["_root.context"]
    folder_id = params.vfolder_id
    domain_name = request["user"]["domain_name"]
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()
    log.info(
        "VFOLDER.RESTORE (email: {}, ak:{}, vf:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        folder_id,
    )

    # TODO: replace with @with_vfolder_rows_resolved + @with_vfolder_status_checked
    # --- from here ---
    row = (
        await resolve_vfolder_rows(
            request, VFolderPermission.OWNER_PERM, folder_id, allow_privileged_access=True
        )
    )[0]
    await check_vfolder_status(row, VFolderStatusSet.RECOVERABLE)

    async with root_ctx.db.begin() as conn:
        restore_targets = await query_accessible_vfolders(
            conn,
            user_uuid,
            allow_privileged_access=True,
            user_role=user_role,
            domain_name=domain_name,
            allowed_vfolder_types=allowed_vfolder_types,
            extra_vf_conds=(vfolders.c.id == folder_id),
        )
        if len(restore_targets) > 1:
            log.error(
                "VFOLDER.RESTORE(email:{}, folder id:{}, hosts:{})",
                request["user"]["email"],
                folder_id,
                [entry["host"] for entry in restore_targets],
            )
            raise TooManyVFoldersFound(restore_targets)
        elif len(restore_targets) == 0:
            raise InvalidAPIParameters("No such vfolder.")

        row = restore_targets[0]
    # --- until here ---

    # Folder owner OR user who have DELETE permission can restore folder.
    if not row["is_owner"] and row["permission"] != VFolderPermission.RW_DELETE:
        raise InvalidAPIParameters("Cannot restore the vfolder that is not owned by myself.")

    # fs-level mv may fail or take longer time
    # but let's complete the db transaction to reflect that it's deleted.
    await update_vfolder_status(root_ctx.db, (row["id"],), VFolderOperationStatus.READY)
    return web.Response(status=204)


@auth_required
@server_status_required(ALL_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.READABLE, allow_privileged_access=True)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        tx.AliasedKey(["shared_user_uuid", "sharedUserUuid"], default=None): t.String | t.Null,
    }),
)
async def leave(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    """
    Leave from shared VFolder.

    Cannot leave a group VFolder or a VFolder that the requesting user owns.
    """
    if row["ownership_type"] == VFolderOwnershipType.GROUP:
        raise InvalidAPIParameters("Cannot leave a group vfolder.")

    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    user_role = request["user"]["role"]
    rqst_user_uuid = request["user"]["uuid"]
    shared_user_uuid = params["shared_user_uuid"]
    vfolder_id = row["id"]
    perm = row["permission"]

    if shared_user_uuid:
        # Allow only superadmin to leave the shared vfolder of others.
        if (rqst_user_uuid != shared_user_uuid) and (user_role != UserRole.SUPERADMIN):
            raise InsufficientPrivilege("Insufficient permission.")
        user_uuid = shared_user_uuid
    else:
        if row["is_owner"]:
            raise InvalidAPIParameters("Cannot leave a vfolder owned by the requesting user.")
        user_uuid = rqst_user_uuid

    log.info(
        "VFOLDER.LEAVE(email:{}, ak:{}, vf:{} (resolved-from:{!r}), uid:{}, perm:{})",
        request["user"]["email"],
        access_key,
        vfolder_id,
        request.match_info["name"],
        user_uuid,
        perm,
    )
    async with root_ctx.db.begin() as conn:
        query = (
            sa.delete(vfolder_permissions)
            .where(vfolder_permissions.c.vfolder == vfolder_id)
            .where(vfolder_permissions.c.user == user_uuid)
        )
        await conn.execute(query)
    resp = {"msg": "left the shared vfolder"}
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(ALL_ALLOWED)
@with_vfolder_rows_resolved(VFolderPermissionSetAlias.READABLE)
@with_vfolder_status_checked(VFolderStatusSet.UPDATABLE)
@check_api_params(
    t.Dict({
        t.Key("cloneable", default=False): t.Bool,
        t.Key("target_name"): tx.Slug(allow_dot=True),
        t.Key("target_host", default=None) >> "folder_host": t.String | t.Null,
        t.Key("usage_mode", default="general"): tx.Enum(VFolderUsageMode) | t.Null,
        t.Key("permission", default="rw"): tx.Enum(VFolderPermission) | t.Null,
    }),
)
async def clone(request: web.Request, params: Any, row: VFolderRow) -> web.Response:
    resp: Dict[str, Any] = {}
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    user_role = request["user"]["role"]
    user_uuid = request["user"]["uuid"]
    resource_policy = request["keypair"]["resource_policy"]
    domain_name = request["user"]["domain_name"]
    log.info(
        "VFOLDER.CLONE (email:{}, ak:{}, vf:{} (resolved-from:{!r}), vft:{}, vfh:{}, umod:{}, perm:{})",
        request["user"]["email"],
        access_key,
        row["id"],
        request.match_info["name"],
        params["target_name"],
        params["folder_host"],
        params["usage_mode"].value,
        params["permission"].value,
    )
    source_folder_host = row["host"]
    source_folder_id = VFolderID(row["quota_scope_id"], row["id"])
    target_folder_host = params["folder_host"]
    target_quota_scope_id = "..."  # TODO: implement
    source_unmanaged_path = row["unmanaged_path"]
    source_proxy_name, source_volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        source_folder_host, is_unmanaged(source_unmanaged_path)
    )
    target_proxy_name, target_volume_name = root_ctx.storage_manager.get_proxy_and_volume(
        target_folder_host
    )

    # check if the source vfolder is allowed to be cloned
    if not row["cloneable"]:
        raise GenericForbidden("The source vfolder is not permitted to be cloned.")

    if not target_folder_host:
        target_folder_host = await root_ctx.shared_config.etcd.get("volumes/default_host")
        if not target_folder_host:
            raise InvalidAPIParameters(
                "You must specify the vfolder host because the default host is not configured."
            )

    allowed_vfolder_types = await root_ctx.shared_config.get_vfolder_types()

    if not verify_vfolder_name(params["target_name"]):
        raise InvalidAPIParameters(f"{params['target_name']} is reserved for internal operations.")

    if source_proxy_name != target_proxy_name:
        raise InvalidAPIParameters("proxy name of source and target vfolders must be equal.")

    async with root_ctx.db.begin_session() as sess:
        if row["group"]:
            log.debug("Cloning VFolder group ID: {}", row["group"])
            query = (
                sa.select(GroupRow)
                .where((GroupRow.domain_name == domain_name) & (GroupRow.id == row["group"]))
                .options(
                    selectinload(GroupRow.resource_policy_row).options(
                        load_only(ProjectResourcePolicyRow.max_vfolder_count)
                    )
                )
            )
            result = await sess.execute(query)
            group_row = result.scalar()
            max_vfolder_count = group_row.resource_policy_row.max_vfolder_count

        else:
            query = (
                sa.select(UserRow)
                .where(UserRow.uuid == user_uuid)
                .options(
                    selectinload(UserRow.resource_policy_row).options(
                        load_only(UserResourcePolicyRow.max_vfolder_count)
                    )
                )
            )
            result = await sess.execute(query)
            user_row = result.scalar()
            max_vfolder_count = user_row.resource_policy_row.max_vfolder_count

    async with root_ctx.db.begin() as conn:
        allowed_hosts = await filter_host_allowed_permission(
            conn,
            allowed_vfolder_types=allowed_vfolder_types,
            user_uuid=user_uuid,
            resource_policy=resource_policy,
            domain_name=domain_name,
        )
        if (
            target_folder_host not in allowed_hosts
            or VFolderHostPermission.CREATE not in allowed_hosts[target_folder_host]
        ):
            raise InvalidAPIParameters(
                f"`{VFolderHostPermission.CREATE}` Not allowed in vfolder"
                f" host(`{target_folder_host}`)"
            )
        # TODO: handle legacy host lists assuming that volume names don't overlap?
        if target_folder_host not in allowed_hosts:
            raise InvalidAPIParameters("You are not allowed to use this vfolder host.")

        # Check resource policy's max_vfolder_count
        if max_vfolder_count > 0:
            query = sa.select([sa.func.count()]).where(
                (vfolders.c.user == user_uuid)
                & ~(vfolders.c.status.in_(HARD_DELETED_VFOLDER_STATUSES))
            )
            result = await conn.scalar(query)
            if result >= max_vfolder_count:
                raise InvalidAPIParameters("You cannot create more vfolders.")

        # Prevent creation of vfolder with duplicated name on all hosts.
        extra_vf_conds = [vfolders.c.name == params["target_name"]]
        entries = await query_accessible_vfolders(
            conn,
            user_uuid,
            user_role=user_role,
            domain_name=domain_name,
            allowed_vfolder_types=allowed_vfolder_types,
            extra_vf_conds=(sa.and_(*extra_vf_conds)),
        )
        if len(entries) > 0:
            raise VFolderAlreadyExists
        if params["target_name"].startswith("."):
            dotfiles, _ = await query_owned_dotfiles(conn, access_key)
            for dotfile in dotfiles:
                if params["target_name"] == dotfile["path"]:
                    raise InvalidAPIParameters("vFolder name conflicts with your dotfile.")

        if "user" not in allowed_vfolder_types:
            raise InvalidAPIParameters("user vfolder cannot be created in this host")

    task_id, target_folder_id = await initiate_vfolder_clone(
        root_ctx.db,
        VFolderCloneInfo(
            source_folder_id,
            source_folder_host,
            source_unmanaged_path,
            domain_name,
            target_quota_scope_id,
            params["target_name"],
            target_folder_host,
            params["usage_mode"],
            params["permission"],
            request["user"]["email"],
            user_uuid,
            params["cloneable"],
        ),
        root_ctx.storage_manager,
        root_ctx.background_task_manager,
    )

    # Return the information about the destination vfolder.
    resp = {
        "id": target_folder_id.hex,
        "name": params["target_name"],
        "host": target_folder_host,
        "usage_mode": params["usage_mode"].value,
        "permission": params["permission"].value,
        "creator": request["user"]["email"],
        "ownership_type": "user",
        "user": str(user_uuid),
        "group": None,
        "cloneable": params["cloneable"],
        "bgtask_id": str(task_id),
    }
    return web.json_response(resp, status=201)


@auth_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        tx.AliasedKey(["vfolder_id", "vfolderId"], default=None): tx.UUID | t.Null,
    }),
)
async def list_shared_vfolders(request: web.Request, params: Any) -> web.Response:
    """
    List shared vfolders.

    Not available for group vfolders.
    """
    root_ctx: RootContext = request.app["_root.context"]
    target_vfid = params["vfolder_id"]
    log.info(
        "VFOLDER.LIST_SHARED_VFOLDERS (email:{}, ak:{}, vf:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        target_vfid,
    )
    async with root_ctx.db.begin() as conn:
        j = vfolder_permissions.join(vfolders, vfolders.c.id == vfolder_permissions.c.vfolder).join(
            users, users.c.uuid == vfolder_permissions.c.user
        )
        query = sa.select([
            vfolder_permissions,
            vfolders.c.id.label("vfolder_id"),
            vfolders.c.name,
            vfolders.c.group,
            vfolders.c.status,
            vfolders.c.user.label("vfolder_user"),
            users.c.email,
        ]).select_from(j)
        if target_vfid is not None:
            query = query.where(vfolders.c.id == target_vfid)
        result = await conn.execute(query)
        shared_list = result.fetchall()
    shared_info = []
    for shared in shared_list:
        owner = shared.group if shared.group else shared.vfolder_user
        folder_type = "project" if shared.group else "user"
        shared_info.append({
            "vfolder_id": str(shared.vfolder_id),
            "vfolder_name": str(shared.name),
            "status": shared.status.value,
            "owner": str(owner),
            "type": folder_type,
            "shared_to": {
                "uuid": str(shared.user),
                "email": shared.email,
            },
            "perm": shared.permission.value,
        })
    resp = {"shared": shared_info}
    return web.json_response(resp, status=200)


@auth_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("vfolder"): tx.UUID,
        t.Key("user"): tx.UUID,
        tx.AliasedKey(["perm", "permission"]): VFolderPermissionValidator | t.Null,
    }),
)
async def update_shared_vfolder(request: web.Request, params: Any) -> web.Response:
    """
    Update permission for shared vfolders.

    If params['perm'] is None, remove user's permission for the vfolder.
    """
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    vfolder_id = params["vfolder"]
    user_uuid = params["user"]
    perm = params["perm"]
    log.info(
        "VFOLDER.UPDATE_SHARED_VFOLDER(email:{}, ak:{}, vf:{}, uid:{}, perm:{})",
        request["user"]["email"],
        access_key,
        vfolder_id,
        user_uuid,
        perm,
    )
    async with root_ctx.db.begin() as conn:
        if perm is not None:
            query = (
                sa.update(vfolder_permissions)
                .values(permission=perm)
                .where(vfolder_permissions.c.vfolder == vfolder_id)
                .where(vfolder_permissions.c.user == user_uuid)
            )
        else:
            query = (
                sa.delete(vfolder_permissions)
                .where(vfolder_permissions.c.vfolder == vfolder_id)
                .where(vfolder_permissions.c.user == user_uuid)
            )
        await conn.execute(query)
    resp = {"msg": "shared vfolder permission updated"}
    return web.json_response(resp, status=200)


class UserPermMapping(BaseModel):
    user_id: Annotated[
        uuid.UUID,
        Field(
            validation_alias=AliasChoices("user", "user_id", "userID"),
            description="Target user id to update sharing status.",
        ),
    ]
    perm: Annotated[
        VFolderPermission | None,
        Field(
            validation_alias=AliasChoices("perm", "permission"),
            default=None,
            description=textwrap.dedent(
                "Permission to update. Delete the sharing between vfolder and user if this value is null. "
                f"Should be one of {[p.value for p in VFolderPermission]}. "
                "Default value is null."
            ),
        ),
    ]


class UpdateSharedRequestModel(BaseModel):
    vfolder_id: Annotated[
        uuid.UUID,
        Field(
            validation_alias=AliasChoices("vfolder_id", "vfolderId", "vfolder"),
            description="Target vfolder id to update sharing status.",
        ),
    ]
    user_perm_list: Annotated[
        list[UserPermMapping],
        Field(
            validation_alias=AliasChoices("user_perm", "user_perm_list", "userPermList"),
            description="A list of user and permission mappings.",
        ),
    ]


@auth_required
@server_status_required(ALL_ALLOWED)
@pydantic_params_api_handler(UpdateSharedRequestModel)
async def update_vfolder_sharing_status(
    request: web.Request, params: UpdateSharedRequestModel
) -> web.Response:
    """
    Update permission for shared vfolders.
    """
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    vfolder_id = params.vfolder_id
    user_perm_list = params.user_perm_list
    log.info(
        "VFOLDER.UPDATE_VFOLDER_SHARING_STATUS(email:{}, ak:{}, vf:{}, data:{})",
        request["user"]["email"],
        access_key,
        vfolder_id,
        user_perm_list,
    )

    to_delete: list[uuid.UUID] = []
    to_update: list[Mapping[str, Any]] = []
    for mapping in user_perm_list:
        if mapping.perm is None:
            to_delete.append(mapping.user_id)
        else:
            to_update.append({
                "user_id": mapping.user_id,
                "perm": mapping.perm,
            })

    async def _update_or_delete(db_session: SASession) -> None:
        if to_delete:
            stmt = (
                sa.delete(VFolderPermissionRow)
                .where(VFolderPermissionRow.vfolder == vfolder_id)
                .where(VFolderPermissionRow.user.in_(to_delete))
            )
            await db_session.execute(stmt)

        if to_update:
            stmt = (
                sa.update(VFolderPermissionRow)
                .values(permission=sa.bindparam("perm"))
                .where(VFolderPermissionRow.vfolder == vfolder_id)
                .where(VFolderPermissionRow.user == sa.bindparam("user_id"))
            )
            await db_session.execute(stmt, to_update)

    async with root_ctx.db.connect() as db_conn:
        await execute_with_txn_retry(_update_or_delete, root_ctx.db.begin_session, db_conn)
    return web.Response(status=201)


@superadmin_required
@server_status_required(READ_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("fstab_path", default=None): t.String | t.Null,
        t.Key("agent_id", default=None): t.String | t.Null,
    }),
)
async def get_fstab_contents(request: web.Request, params: Any) -> web.Response:
    """
    Return the contents of `/etc/fstab` file.
    """
    access_key = request["keypair"]["access_key"]
    log.info(
        "VFOLDER.GET_FSTAB_CONTENTS(email:{}, ak:{}, ag:{})",
        request["user"]["email"],
        access_key,
        params["agent_id"],
    )
    if params["fstab_path"] is None:
        params["fstab_path"] = "/etc/fstab"
    if params["agent_id"] is not None:
        # Return specific agent's fstab.
        watcher_info = await get_watcher_info(request, params["agent_id"])
        try:
            client_timeout = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(timeout=client_timeout) as sess:
                headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
                url = watcher_info["addr"] / "fstab"
                async with sess.get(url, headers=headers, params=params) as watcher_resp:
                    if watcher_resp.status == 200:
                        content = await watcher_resp.text()
                        resp = {
                            "content": content,
                            "node": "agent",
                            "node_id": params["agent_id"],
                        }
                        return web.json_response(resp)
                    else:
                        message = await watcher_resp.text()
                        raise BackendAgentError(
                            "FAILURE", f"({watcher_resp.status}: {watcher_resp.reason}) {message}"
                        )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            log.error(
                "VFOLDER.GET_FSTAB_CONTENTS(u:{}): timeout from watcher (agent:{})",
                access_key,
                params["agent_id"],
            )
            raise BackendAgentError("TIMEOUT", "Could not fetch fstab data from agent")
        except Exception:
            log.exception(
                "VFOLDER.GET_FSTAB_CONTENTS(u:{}): "
                "unexpected error while reading from watcher (agent:{})",
                access_key,
                params["agent_id"],
            )
            raise InternalServerError
    else:
        resp = {
            "content": (
                "# Since Backend.AI 20.09, reading the manager fstab is no longer supported."
            ),
            "node": "manager",
            "node_id": "manager",
        }
        return web.json_response(resp)


@superadmin_required
@server_status_required(READ_ALLOWED)
async def list_mounts(request: web.Request) -> web.Response:
    """
    List all mounted vfolder hosts in vfroot.

    All mounted hosts from connected (ALIVE) agents are also gathered.
    Generally, agents should be configured to have same hosts structure,
    but newly introduced one may not.
    """
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    log.info(
        "VFOLDER.LIST_MOUNTS(ak:{})",
        access_key,
    )
    mount_prefix = await root_ctx.shared_config.get_raw("volumes/_mount")
    if mount_prefix is None:
        mount_prefix = "/mnt"

    # NOTE: Changed in 20.09: the manager instances no longer have mountpoints.
    all_volumes = [*await root_ctx.storage_manager.get_all_volumes()]
    all_mounts = [volume_data["path"] for proxy_name, volume_data in all_volumes]
    all_vfolder_hosts = [
        f"{proxy_name}:{volume_data['name']}" for proxy_name, volume_data in all_volumes
    ]
    resp: MutableMapping[str, Any] = {
        "manager": {
            "success": True,
            "mounts": all_mounts,
            "message": "(legacy)",
        },
        "storage-proxy": {
            "success": True,
            "mounts": [*zip(all_vfolder_hosts, all_mounts)],
            "message": "",
        },
        "agents": {},
    }

    # Scan mounted vfolder hosts for connected agents.
    async def _fetch_mounts(
        sema: asyncio.Semaphore,
        sess: aiohttp.ClientSession,
        agent_id: str,
    ) -> Tuple[str, Mapping]:
        async with sema:
            watcher_info = await get_watcher_info(request, agent_id)
            headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
            url = watcher_info["addr"] / "mounts"
            try:
                async with sess.get(url, headers=headers) as watcher_resp:
                    if watcher_resp.status == 200:
                        data = {
                            "success": True,
                            "mounts": await watcher_resp.json(),
                            "message": "",
                        }
                    else:
                        data = {
                            "success": False,
                            "mounts": [],
                            "message": await watcher_resp.text(),
                        }
                    return (agent_id, data)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                log.error(
                    "VFOLDER.LIST_MOUNTS(u:{}): timeout from watcher (agent:{})",
                    access_key,
                    agent_id,
                )
                raise
            except Exception:
                log.exception(
                    "VFOLDER.LIST_MOUNTS(u:{}): "
                    "unexpected error while reading from watcher (agent:{})",
                    access_key,
                    agent_id,
                )
                raise

    async with root_ctx.db.begin() as conn:
        query = (
            sa.select([agents.c.id]).select_from(agents).where(agents.c.status == AgentStatus.ALIVE)
        )
        result = await conn.execute(query)
        rows = result.fetchall()

    client_timeout = aiohttp.ClientTimeout(total=10.0)
    async with aiohttp.ClientSession(timeout=client_timeout) as sess:
        sema = asyncio.Semaphore(8)
        mounts = await asyncio.gather(
            *[_fetch_mounts(sema, sess, row.id) for row in rows], return_exceptions=True
        )
        for mount in mounts:
            match mount:
                case BaseException():
                    continue
                case _:
                    resp["agents"][mount[0]] = mount[1]

    return web.json_response(resp, status=200)


@superadmin_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("fs_location"): t.String,
        t.Key("name"): t.String,
        t.Key("fs_type", default="nfs"): t.String,
        t.Key("options", default=None): t.String | t.Null,
        t.Key("scaling_group", default=None): t.String | t.Null,
        t.Key("fstab_path", default=None): t.String | t.Null,
        t.Key("edit_fstab", default=False): t.ToBool,
    }),
)
async def mount_host(request: web.Request, params: Any) -> web.Response:
    """
    Mount device into vfolder host.

    Mount a device (eg: nfs) located at `fs_location` into `<vfroot>/name` in the
    host machines (manager and all agents). `fs_type` can be specified by requester,
    which fallbaks to 'nfs'.

    If `scaling_group` is specified, try to mount for agents in the scaling group.
    """
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    log_fmt = "VFOLDER.MOUNT_HOST(ak:{}, name:{}, fs:{}, sg:{})"
    log_args = (access_key, params["name"], params["fs_location"], params["scaling_group"])
    log.info(log_fmt, *log_args)
    mount_prefix = await root_ctx.shared_config.get_raw("volumes/_mount")
    if mount_prefix is None:
        mount_prefix = "/mnt"

    # NOTE: Changed in 20.09: the manager instances no longer have mountpoints.
    resp: MutableMapping[str, Any] = {
        "manager": {
            "success": True,
            "message": "Managers do not have mountpoints since v20.09.",
        },
        "agents": {},
    }

    # Mount on running agents.
    async with root_ctx.db.begin() as conn:
        query = (
            sa.select([agents.c.id]).select_from(agents).where(agents.c.status == AgentStatus.ALIVE)
        )
        if params["scaling_group"] is not None:
            query = query.where(agents.c.scaling == params["scaling_group"])
        result = await conn.execute(query)
        rows = result.fetchall()

    async def _mount(
        sema: asyncio.Semaphore,
        sess: aiohttp.ClientSession,
        agent_id: str,
    ) -> Tuple[str, Mapping]:
        async with sema:
            watcher_info = await get_watcher_info(request, agent_id)
            try:
                headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
                url = watcher_info["addr"] / "mounts"
                async with sess.post(url, json=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = {
                            "success": True,
                            "message": await resp.text(),
                        }
                    else:
                        data = {
                            "success": False,
                            "message": await resp.text(),
                        }
                    return (agent_id, data)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                log.error(
                    log_fmt + ": timeout from watcher (ag:{})",
                    *log_args,
                    agent_id,
                )
                raise
            except Exception:
                log.exception(
                    log_fmt + ": unexpected error while reading from watcher (ag:{})",
                    *log_args,
                    agent_id,
                )
                raise

    client_timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=client_timeout) as sess:
        sema = asyncio.Semaphore(8)
        results = await asyncio.gather(
            *[_mount(sema, sess, row.id) for row in rows], return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                # exceptions are already logged.
                continue
            resp["agents"][result[0]] = result[1]

    return web.json_response(resp, status=200)


@superadmin_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("name"): t.String,
        t.Key("scaling_group", default=None): t.String | t.Null,
        t.Key("fstab_path", default=None): t.String | t.Null,
        t.Key("edit_fstab", default=False): t.ToBool,
    }),
)
async def umount_host(request: web.Request, params: Any) -> web.Response:
    """
    Unmount device from vfolder host.

    Unmount a device (eg: nfs) located at `<vfroot>/name` from the host machines
    (manager and all agents).

    If `scaling_group` is specified, try to unmount for agents in the scaling group.
    """
    root_ctx: RootContext = request.app["_root.context"]
    access_key = request["keypair"]["access_key"]
    log_fmt = "VFOLDER.UMOUNT_HOST(ak:{}, name:{}, sg:{})"
    log_args = (access_key, params["name"], params["scaling_group"])
    log.info(log_fmt, *log_args)
    mount_prefix = await root_ctx.shared_config.get_raw("volumes/_mount")
    if mount_prefix is None:
        mount_prefix = "/mnt"
    mountpoint = Path(mount_prefix) / params["name"]
    assert Path(mount_prefix) != mountpoint

    async with root_ctx.db.begin() as conn, conn.begin():
        # Prevent unmount if target host is mounted to running kernels.
        query = (
            sa.select([kernels.c.mounts])
            .select_from(kernels)
            .where(kernels.c.status != KernelStatus.TERMINATED)
        )
        result = await conn.execute(query)
        _kernels = result.fetchall()
        _mounted = set()
        for kern in _kernels:
            if kern.mounts:
                _mounted.update([m[1] for m in kern.mounts])
        if params["name"] in _mounted:
            return web.json_response(
                {
                    "title": "Target host is used in sessions",
                    "message": "Target host is used in sessions",
                },
                status=409,
            )

        query = (
            sa.select([agents.c.id]).select_from(agents).where(agents.c.status == AgentStatus.ALIVE)
        )
        if params["scaling_group"] is not None:
            query = query.where(agents.c.scaling == params["scaling_group"])
        result = await conn.execute(query)
        _agents = result.fetchall()

    # Unmount from manager.
    # NOTE: Changed in 20.09: the manager instances no longer have mountpoints.
    resp: MutableMapping[str, Any] = {
        "manager": {
            "success": True,
            "message": "Managers do not have mountpoints since v20.09.",
        },
        "agents": {},
    }

    # Unmount from running agents.
    async def _umount(
        sema: asyncio.Semaphore,
        sess: aiohttp.ClientSession,
        agent_id: str,
    ) -> Tuple[str, Mapping]:
        async with sema:
            watcher_info = await get_watcher_info(request, agent_id)
            try:
                headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
                url = watcher_info["addr"] / "mounts"
                async with sess.delete(url, json=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = {
                            "success": True,
                            "message": await resp.text(),
                        }
                    else:
                        data = {
                            "success": False,
                            "message": await resp.text(),
                        }
                    return (agent_id, data)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                log.error(
                    log_fmt + ": timeout from watcher (agent:{})",
                    *log_args,
                    agent_id,
                )
                raise
            except Exception:
                log.exception(
                    log_fmt + ": unexpected error while reading from watcher (agent:{})",
                    *log_args,
                    agent_id,
                )
                raise

    client_timeout = aiohttp.ClientTimeout(total=10.0)
    async with aiohttp.ClientSession(timeout=client_timeout) as sess:
        sema = asyncio.Semaphore(8)
        results = await asyncio.gather(
            *[_umount(sema, sess, _agent.id) for _agent in _agents], return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                # exceptions are already logged.
                continue
            resp["agents"][result[0]] = result[1]

    return web.json_response(resp, status=200)


async def storage_task_exception_handler(
    exc_type: type[BaseException],
    exc_obj: BaseException,
    exc_tb: TracebackType,
) -> None:
    log.exception("Error while removing vFolder", exc_info=exc_obj)


@superadmin_required
@server_status_required(ALL_ALLOWED)
@check_api_params(
    t.Dict({
        t.Key("vfolder"): tx.UUID,
        t.Key("user_email"): t.String,
    }),
)
async def change_vfolder_ownership(request: web.Request, params: Any) -> web.Response:
    """
    Change the ownership of vfolder
    For now, we only provide changing the ownership of user-folder
    """
    vfolder_id = params["vfolder"]
    user_email = params["user_email"]
    root_ctx: RootContext = request.app["_root.context"]

    allowed_hosts_by_user = VFolderHostPermissionMap()
    async with root_ctx.db.begin_readonly() as conn:
        j = sa.join(users, keypairs, users.c.email == keypairs.c.user_id)
        query = (
            sa.select([users.c.uuid, users.c.domain_name, keypairs.c.resource_policy])
            .select_from(j)
            .where((users.c.email == user_email) & (users.c.status == UserStatus.ACTIVE))
        )
        try:
            result = await conn.execute(query)
        except sa.exc.DataError:
            raise InvalidAPIParameters
        user_info = result.first()
        if user_info is None:
            raise ObjectNotFound(object_name="user")
        resource_policy_name = user_info.resource_policy
        result = await conn.execute(
            sa.select([keypair_resource_policies.c.allowed_vfolder_hosts]).where(
                keypair_resource_policies.c.name == resource_policy_name
            )
        )
        resource_policy = result.first()
        allowed_hosts_by_user = await get_allowed_vfolder_hosts_by_user(
            conn=conn,
            resource_policy=resource_policy,
            domain_name=user_info.domain_name,
            user_uuid=user_info.uuid,
        )
    log.info(
        "VFOLDER.CHANGE_VFOLDER_OWNERSHIP(email:{}, ak:{}, vfid:{}, uid:{})",
        request["user"]["email"],
        request["keypair"]["access_key"],
        vfolder_id,
        user_info.uuid,
    )
    async with root_ctx.db.begin_readonly() as conn:
        query = (
            sa.select([vfolders.c.host])
            .select_from(vfolders)
            .where(
                (vfolders.c.id == vfolder_id)
                & (vfolders.c.ownership_type == VFolderOwnershipType.USER)
            )
        )
        folder_host = await conn.scalar(query)
    if folder_host not in allowed_hosts_by_user:
        raise VFolderOperationFailed("User to migrate vfolder needs an access to the storage host.")

    async def _update() -> None:
        async with root_ctx.db.begin() as conn:
            # TODO: we need to implement migration from project to other project
            #       for now we only support migration btw user folder only
            # TODO: implement quota-scope migration and progress checks
            query = (
                sa.update(vfolders)
                .values(user=user_info.uuid)
                .where(
                    (vfolders.c.id == vfolder_id)
                    & (vfolders.c.ownership_type == VFolderOwnershipType.USER)
                )
            )
            await conn.execute(query)

    await execute_with_retry(_update)

    async def _delete_vfolder_related_rows() -> None:
        async with root_ctx.db.begin() as conn:
            # delete vfolder_invitation if the new owner user has already been shared with the vfolder
            query = sa.delete(vfolder_invitations).where(
                (vfolder_invitations.c.invitee == user_email)
                & (vfolder_invitations.c.vfolder == vfolder_id)
            )
            await conn.execute(query)
            # delete vfolder_permission if the new owner user has already been shared with the vfolder
            query = sa.delete(vfolder_permissions).where(
                (vfolder_permissions.c.vfolder == vfolder_id)
                & (vfolder_permissions.c.user == user_info.uuid)
            )
            await conn.execute(query)

    await execute_with_retry(_delete_vfolder_related_rows)

    return web.json_response({}, status=200)


@attrs.define(slots=True, auto_attribs=True, init=False)
class PrivateContext:
    database_ptask_group: aiotools.PersistentTaskGroup
    storage_ptask_group: aiotools.PersistentTaskGroup


async def init(app: web.Application) -> None:
    app_ctx: PrivateContext = app["folders.context"]
    app_ctx.database_ptask_group = aiotools.PersistentTaskGroup()
    app_ctx.storage_ptask_group = aiotools.PersistentTaskGroup(
        exception_handler=storage_task_exception_handler
    )


async def shutdown(app: web.Application) -> None:
    app_ctx: PrivateContext = app["folders.context"]
    await app_ctx.database_ptask_group.shutdown()
    await app_ctx.storage_ptask_group.shutdown()


def create_app(default_cors_options):
    app = web.Application()
    app["prefix"] = "folders"
    app["api_versions"] = (2, 3, 4)
    app.on_startup.append(init)
    app.on_shutdown.append(shutdown)
    app["folders.context"] = PrivateContext()
    cors = aiohttp_cors.setup(app, defaults=default_cors_options)
    add_route = app.router.add_route
    root_resource = cors.add(app.router.add_resource(r""))
    cors.add(root_resource.add_route("POST", create))
    cors.add(root_resource.add_route("GET", list_folders))
    cors.add(root_resource.add_route("DELETE", delete_by_id))
    vfolder_resource = cors.add(app.router.add_resource(r"/{name}"))
    cors.add(vfolder_resource.add_route("GET", get_info))
    cors.add(vfolder_resource.add_route("DELETE", delete_by_name))
    cors.add(add_route("GET", r"/_/id", get_vfolder_id))
    cors.add(add_route("GET", r"/_/hosts", list_hosts))
    cors.add(add_route("GET", r"/_/all-hosts", list_all_hosts))
    cors.add(add_route("GET", r"/_/allowed-types", list_allowed_types))
    cors.add(add_route("GET", r"/_/all_hosts", list_all_hosts))  # legacy underbar
    cors.add(add_route("GET", r"/_/allowed_types", list_allowed_types))  # legacy underbar
    cors.add(add_route("GET", r"/_/perf-metric", get_volume_perf_metric))
    cors.add(add_route("POST", r"/{name}/rename", rename_vfolder))
    cors.add(add_route("POST", r"/{name}/update-options", update_vfolder_options))
    cors.add(add_route("POST", r"/{name}/mkdir", mkdir))
    cors.add(add_route("POST", r"/{name}/request-upload", create_upload_session))
    cors.add(add_route("POST", r"/{name}/request-download", create_download_session))
    cors.add(add_route("POST", r"/{name}/move-file", move_file))
    cors.add(add_route("POST", r"/{name}/rename-file", rename_file))
    cors.add(add_route("POST", r"/{name}/delete-files", delete_files))
    cors.add(add_route("DELETE", r"/{name}/delete-files", delete_files))
    cors.add(add_route("POST", r"/{name}/rename_file", rename_file))  # legacy underbar
    cors.add(add_route("DELETE", r"/{name}/delete_files", delete_files))  # legacy underbar
    cors.add(add_route("GET", r"/{name}/files", list_files))
    cors.add(add_route("POST", r"/{name}/invite", invite))
    cors.add(add_route("POST", r"/{name}/leave", leave))
    cors.add(add_route("POST", r"/{name}/share", share))
    cors.add(add_route("POST", r"/{name}/unshare", unshare))
    cors.add(add_route("DELETE", r"/{name}/unshare", unshare))
    cors.add(add_route("POST", r"/{name}/clone", clone))
    cors.add(add_route("POST", r"/purge", purge))
    cors.add(add_route("POST", r"/restore-from-trash-bin", restore))
    cors.add(add_route("POST", r"/delete-from-trash-bin", delete_from_trash_bin))
    cors.add(add_route("DELETE", r"/{name}/force", force_delete))
    cors.add(add_route("GET", r"/invitations/list-sent", list_sent_invitations))
    cors.add(add_route("GET", r"/invitations/list_sent", list_sent_invitations))  # legacy underbar
    cors.add(add_route("POST", r"/invitations/update/{inv_id}", update_invitation))
    cors.add(add_route("GET", r"/invitations/list", invitations))
    cors.add(add_route("POST", r"/invitations/accept", accept_invitation))
    cors.add(add_route("POST", r"/invitations/delete", delete_invitation))
    cors.add(add_route("DELETE", r"/invitations/delete", delete_invitation))
    cors.add(add_route("GET", r"/_/shared", list_shared_vfolders))
    cors.add(add_route("POST", r"/_/shared", update_shared_vfolder))
    cors.add(add_route("POST", r"/_/sharing", update_vfolder_sharing_status))
    cors.add(add_route("GET", r"/_/fstab", get_fstab_contents))
    cors.add(add_route("GET", r"/_/mounts", list_mounts))
    cors.add(add_route("POST", r"/_/mounts", mount_host))
    cors.add(add_route("POST", r"/_/umounts", umount_host))
    cors.add(add_route("DELETE", r"/_/mounts", umount_host))
    cors.add(add_route("POST", r"/_/change-ownership", change_vfolder_ownership))
    cors.add(add_route("GET", r"/_/quota", get_quota))
    cors.add(add_route("POST", r"/_/quota", update_quota))
    cors.add(add_route("GET", r"/_/usage", get_usage))
    cors.add(add_route("GET", r"/_/used-bytes", get_used_bytes))
    return app, []
