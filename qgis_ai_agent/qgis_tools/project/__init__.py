from qgis_ai_agent.qgis_tools.project.add_basemap import AddBasemapTool
from qgis_ai_agent.qgis_tools.project.add_db_layer import AddDbLayerTool
from qgis_ai_agent.qgis_tools.project.add_layer import AddLayerTool
from qgis_ai_agent.qgis_tools.project.add_service_layer import AddServiceLayerTool
from qgis_ai_agent.qgis_tools.project.configure_layer import ConfigureLayerTool
from qgis_ai_agent.qgis_tools.project.configure_project import ConfigureProjectTool
from qgis_ai_agent.qgis_tools.project.export_layer import ExportLayerTool
from qgis_ai_agent.qgis_tools.project.list_db_connections import ListDbConnectionsTool
from qgis_ai_agent.qgis_tools.project.list_db_tables import ListDbTablesTool
from qgis_ai_agent.qgis_tools.project.remove_layer import RemoveLayerTool
from qgis_ai_agent.qgis_tools.project.save_project import SaveProjectTool
from qgis_ai_agent.qgis_tools.project.undo_last_apply import UndoLastApplyTool
from qgis_ai_agent.qgis_tools.project.views import ListViewsTool, SaveBookmarkTool, SaveMapThemeTool
from qgis_ai_agent.qgis_tools.project.zoom_to_layer import ZoomToLayerTool

PROJECT_TOOLS = [
    ZoomToLayerTool(),
    AddLayerTool(),
    AddBasemapTool(),
    AddServiceLayerTool(),
    ListDbConnectionsTool(),
    ListDbTablesTool(),
    AddDbLayerTool(),
    RemoveLayerTool(),
    ConfigureLayerTool(),
    ConfigureProjectTool(),
    SaveProjectTool(),
    ExportLayerTool(),
    UndoLastApplyTool(),
    ListViewsTool(),
    SaveBookmarkTool(),
    SaveMapThemeTool(),
]
