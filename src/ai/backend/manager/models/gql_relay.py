from __future__ import annotations

import enum
import functools
import re
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import (
    Any,
    Generic,
    NamedTuple,
    Protocol,
    TypeAlias,
    TypeVar,
)

import graphene
import graphql
from graphene.relay.connection import (
    ConnectionOptions,
    IterableConnectionField,
    PageInfo,
)
from graphene.relay.node import Node, NodeField, is_node
from graphene.types import Field, NonNull, ObjectType, String
from graphene.types.objecttype import ObjectTypeMeta
from graphene.types.utils import get_type
from graphql_relay.utils import base64, unbase64


def get_edge_class(
    connection_class: type[Connection],
    _node: type[AsyncNode],
    base_name: str,
    strict_types: bool = False,
    description: str | None = None,
) -> ObjectTypeMeta:
    edge_class = getattr(connection_class, "Edge", None)

    class EdgeBase:
        node = Field(
            NonNull(_node) if strict_types else _node,
            description="The item at the end of the edge",
        )
        cursor = String(required=True, description="A cursor for use in pagination")

    edge_description = f"A Relay edge containing a `{base_name}` and its cursor."
    if description is not None:
        edge_description = f"{description} {edge_description}"

    class EdgeMeta:
        description = edge_description

    edge_name = f"{base_name}Edge"

    edge_bases = [edge_class, EdgeBase] if edge_class else [EdgeBase]
    if not isinstance(edge_class, ObjectType):
        edge_bases = [*edge_bases, ObjectType]

    return type(edge_name, tuple(edge_bases), {"Meta": EdgeMeta})


class PageInfoType(Protocol):
    @property
    def start_cursor(self) -> str | None: ...

    @property
    def end_cursor(self) -> str | None: ...

    @property
    def has_previous_page(self) -> bool: ...

    @property
    def has_next_page(self) -> bool: ...


class EdgeType(Protocol):
    @property
    def node(self) -> Any: ...

    @property
    def cursor(self) -> str: ...


class ConnectionType(Protocol):
    @property
    def edges(self) -> list[EdgeType]: ...

    @property
    def page_info(self) -> PageInfoType: ...


class EdgeConstructor(Protocol):
    def __call__(
        self,
        *,
        node: Any,
        cursor: str,
    ) -> EdgeType: ...


class ConnectionConstructor(Protocol):
    @property
    def Edge(self) -> EdgeConstructor: ...

    def __call__(
        self,
        *,
        edges: list[EdgeType],
        page_info: PageInfoType,
        count: int,
    ) -> Connection: ...


class AsyncNodeField(NodeField):
    def wrap_resolve(self, parent_resolver):
        return functools.partial(self.node_type.node_resolver, get_type(self.field_type))


def _resolve_global_id(global_id: str) -> tuple[str, str]:
    unbased_global_id = unbase64(global_id)
    type_, _, id_ = unbased_global_id.partition(":")
    return type_, id_


class AsyncNode(Node):
    """
    This GraphQL Relay Node extension is for running asynchronous resolvers and fine-grained handling of global id.
    Refer to: https://github.com/graphql-python/graphene/blob/master/graphene/relay/node.py
    """

    class Meta:
        name = "Node"

    @classmethod
    def Field(cls, *args, **kwargs):
        return AsyncNodeField(cls, *args, **kwargs)

    @classmethod
    async def node_resolver(cls, only_type, root, info, id):
        return await cls.get_node_from_global_id(info, id, only_type=only_type)

    @staticmethod
    def to_global_id(type_, id_) -> str:
        if id_ is None:
            raise Exception("Encoding None value as Global ID is not allowed.")
        return base64(f"{type_}:{id_}")

    @classmethod
    def resolve_global_id(cls, info, global_id: str) -> tuple[str, str]:
        return _resolve_global_id(global_id)

    @classmethod
    async def get_node_from_global_id(cls, info, global_id: str, only_type=None) -> Any:
        _type, _ = cls.resolve_global_id(info, global_id)

        graphene_type = info.schema.get_type(_type)
        if graphene_type is None:
            raise Exception(f'Relay Node "{_type}" not found in schema')

        graphene_type = graphene_type.graphene_type

        if only_type:
            assert graphene_type == only_type, f"Must receive a {only_type._meta.name} id."

        if cls not in graphene_type._meta.interfaces:
            raise Exception(f'ObjectType "{_type}" does not implement the "{cls}" interface.')

        get_node = getattr(graphene_type, "get_node", None)
        if get_node:
            return await get_node(info, global_id)
        raise Exception(f'ObjectType "{_type}" does not implement `get_node` method.')


