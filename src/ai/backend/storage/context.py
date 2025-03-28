from __future__ import annotations

import logging
from contextlib import asynccontextmanager as actxmgr
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Final,
    Mapping,
    Optional,
    Type,
)

import aiohttp_cors
from aiohttp import web
from aiohttp.typedefs import Middleware

from ai.backend.common.defs import NOOP_STORAGE_VOLUME_NAME
from ai.backend.common.etcd import AsyncEtcd
from ai.backend.common.events import (
    EventDispatcher,
    EventProducer,
)
from ai.backend.common.metrics.metric import CommonMetricRegistry
from ai.backend.logging import BraceStyleAdapter

from .api.client import init_client_app
from .api.manager import init_internal_app, init_manager_app
from .exception import InvalidVolumeError
from .plugin import (
    BasePluginContext,
    StorageClientWebappPluginContext,
    StorageManagerWebappPluginContext,
    StoragePluginContext,
)
from .services.service import VolumeService
from .types import VolumeInfo
from .volumes.abc import AbstractVolume
from .volumes.cephfs import CephFSVolume
from .volumes.ddn import EXAScalerFSVolume
from .volumes.dellemc import DellEMCOneFSVolume
from .volumes.gpfs import GPFSVolume
from .volumes.netapp import NetAppVolume
from .volumes.noop import NoopVolume, init_noop_volume
from .volumes.pool import VolumePool
from .volumes.purestorage import FlashBladeVolume
from .volumes.vast import VASTVolume
from .volumes.vfs import BaseVolume
from .volumes.weka import WekaVolume
from .volumes.xfs import XfsVolume
from .watcher import WatcherClient

log = BraceStyleAdapter(logging.getLogger(__spec__.name))

EVENT_DISPATCHER_CONSUMER_GROUP: Final = "storage-proxy"

DEFAULT_BACKENDS: Mapping[str, Type[AbstractVolume]] = {
    FlashBladeVolume.name: FlashBladeVolume,
    BaseVolume.name: BaseVolume,
    XfsVolume.name: XfsVolume,
    NetAppVolume.name: NetAppVolume,
    # NOTE: Dell EMC has two different storage: PowerStore and PowerScale (OneFS).
    #       We support the latter only for now.
    DellEMCOneFSVolume.name: DellEMCOneFSVolume,
    WekaVolume.name: WekaVolume,
    GPFSVolume.name: GPFSVolume,  # IBM SpectrumScale or GPFS
    "spectrumscale": GPFSVolume,  # IBM SpectrumScale or GPFS
    CephFSVolume.name: CephFSVolume,
    VASTVolume.name: VASTVolume,
    EXAScalerFSVolume.name: EXAScalerFSVolume,
    NoopVolume.name: NoopVolume,
}


async def on_prepare(request: web.Request, response: web.StreamResponse) -> None:
    response.headers["Server"] = "BackendAI"


def _init_subapp(
    pkg_name: str,
    root_app: web.Application,
    subapp: web.Application,
    global_middlewares: list[Middleware],
) -> None:
    subapp.on_response_prepare.append(on_prepare)

    async def _set_root_ctx(subapp: web.Application):
        # Allow subapp's access to the root app properties.
        # These are the public APIs exposed to plugins as well.
        subapp["ctx"] = root_app["ctx"]

    # We must copy the public interface prior to all user-defined startup signal handlers.
    subapp.on_startup.insert(0, _set_root_ctx)
    if "prefix" not in subapp:
        subapp["prefix"] = pkg_name.split(".")[-1].replace("_", "-")
    prefix = subapp["prefix"]
    root_app.add_subapp("/" + prefix, subapp)
    root_app.middlewares.extend(global_middlewares)


class ServiceContext:
    volume_service: VolumeService

    def __init__(
        self,
        local_config: Mapping[str, Any],
        etcd: AsyncEtcd,
        event_dispatcher: EventDispatcher,
        event_producer: EventProducer,
    ) -> None:
        volume_pool = VolumePool(
            local_config=local_config,
            etcd=etcd,
            event_dispatcher=event_dispatcher,
            event_producer=event_producer,
        )
        self.volume_service = VolumeService(volume_pool)


