from qgis_ai_agent.qgis_tools.project.add_layer import AddLayerTool
from qgis_ai_agent.qgis_tools.project.configure_layer import ConfigureLayerTool
from qgis_ai_agent.qgis_tools.project.configure_project import ConfigureProjectTool
from qgis_ai_agent.qgis_tools.project.remove_layer import RemoveLayerTool
from qgis_ai_agent.qgis_tools.project.save_project import SaveProjectTool
from qgis_ai_agent.qgis_tools.project.zoom_to_layer import ZoomToLayerTool

PROJECT_TOOLS = [
    ZoomToLayerTool(),
    AddLayerTool(),
    RemoveLayerTool(),
    ConfigureLayerTool(),
    ConfigureProjectTool(),
    SaveProjectTool(),
]
