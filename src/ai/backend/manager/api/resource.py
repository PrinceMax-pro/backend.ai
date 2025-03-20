"""
Resource preset APIs.
"""

from __future__ import annotations

import copy
import functools
import json
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)
from uuid import UUID

import aiohttp
import aiohttp_cors
import msgpack
import sqlalchemy as sa
import trafaret as t
import yarl
from aiohttp import web
from async_timeout import timeout as _timeout
from dateutil.tz import tzutc
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline as RedisPipeline

from ai.backend.common import redis_helper
from ai.backend.common import validators as tx
from ai.backend.common.utils import nmget
from ai.backend.logging import BraceStyleAdapter
from ai.backend.manager.models.container_registry import ContainerRegistryRow
from ai.backend.manager.services.resource.actions.check_presets import CheckResourcePresetsAction
from ai.backend.manager.services.resource.actions.list_presets import ListResourcePresetsAction
from ai.backend.manager.services.resource.actions.recalculate_usage import RecalculateUsageAction
from ai.backend.manager.services.resource.actions.usage_per_month import UsagePerMonthAction
from ai.backend.manager.services.resource.actions.usage_per_period import UsagePerPeriodAction

from ..models import (
    LIVE_STATUS,
    RESOURCE_USAGE_KERNEL_STATUSES,
    groups,
    kernels,
    users,
)
from ..models.resource_usage import (
    ProjectResourceUsage,
    fetch_resource_usage,
    parse_resource_usage_groups,
    parse_total_resource_group,
)
from .auth import auth_required, superadmin_required
from .exceptions import InvalidAPIParameters
from .manager import READ_ALLOWED, server_status_required
from .types import CORSOptions, WebMiddleware
from .utils import check_api_params

if TYPE_CHECKING:
    from .context import RootContext

log = BraceStyleAdapter(logging.getLogger(__spec__.name))

_json_loads = functools.partial(json.loads, parse_float=Decimal)


@auth_required
async def list_presets(request: web.Request) -> web.Response:
    """
    Returns the list of all resource presets.
    """
    log.info("LIST_PRESETS (ak:{})", request["keypair"]["access_key"])
    root_ctx: RootContext = request.app["_root.context"]

    scaling_group_name = request.query.get("scaling_group")
    result = await root_ctx.processors.resource.list_presets.wait_for_complete(
        ListResourcePresetsAction(
            access_key=request["keypair"]["access_key"],
            scaling_group=scaling_group_name,
        )
    )
    return web.json_response({"presets": result}, status=200)


@server_status_required(READ_ALLOWED)
@auth_required
@check_api_params(
    t.Dict({
        t.Key("scaling_group", default=None): t.Null | t.String,
        t.Key("group", default="default"): t.String,
    })
)
async def check_presets(request: web.Request, params: Any) -> web.Response:
    """
    Returns the list of all resource presets in the current scaling group,
    with additional information including allocatability of each preset,
    amount of total remaining resources, and the current keypair resource limits.
    """
    root_ctx: RootContext = request.app["_root.context"]
    try:
        access_key = request["keypair"]["access_key"]
        resource_policy = request["keypair"]["resource_policy"]
        domain_name = request["user"]["domain_name"]
        # TODO: uncomment when we implement scaling group.
        # scaling_group = request.query.get('scaling_group')
        # assert scaling_group is not None, 'scaling_group parameter is missing.'
    except (json.decoder.JSONDecodeError, AssertionError) as e:
        raise InvalidAPIParameters(extra_msg=str(e.args[0]))

    log.info(
        "CHECK_PRESETS (ak:{}, g:{}, sg:{})",
        access_key,
        params["group"],
        params["scaling_group"],
    )

    result = await root_ctx.processors.resource.check_presets.wait_for_complete(
        CheckResourcePresetsAction(
            access_key=access_key,
            resource_policy=resource_policy,
            domain_name=domain_name,
            user_id=request["user"]["uuid"],
            group=params["group"],
            scaling_group=params["scaling_group"],
        )
    )

    resp = {
        "presets": result.presets,
        "keypair_limits": result.keypair_limits,
        "keypair_using": result.keypair_using,
        "keypair_remaining": result.keypair_remaining,
        "group_limits": result.group_limits,
        "group_using": result.group_using,
        "group_remaining": result.group_remaining,
        "scaling_group_remaining": result.scaling_group_remaining,
        "scaling_groups": result.scaling_groups,
    }

    return web.json_response(resp, status=200)