class Connection(graphene.ObjectType):
    """
    This GraphQL Relay Connection has been implemented to have additional fields, such as `count`.
    Refer to: https://github.com/graphql-python/graphene/blob/master/graphene/relay/connection.py
    """

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls, node=None, name=None, strict_types=False, _meta=None, **options
    ):
        if not _meta:
            _meta = ConnectionOptions(cls)
        assert node, f"You have to provide a node in {cls.__name__}.Meta"
        assert isinstance(node, graphene.NonNull) or issubclass(
            node,
            (
                graphene.Scalar,
                graphene.Enum,
                graphene.ObjectType,
                graphene.Interface,
                graphene.Union,
                graphene.NonNull,
            ),
        ), f'Received incompatible node "{node}" for Connection {cls.__name__}.'

        base_name = re.sub("Connection$", "", name or cls.__name__) or node._meta.name
        if not name:
            name = f"{base_name}Connection"

        options["name"] = name

        _meta.node = node

        if not _meta.fields:
            _meta.fields = {}

        if "page_info" not in _meta.fields:
            _meta.fields["page_info"] = graphene.Field(
                PageInfo,
                name="pageInfo",
                required=True,
                description="Pagination data for this connection.",
            )

        if "edges" not in _meta.fields:
            connection_description = options.get("description")
            edge_class = get_edge_class(cls, node, base_name, strict_types, connection_description)  # type: ignore
            cls.Edge = edge_class
            _meta.fields["edges"] = graphene.Field(
                graphene.NonNull(
                    graphene.List(graphene.NonNull(edge_class) if strict_types else edge_class)
                ),
                description="Contains the nodes in this connection.",
            )

        if "count" not in _meta.fields:
            _meta.fields["count"] = graphene.Field(
                graphene.Int(),
                name="count",
                description="Total count of the GQL nodes of the query.",
            )

        return super().__init_subclass_with_meta__(_meta=_meta, **options)


class ConnectionPaginationOrder(enum.Enum):
    FORWARD = "forward"
    BACKWARD = "backward"


T_Node = TypeVar("T_Node", bound=ObjectType)


class ConnectionResolverResult(Generic[T_Node], NamedTuple):
    node_list: list[T_Node] | Connection
    cursor: str | None
    pagination_order: ConnectionPaginationOrder | None
    requested_page_size: int | None
    total_count: int


Resolver = (
    Callable[..., Awaitable[ConnectionResolverResult]] | Callable[..., ConnectionResolverResult]
)


class AsyncListConnectionField(IterableConnectionField):
    """
    This GraphQL Relay Connection field extension is for getting paginated list data from asynchronous resolvers.
    The resolver function of graphene.relay.Connection is implemented
    to accept only one complete array (Iterable values) without considering pagination, which is a huge performance issue.
    Refer to: https://github.com/graphql-python/graphene/blob/master/graphene/relay/connection.py
    """

    @property
    def type(self):
        type_ = super(IterableConnectionField, self).type
        connection_type = type_
        if isinstance(type_, graphene.NonNull):
            connection_type = type_.of_type

        if is_node(connection_type):
            raise Exception("ConnectionFields now need a explicit ConnectionType for Nodes.")

        assert issubclass(connection_type, Connection), (
            f"{self.__class__.__name__} type has to be a subclass of"
            f' ai.backend.manager.models.gql_relay.Connection. Received "{connection_type}".'
        )
        return type_

    @classmethod
    def resolve_connection(
        cls,
        connection_type: ConnectionConstructor,
        args: dict[str, Any] | None,
        resolver_result: ConnectionResolverResult,
    ) -> Connection:
        resolved = resolver_result.node_list
        page_size = resolver_result.requested_page_size
        pagination_order = resolver_result.pagination_order
        count = resolver_result.total_count

        if isinstance(resolved, Connection):
            return resolved

        assert isinstance(resolved, list), (
            "Resolved value from the connection field has to be a list or instance of"
            f' {connection_type}. Received "{resolved}"'
        )

        orig_resolved_len = len(resolved)
        if page_size is not None:
            resolved = resolved[:page_size]
        if pagination_order == ConnectionPaginationOrder.BACKWARD:
            resolved = resolved[::-1]
        edge_type = connection_type.Edge
        edges = [
            edge_type(
                node=value,
                cursor=AsyncNode.to_global_id(str(connection_type._meta.node), value.id),  # type: ignore[attr-defined]
            )
            for value in resolved
        ]
        return connection_type(
            edges=edges,
            page_info=PageInfo(
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
                has_previous_page=(
                    pagination_order == ConnectionPaginationOrder.BACKWARD
                    and page_size is not None
                    and page_size < orig_resolved_len
                ),
                has_next_page=(
                    pagination_order == ConnectionPaginationOrder.FORWARD
                    and page_size is not None
                    and page_size < orig_resolved_len
                ),
            ),
            count=count,
        )

    @classmethod
    async def connection_resolver(
        cls,
        resolver: Resolver,
        connection_type: ConnectionConstructor,
        root,
        info,
        **args,
    ) -> Connection:
        _result = resolver(root, info, **args)
        match _result:
            case ConnectionResolverResult():
                result = _result
            case _:
                result = await _result

        if isinstance(connection_type, graphene.NonNull):
            connection_type = connection_type.of_type

        return cls.resolve_connection(
            connection_type,
            args,
            resolver_result=result,
        )


ConnectionField = AsyncListConnectionField

NodeTypeName: TypeAlias = str
NodeID: TypeAlias = str
ResolvedGlobalID: TypeAlias = tuple[NodeTypeName, NodeID]


def _from_str(value: str) -> ResolvedGlobalID:
    type_, id_ = _resolve_global_id(value)
    if not id_:
        return type_, value
    return type_, id_


class GlobalIDField(graphene.Scalar):
    class Meta:
        description = (
            "Added in 24.09.0. Global ID of GQL relay spec. "
            'Base64 encoded version of "<node type name>:<node id>". '
            "UUID or string type values are also allowed."
        )

    @staticmethod
    def serialize(val: Any) -> Any:
        return val

    @staticmethod
    def parse_literal(node: Any, _variables=None) -> ResolvedGlobalID | None:
        if isinstance(node, graphql.language.ast.StringValueNode):
            return _from_str(node.value)
        return None

    @staticmethod
    def parse_value(value: str) -> ResolvedGlobalID:
        return _from_str(value)
