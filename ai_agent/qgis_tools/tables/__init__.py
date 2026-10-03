from ai_agent.qgis_tools.tables.join_table import JoinTableTool
from ai_agent.qgis_tools.tables.list_joins import ListJoinsTool
from ai_agent.qgis_tools.tables.load_table import LoadTableTool
from ai_agent.qgis_tools.tables.preview_table import PreviewTableTool
from ai_agent.qgis_tools.tables.remove_join import RemoveJoinTool

TABLES_TOOLS = [
    PreviewTableTool(),
    LoadTableTool(),
    JoinTableTool(),
    ListJoinsTool(),
    RemoveJoinTool(),
]