@server_status_required(READ_ALLOWED)
@superadmin_required
async def recalculate_usage(request: web.Request) -> web.Response:
    """
    Update `keypair_resource_usages` in redis and `agents.c.occupied_slots`.

    Those two values are sometimes out of sync. In that case, calling this API
    re-calculates the values for running containers and updates them in DB.
    """
    log.info("RECALCULATE_USAGE ()")
    root_ctx: RootContext = request.app["_root.context"]
    await root_ctx.processors.resource.check_presets.wait_for_complete(RecalculateUsageAction())

    return web.json_response({}, status=200)


@server_status_required(READ_ALLOWED)
@superadmin_required
@check_api_params(
    t.Dict({
        tx.MultiKey("group_ids"): t.List(t.String) | t.Null,
        t.Key("month"): t.Regexp(r"^\d{6}", re.ASCII),
    }),
    loads=_json_loads,
)
async def usage_per_month(request: web.Request, params: Any) -> web.Response:
    """
    Return usage statistics of terminated containers for a specified month.
    The date/time comparison is done using the configured timezone.

    :param group_ids: If not None, query containers only in those groups.
    :param month: The year-month to query usage statistics. ex) "202006" to query for Jun 2020
    """
    log.info("USAGE_PER_MONTH (g:[{}], month:{})", ",".join(params["group_ids"]), params["month"])
    root_ctx: RootContext = request.app["_root.context"]

    result = await root_ctx.processors.resource.usage_per_month.wait_for_complete(
        UsagePerMonthAction(
            group_ids=params["group_ids"],
            month=params["month"],
        )
    )
    return web.json_response(result, status=200)


@server_status_required(READ_ALLOWED)
@superadmin_required
@check_api_params(
    t.Dict({
        tx.AliasedKey(["project_id", "group_id"], default=None): t.Null | t.String,
        t.Key("start_date"): t.Regexp(r"^\d{8}$", re.ASCII),
        t.Key("end_date"): t.Regexp(r"^\d{8}$", re.ASCII),
    }),
    loads=_json_loads,
)
async def usage_per_period(request: web.Request, params: Any) -> web.Response:
    """
    Return usage statistics of terminated containers belonged to the given group for a specified
    period in dates.
    The date/time comparison is done using the configured timezone.

    :param project_id: If not None, query containers only in the project.
    :param start_date str: "yyyymmdd" format.
    :param end_date str: "yyyymmdd" format.
    """
    root_ctx: RootContext = request.app["_root.context"]

    result = await root_ctx.processors.resource.usage_per_period.wait_for_complete(
        UsagePerPeriodAction(
            project_id=params["project_id"],
            start_date=params["start_date"],
            end_date=params["end_date"],
        )
    )

    return web.json_response(result, status=200)


