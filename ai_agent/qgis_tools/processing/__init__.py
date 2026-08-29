from ai_agent.qgis_tools.processing.describe_processing import DescribeProcessingTool
from ai_agent.qgis_tools.processing.run_processing import RunProcessingTool
from ai_agent.qgis_tools.processing.search_processing import SearchProcessingTool

PROCESSING_TOOLS = [
    SearchProcessingTool(),
    DescribeProcessingTool(),
    RunProcessingTool(),
]
