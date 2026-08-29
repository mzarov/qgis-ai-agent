from qgis_ai_agent.qgis_tools.annotations.add_annotation import AddAnnotationTool
from qgis_ai_agent.qgis_tools.annotations.manage_annotations import ListAnnotationsTool, RemoveAnnotationTool

ANNOTATIONS_TOOLS = [
    AddAnnotationTool(),
    ListAnnotationsTool(),
    RemoveAnnotationTool(),
]
