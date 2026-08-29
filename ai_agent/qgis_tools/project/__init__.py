from ai_agent.qgis_tools.project.add_basemap import AddBasemapTool
from ai_agent.qgis_tools.project.add_db_layer import AddDbLayerTool
from ai_agent.qgis_tools.project.add_layer import AddLayerTool
from ai_agent.qgis_tools.project.add_service_layer import AddServiceLayerTool
from ai_agent.qgis_tools.project.configure_layer import ConfigureLayerTool
from ai_agent.qgis_tools.project.configure_project import ConfigureProjectTool
from ai_agent.qgis_tools.project.export_layer import ExportLayerTool
from ai_agent.qgis_tools.project.list_db_connections import ListDbConnectionsTool
from ai_agent.qgis_tools.project.list_db_tables import ListDbTablesTool
from ai_agent.qgis_tools.project.remember import ForgetTool, ListNotesTool, RememberTool
from ai_agent.qgis_tools.project.remove_layer import RemoveLayerTool
from ai_agent.qgis_tools.project.reorder_layers import ReorderLayersTool
from ai_agent.qgis_tools.project.save_project import SaveProjectTool
from ai_agent.qgis_tools.project.undo_last_apply import UndoLastApplyTool
from ai_agent.qgis_tools.project.views import ListViewsTool, SaveBookmarkTool, SaveMapThemeTool
from ai_agent.qgis_tools.project.zoom_to_layer import ZoomToLayerTool

PROJECT_TOOLS = [
    ZoomToLayerTool(),
    AddLayerTool(),
    AddBasemapTool(),
    AddServiceLayerTool(),
    ListDbConnectionsTool(),
    ListDbTablesTool(),
    AddDbLayerTool(),
    RemoveLayerTool(),
    ReorderLayersTool(),
    ConfigureLayerTool(),
    ConfigureProjectTool(),
    SaveProjectTool(),
    ExportLayerTool(),
    UndoLastApplyTool(),
    ListViewsTool(),
    RememberTool(),
    ListNotesTool(),
    ForgetTool(),
    SaveBookmarkTool(),
    SaveMapThemeTool(),
]
