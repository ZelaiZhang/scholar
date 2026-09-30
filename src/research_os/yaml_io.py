"""Safe YAML parsing that never silently overwrites a duplicate mapping key."""

from __future__ import annotations

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


class UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False):
        if not isinstance(node, MappingNode):
            return super().construct_mapping(node, deep=deep)
        self.flatten_mapping(node)
        seen: set[object] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    "found unhashable key", key_node.start_mark,
                ) from exc
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"found duplicate key {key!r}", key_node.start_mark,
                )
        return super().construct_mapping(node, deep=deep)


def load_yaml(text: str) -> object:
    """Parse data with SafeLoader types and reject ambiguous duplicate keys."""
    return yaml.load(text, Loader=UniqueKeySafeLoader)
