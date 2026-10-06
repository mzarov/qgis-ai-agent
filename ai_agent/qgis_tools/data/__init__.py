from ai_agent.qgis_tools.data.find_open_data import FindOpenDataTool
from ai_agent.qgis_tools.data.load_dataset import LoadDatasetTool
from ai_agent.qgis_tools.data.load_imagery import LoadImageryTool
from ai_agent.qgis_tools.data.load_service import LoadServiceTool
from ai_agent.qgis_tools.data.search_imagery import SearchImageryTool

DATA_TOOLS = [
    FindOpenDataTool(),
    SearchImageryTool(),
    LoadImageryTool(),
    LoadDatasetTool(),
    LoadServiceTool(),
]