class RootContext:
    volumes: dict[str, AbstractVolume]
    pid: int
    etcd: AsyncEtcd
    local_config: Mapping[str, Any]
    dsn: str | None
    event_producer: EventProducer
    event_dispatcher: EventDispatcher
    watcher: WatcherClient | None
    service_context: ServiceContext
    metric_registry: CommonMetricRegistry

    def __init__(
        self,
        pid: int,
        pidx: int,
        node_id: str,
        local_config: Mapping[str, Any],
        etcd: AsyncEtcd,
        *,
        event_producer: EventProducer,
        event_dispatcher: EventDispatcher,
        watcher: WatcherClient | None,
        dsn: Optional[str] = None,
        metric_registry: CommonMetricRegistry = CommonMetricRegistry.instance(),
    ) -> None:
        self.volumes = {
            NOOP_STORAGE_VOLUME_NAME: init_noop_volume(etcd, event_dispatcher, event_producer)
        }
        self.pid = pid
        self.pidx = pidx
        self.node_id = node_id
        self.etcd = etcd
        self.local_config = local_config
        self.dsn = dsn
        self.event_producer = event_producer
        self.event_dispatcher = event_dispatcher
        self.watcher = watcher
        self.cors_options = {
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=False, expose_headers="*", allow_headers="*"
            ),
        }
        self.service_context = ServiceContext(
            local_config=self.local_config,
            etcd=self.etcd,
            event_dispatcher=self.event_dispatcher,
            event_producer=self.event_producer,
        )
        self.metric_registry = metric_registry

    async def __aenter__(self) -> None:
        # TODO: Setup the apps outside of the context.
        self.client_api_app = await init_client_app(self)
        self.manager_api_app = await init_manager_app(self)
        self.internal_api_app = init_internal_app()
        self.backends = {
            **DEFAULT_BACKENDS,
        }
        await self.init_storage_plugin()
        self.manager_webapp_plugin_ctx = await self.init_storage_webapp_plugin(
            StorageManagerWebappPluginContext(self.etcd, self.local_config),
            self.manager_api_app,
        )
        self.client_webapp_plugin_ctx = await self.init_storage_webapp_plugin(
            StorageClientWebappPluginContext(self.etcd, self.local_config),
            self.client_api_app,
        )

    async def init_storage_plugin(self) -> None:
        plugin_ctx = StoragePluginContext(self.etcd, self.local_config)
        await plugin_ctx.init()
        self.storage_plugin_ctx = plugin_ctx
        for plugin_name, plugin_instance in plugin_ctx.plugins.items():
            log.info("Loading storage plugin: {0}", plugin_name)
            volume_cls = plugin_instance.get_volume_class()
            self.backends[plugin_name] = volume_cls

    async def init_storage_webapp_plugin(
        self, plugin_ctx: BasePluginContext, root_app: web.Application
    ) -> BasePluginContext:
        await plugin_ctx.init()
        for plugin_name, plugin_instance in plugin_ctx.plugins.items():
            if self.pid == 0:
                log.info("Loading storage webapp plugin: {0}", plugin_name)
            subapp, global_middlewares = await plugin_instance.create_app(self.cors_options)
            _init_subapp(plugin_name, root_app, subapp, global_middlewares)
        return plugin_ctx

    def list_volumes(self) -> Mapping[str, VolumeInfo]:
        return {name: VolumeInfo(**info) for name, info in self.local_config["volume"].items()}

    async def __aexit__(self, *exc_info) -> Optional[bool]:
        for volume in self.volumes.values():
            await volume.shutdown()

        await self.storage_plugin_ctx.cleanup()
        await self.manager_webapp_plugin_ctx.cleanup()
        await self.client_webapp_plugin_ctx.cleanup()
        return None

    @actxmgr
    async def get_volume(self, name: str) -> AsyncIterator[AbstractVolume]:
        if name in self.volumes:
            yield self.volumes[name]
        else:
            try:
                volume_config = self.local_config["volume"][name]
            except KeyError:
                raise InvalidVolumeError(name)
            volume_cls: Type[AbstractVolume] = self.backends[volume_config["backend"]]
            volume_obj = volume_cls(
                local_config=self.local_config,
                mount_path=Path(volume_config["path"]),
                options=volume_config["options"] or {},
                etcd=self.etcd,
                event_dispatcher=self.event_dispatcher,
                event_producer=self.event_producer,
                watcher=self.watcher,
            )

            await volume_obj.init()
            self.volumes[name] = volume_obj

            yield volume_obj
