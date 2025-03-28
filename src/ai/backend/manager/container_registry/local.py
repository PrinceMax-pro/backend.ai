from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager as actxmgr
from typing import AsyncIterator, override

import aiohttp
import sqlalchemy as sa
import yarl

from ai.backend.common.docker import arch_name_aliases, get_docker_connector
from ai.backend.logging import BraceStyleAdapter

from ..models.image import ImageRow, ImageStatus
from .base import (
    BaseContainerRegistry,
    concurrency_sema,
    progress_reporter,
)

log = BraceStyleAdapter(logging.getLogger(__spec__.name))


class LocalRegistry(BaseContainerRegistry):
    @actxmgr
    async def prepare_client_session(self) -> AsyncIterator[tuple[yarl.URL, aiohttp.ClientSession]]:
        connector = get_docker_connector()
        async with aiohttp.ClientSession(connector=connector.connector) as sess:
            yield connector.docker_host, sess

    @override
    async def fetch_repositories(
        self,
        sess: aiohttp.ClientSession,
    ) -> AsyncIterator[str]:
        async with sess.get(self.registry_url / "images" / "json") as response:
            items = await response.json()
            if (reporter := progress_reporter.get()) is not None:
                reporter.total_progress = len(items)
            for item in items:
                if item["RepoTags"] is not None:
                    for image_ref_str in item["RepoTags"]:
                        if image_ref_str == "<none>:<none>":
                            # cache images
                            continue
                        yield image_ref_str  # this includes the tag part

    @override
    async def _scan_image(
        self,
        sess: aiohttp.ClientSession,
        image: str,
    ) -> None:
        repo, _, tag = image.rpartition(":")
        await self._scan_tag_local(sess, {}, repo, tag)

    async def _scan_tag_local(
        self,
        sess: aiohttp.ClientSession,
        rqst_args: dict[str, str],
        image: str,
        tag: str,
    ) -> None:
        async def _read_image_info(
            _tag: str,
        ) -> tuple[dict[str, dict], str | None]:
            async with sess.get(
                self.registry_url / "images" / f"{image}:{tag}" / "json"
            ) as response:
                data = await response.json()
            architecture = arch_name_aliases.get(data["Architecture"], data["Architecture"])
            summary = {
                "Id": data["Id"],
                "RepoDigests": data.get("RepoDigests", []),
                "Config.Image": data["Config"]["Image"],
                "ContainerConfig.Image": data.get("ContainerConfig", {}).get("Image", None),
                "Architecture": architecture,
            }
            log.debug("scanned image info: {}:{}\n{}", image, tag, json.dumps(summary, indent=2))
            already_exists = 0
            config_digest = data["Id"]
            async with self.db.begin_readonly_session() as db_session:
                already_exists = await db_session.scalar(
                    sa.select([sa.func.count(ImageRow.id)]).where(
                        sa.and_(
                            ImageRow.config_digest == config_digest,
                            ImageRow.is_local == sa.false(),
                            ImageRow.status == ImageStatus.ALIVE,
                        )
                    ),
                )
            if already_exists > 0:
                return {}, "already synchronized from a remote registry"
            labels = data["Config"]["Labels"]
            if labels is None:
                log.debug(
                    "The image {}:{}/{} has no metadata labels -> treating as vanilla image",
                    image,
                    tag,
                    architecture,
                )
                labels = {}
            return {
                architecture: {
                    "size": data["Size"],
                    "labels": labels,
                    "digest": config_digest,
                },
            }, None

        async with concurrency_sema.get():
            manifests, skip_reason = await _read_image_info(tag)
            await self._read_manifest(image, tag, manifests, skip_reason)
