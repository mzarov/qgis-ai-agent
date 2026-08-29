import unittest

from ai_agent.qgis_tools.project import configure_layer as module
from ai_agent.qgis_tools.project import reorder_layers as reorder_module
from ai_agent.qgis_tools.project.reorder_layers import ReorderLayersTool

LAYER_ID = "roads_2024"


class Registry:
    def __init__(self):
        self.alive = {LAYER_ID}

    def on_removed(self, tree, layer_id):
        if tree.find(layer_id) is None:
            self.alive.discard(layer_id)


class Node:
    def __init__(self, layer_id, tree):
        self.layer_id = layer_id
        self._tree = tree
        self._parent = None

    def clone(self):
        return Node(self.layer_id, self._tree)

    def parent(self):
        return self._parent


class Group:
    def __init__(self, tree, name=""):
        self._tree = tree
        self._name = name
        self._children = []

    def children(self):
        return list(self._children)

    def insertChildNode(self, index, node):
        node._parent = self
        self._children.insert(index, node)

    def removeChildNode(self, node):
        self._children.remove(node)
        self._tree.registry.on_removed(self._tree, node.layer_id)


class Tree:
    def __init__(self):
        self.registry = Registry()
        self.root = Group(self)

    def find(self, layer_id):
        return self._find(self.root, layer_id)

    def _find(self, group, layer_id):
        for child in group._children:
            if isinstance(child, Group):
                found = self._find(child, layer_id)
                if found is not None:
                    return found
            elif child.layer_id == layer_id:
                return child
        return None


class MoveTest(unittest.TestCase):
    def setUp(self):
        self.tree = Tree()
        self.node = Node(LAYER_ID, self.tree)
        self.others = [Node(f"other_{index}", self.tree) for index in range(2)]
        self.tree.root.insertChildNode(0, self.node)
        for index, other in enumerate(self.others, 1):
            self.tree.root.insertChildNode(index, other)
        self.saved = module.parent_of
        module.parent_of = lambda node: node._parent

    def tearDown(self):
        module.parent_of = self.saved

    def _ids(self):
        return [child.layer_id for child in self.tree.root.children()]

    def test_the_layer_survives_the_move(self):
        module._move(object(), self.node, {"position": 2})
        self.assertIn(LAYER_ID, self.tree.registry.alive)

    def test_moving_down_lands_on_the_asked_position(self):
        module._move(object(), self.node, {"position": 2})
        self.assertEqual(self._ids(), ["other_0", "other_1", LAYER_ID])

    def test_moving_up_lands_on_the_asked_position(self):
        module._move(object(), self.others[1], {"position": 0})
        self.assertEqual(self._ids(), ["other_1", LAYER_ID, "other_0"])

    def test_the_position_is_clamped_to_the_children(self):
        module._move(object(), self.node, {"position": 99})
        self.assertEqual(self._ids()[-1], LAYER_ID)
        self.assertIn(LAYER_ID, self.tree.registry.alive)

    def test_a_negative_position_means_the_top(self):
        module._move(object(), self.others[0], {"position": -3})
        self.assertEqual(self._ids()[0], "other_0")

    def test_no_duplicate_is_left_behind(self):
        module._move(object(), self.node, {"position": 1})
        self.assertEqual(self._ids().count(LAYER_ID), 1)

    def test_moving_into_a_group_keeps_the_layer_alive(self):
        group = Group(self.tree, "Transport")
        self.tree.root.insertChildNode(3, group)
        saved = module.ensure_group
        module.ensure_group = lambda name: group
        try:
            module._move(object(), self.node, {"group": "Transport", "position": 0})
        finally:
            module.ensure_group = saved
        self.assertIn(LAYER_ID, self.tree.registry.alive)
        self.assertEqual([child.layer_id for child in group.children()], [LAYER_ID])


if __name__ == "__main__":
    unittest.main()


class FakeLayer:
    def __init__(self, node):
        self._node = node

    def name(self):
        return self._node.layer_id


class ReorderTest(unittest.TestCase):
    def setUp(self):
        self.tree = Tree()
        self.tree.registry.alive = set()
        self.nodes = {}
        for index, name in enumerate(("boundary", "parks", "roads", "osm", "cafes")):
            node = Node(name, self.tree)
            self.tree.registry.alive.add(name)
            self.tree.root.insertChildNode(index, node)
            self.nodes[name] = node
        self.saved = (
            reorder_module.layer_tree,
            reorder_module.parent_of,
            reorder_module.tree_node,
            reorder_module.find_layer,
        )
        reorder_module.layer_tree = lambda: self.tree.root
        reorder_module.parent_of = lambda node: node._parent
        reorder_module.tree_node = lambda layer: layer._node
        reorder_module.find_layer = lambda name: FakeLayer(self.nodes[name])
        self.tool = ReorderLayersTool()

    def tearDown(self):
        (
            reorder_module.layer_tree,
            reorder_module.parent_of,
            reorder_module.tree_node,
            reorder_module.find_layer,
        ) = self.saved

    def _ids(self):
        return [child.layer_id for child in self.tree.root.children()]

    def test_the_named_order_becomes_the_panel_order(self):
        self.tool.execute({"layer_names": ["cafes", "roads", "parks", "boundary", "osm"]})
        self.assertEqual(self._ids(), ["cafes", "roads", "parks", "boundary", "osm"])

    def test_every_layer_survives(self):
        self.tool.execute({"layer_names": ["cafes", "roads", "parks", "boundary", "osm"]})
        self.assertEqual(len(self.tree.registry.alive), 5)

    def test_unlisted_layers_stay_below_the_listed_ones(self):
        self.tool.execute({"layer_names": ["cafes", "roads"]})
        self.assertEqual(self._ids()[:2], ["cafes", "roads"])
        self.assertEqual(len(self._ids()), 5)

    def test_a_duplicate_name_is_refused(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_names": ["cafes", "Cafes"]})

    def test_an_empty_list_is_refused(self):
        with self.assertRaises(ValueError):
            self.tool.prepare({"layer_names": []})

    def test_the_summary_reads_top_to_bottom(self):
        summary = self.tool.summarize_call({"layer_names": ["cafes", "roads", "parks", "boundary", "osm"]})
        self.assertIn("cafes", summary)
        self.assertIn("…", summary)

    def test_summary_never_raises(self):
        self.assertTrue(self.tool.summarize_call({}).strip())
