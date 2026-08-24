from qgis_ai_agent.qgis_tools.processing.describe_processing import DescribeProcessingTool
from qgis_ai_agent.qgis_tools.processing.run_processing import RunProcessingTool
from qgis_ai_agent.qgis_tools.processing.search_processing import SearchProcessingTool

PROCESSING_TOOLS = [
    SearchProcessingTool(),
    DescribeProcessingTool(),
    RunProcessingTool(),
]
