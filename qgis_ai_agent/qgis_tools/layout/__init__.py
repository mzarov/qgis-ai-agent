from qgis_ai_agent.qgis_tools.layout.add_layout_item import AddLayoutItemTool
from qgis_ai_agent.qgis_tools.layout.configure_layout_item import ConfigureLayoutItemTool
from qgis_ai_agent.qgis_tools.layout.create_layout import CreateLayoutTool
from qgis_ai_agent.qgis_tools.layout.describe_layout import DescribeLayoutTool
from qgis_ai_agent.qgis_tools.layout.export_layout import ExportLayoutTool
from qgis_ai_agent.qgis_tools.layout.list_layouts import ListLayoutsTool
from qgis_ai_agent.qgis_tools.layout.remove_layout_item import RemoveLayoutItemTool
from qgis_ai_agent.qgis_tools.layout.render_layout import RenderLayoutTool

LAYOUT_TOOLS = [
    ListLayoutsTool(),
    DescribeLayoutTool(),
    RenderLayoutTool(),
    CreateLayoutTool(),
    AddLayoutItemTool(),
    ConfigureLayoutItemTool(),
    RemoveLayoutItemTool(),
    ExportLayoutTool(),
]