async def get_time_binned_monthly_stats(request: web.Request, user_uuid=None):
    """
    Generate time-binned (15 min) stats for the last one month (2880 points).
    The structure of the result would be:

        [
          # [
          #     timestamp, num_sessions,
          #     cpu_allocated, mem_allocated, gpu_allocated,
          #     io_read, io_write, scratch_used,
          # ]
            [1562083808.657106, 1, 1.2, 1073741824, ...],
            [1562084708.657106, 2, 4.0, 1073741824, ...],
        ]

    Note that the timestamp is in UNIX-timestamp.
    """
    # Get all or user kernels for the last month from DB.
    time_window = 900  # 15 min
    stat_length = 2880  # 15 * 4 * 24 * 30
    now = datetime.now(tzutc())
    start_date = now - timedelta(days=30)
    root_ctx: RootContext = request.app["_root.context"]
    async with root_ctx.db.begin_readonly() as conn:
        query = (
            sa.select([
                kernels.c.id,
                kernels.c.created_at,
                kernels.c.terminated_at,
                kernels.c.occupied_slots,
            ])
            .select_from(kernels)
            .where(
                (kernels.c.terminated_at >= start_date)
                & (kernels.c.status.in_(RESOURCE_USAGE_KERNEL_STATUSES)),
            )
            .order_by(sa.asc(kernels.c.created_at))
        )
        if user_uuid is not None:
            query = query.where(kernels.c.user_uuid == user_uuid)
        result = await conn.execute(query)
        rows = result.fetchall()

    # Build time-series of time-binned stats.
    start_date_ts = start_date.timestamp()
    time_series_list: list[dict[str, Any]] = [
        {
            "date": start_date_ts + (idx * time_window),
            "num_sessions": {
                "value": 0,
                "unit_hint": "count",
            },
            "cpu_allocated": {
                "value": 0,
                "unit_hint": "count",
            },
            "mem_allocated": {
                "value": 0,
                "unit_hint": "bytes",
            },
            "gpu_allocated": {
                "value": 0,
                "unit_hint": "count",
            },
            "io_read_bytes": {
                "value": 0,
                "unit_hint": "bytes",
            },
            "io_write_bytes": {
                "value": 0,
                "unit_hint": "bytes",
            },
            "disk_used": {
                "value": 0,
                "unit_hint": "bytes",
            },
        }
        for idx in range(stat_length)
    ]

    async def _pipe_builder(r: Redis) -> RedisPipeline:
        pipe = r.pipeline()
        for row in rows:
            await pipe.get(str(row["id"]))
        return pipe

    raw_stats = await redis_helper.execute(root_ctx.redis_stat, _pipe_builder)

    for row, raw_stat in zip(rows, raw_stats):
        if raw_stat is not None:
            last_stat = msgpack.unpackb(raw_stat)
            io_read_byte = int(nmget(last_stat, "io_read.current", 0))
            io_write_byte = int(nmget(last_stat, "io_write.current", 0))
            disk_used = int(nmget(last_stat, "io_scratch_size.stats.max", 0, "/"))
        else:
            io_read_byte = 0
            io_write_byte = 0
            disk_used = 0

        occupied_slots: Mapping[str, Any] = row.occupied_slots
        kernel_created_at: float = row.created_at.timestamp()
        kernel_terminated_at: float = row.terminated_at.timestamp()
        cpu_value = int(occupied_slots.get("cpu", 0))
        mem_value = int(occupied_slots.get("mem", 0))
        cuda_device_value = int(occupied_slots.get("cuda.devices", 0))
        cuda_share_value = Decimal(occupied_slots.get("cuda.shares", 0))

        start_index = int((kernel_created_at - start_date_ts) // time_window)
        end_index = int((kernel_terminated_at - start_date_ts) // time_window) + 1
        if start_index < 0:
            start_index = 0
        for time_series in time_series_list[start_index:end_index]:
            time_series["num_sessions"]["value"] += 1
            time_series["cpu_allocated"]["value"] += cpu_value
            time_series["mem_allocated"]["value"] += mem_value
            time_series["gpu_allocated"]["value"] += cuda_device_value
            time_series["gpu_allocated"]["value"] += cuda_share_value
            time_series["io_read_bytes"]["value"] += io_read_byte
            time_series["io_write_bytes"]["value"] += io_write_byte
            time_series["disk_used"]["value"] += disk_used

    # Change Decimal type to float to serialize to JSON
    for time_series in time_series_list:
        time_series["gpu_allocated"]["value"] = float(time_series["gpu_allocated"]["value"])
    return time_series_list


@server_status_required(READ_ALLOWED)
@auth_required
async def user_month_stats(request: web.Request) -> web.Response:
    """
    Return time-binned (15 min) stats for terminated user sessions
    over last 30 days.
    """
    access_key = request["keypair"]["access_key"]
    user_uuid = request["user"]["uuid"]
    log.info("USER_LAST_MONTH_STATS (ak:{}, u:{})", access_key, user_uuid)
    stats = await get_time_binned_monthly_stats(request, user_uuid=user_uuid)
    return web.json_response(stats, status=200)


@server_status_required(READ_ALLOWED)
@superadmin_required
async def admin_month_stats(request: web.Request) -> web.Response:
    """
    Return time-binned (15 min) stats for all terminated sessions
    over last 30 days.
    """
    log.info("ADMIN_LAST_MONTH_STATS ()")
    stats = await get_time_binned_monthly_stats(request, user_uuid=None)
    return web.json_response(stats, status=200)


async def get_watcher_info(request: web.Request, agent_id: str) -> dict:
    """
    Get watcher information.

    :return addr: address of agent watcher (eg: http://127.0.0.1:6009)
    :return token: agent watcher token ("insecure" if not set in config server)
    """
    root_ctx: RootContext = request.app["_root.context"]
    token = root_ctx.shared_config["watcher"]["token"]
    if token is None:
        token = "insecure"
    agent_ip = await root_ctx.shared_config.etcd.get(f"nodes/agents/{agent_id}/ip")
    raw_watcher_port = await root_ctx.shared_config.etcd.get(
        f"nodes/agents/{agent_id}/watcher_port",
    )
    watcher_port = 6099 if raw_watcher_port is None else int(raw_watcher_port)
    # TODO: watcher scheme is assumed to be http
    addr = yarl.URL(f"http://{agent_ip}:{watcher_port}")
    return {
        "addr": addr,
        "token": token,
    }


@server_status_required(READ_ALLOWED)
@superadmin_required
@check_api_params(
    t.Dict({
        tx.AliasedKey(["agent_id", "agent"]): t.String,
    })
)
async def get_watcher_status(request: web.Request, params: Any) -> web.Response:
    log.info("GET_WATCHER_STATUS (ag:{})", params["agent_id"])
    watcher_info = await get_watcher_info(request, params["agent_id"])
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as sess:
        with _timeout(5.0):
            headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
            async with sess.get(watcher_info["addr"], headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return web.json_response(data, status=resp.status)
                else:
                    data = await resp.text()
                    return web.Response(text=data, status=resp.status)


@server_status_required(READ_ALLOWED)
@superadmin_required
@check_api_params(
    t.Dict({
        tx.AliasedKey(["agent_id", "agent"]): t.String,
    })
)
async def watcher_agent_start(request: web.Request, params: Any) -> web.Response:
    log.info("WATCHER_AGENT_START (ag:{})", params["agent_id"])
    watcher_info = await get_watcher_info(request, params["agent_id"])
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as sess:
        with _timeout(20.0):
            watcher_url = watcher_info["addr"] / "agent/start"
            headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
            async with sess.post(watcher_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return web.json_response(data, status=resp.status)
                else:
                    data = await resp.text()
                    return web.Response(text=data, status=resp.status)


@server_status_required(READ_ALLOWED)
@superadmin_required
@check_api_params(
    t.Dict({
        tx.AliasedKey(["agent_id", "agent"]): t.String,
    })
)
async def watcher_agent_stop(request: web.Request, params: Any) -> web.Response:
    log.info("WATCHER_AGENT_STOP (ag:{})", params["agent_id"])
    watcher_info = await get_watcher_info(request, params["agent_id"])
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as sess:
        with _timeout(20.0):
            watcher_url = watcher_info["addr"] / "agent/stop"
            headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
            async with sess.post(watcher_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return web.json_response(data, status=resp.status)
                else:
                    data = await resp.text()
                    return web.Response(text=data, status=resp.status)


@server_status_required(READ_ALLOWED)
@superadmin_required
@check_api_params(
    t.Dict({
        tx.AliasedKey(["agent_id", "agent"]): t.String,
    })
)
async def watcher_agent_restart(request: web.Request, params: Any) -> web.Response:
    log.info("WATCHER_AGENT_RESTART (ag:{})", params["agent_id"])
    watcher_info = await get_watcher_info(request, params["agent_id"])
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as sess:
        with _timeout(20.0):
            watcher_url = watcher_info["addr"] / "agent/restart"
            headers = {"X-BackendAI-Watcher-Token": watcher_info["token"]}
            async with sess.post(watcher_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return web.json_response(data, status=resp.status)
                else:
                    data = await resp.text()
                    return web.Response(text=data, status=resp.status)


@superadmin_required
async def get_container_registries(request: web.Request) -> web.Response:
    """
    Returns the list of all registered container registries.
    """
    root_ctx: RootContext = request.app["_root.context"]
    async with root_ctx.db.begin_session() as session:
        _registries = await ContainerRegistryRow.get_known_container_registries(session)

    known_registries = {}
    for project, registries in _registries.items():
        for registry_name, url in registries.items():
            if project not in known_registries:
                known_registries[f"{project}/{registry_name}"] = url.human_repr()

    return web.json_response(known_registries, status=200)


def create_app(
    default_cors_options: CORSOptions,
) -> Tuple[web.Application, Iterable[WebMiddleware]]:
    app = web.Application()
    app["api_versions"] = (4,)
    app["prefix"] = "resource"
    cors = aiohttp_cors.setup(app, defaults=default_cors_options)
    add_route = app.router.add_route
    cors.add(add_route("GET", "/presets", list_presets))
    cors.add(add_route("GET", "/container-registries", get_container_registries))
    cors.add(add_route("POST", "/check-presets", check_presets))
    cors.add(add_route("POST", "/recalculate-usage", recalculate_usage))
    cors.add(add_route("GET", "/usage/month", usage_per_month))
    cors.add(add_route("GET", "/usage/period", usage_per_period))
    cors.add(add_route("GET", "/stats/user/month", user_month_stats))
    cors.add(add_route("GET", "/stats/admin/month", admin_month_stats))
    cors.add(add_route("GET", "/watcher", get_watcher_status))
    cors.add(add_route("POST", "/watcher/agent/start", watcher_agent_start))
    cors.add(add_route("POST", "/watcher/agent/stop", watcher_agent_stop))
    cors.add(add_route("POST", "/watcher/agent/restart", watcher_agent_restart))
    return app, []
