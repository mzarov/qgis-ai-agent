from typing import Any

from ai_agent.i18n import tr
from ai_agent.qgis_tools.base import EGRESS_FEATURE_VALUES, SAFETY_READ, BaseTool
from ai_agent.qgis_tools.common.values import clamp_limit
from ai_agent.qgis_tools.tables.coordinates import guess_coordinates
from ai_agent.qgis_tools.tables.delimited import read_table

DEFAULT_ROWS = 5
MAX_ROWS = 20
MAX_CELL_CHARS = 80
LEADING_ZEROS_NOTE = (
    "Columns {0} hold codes with leading zeros; they are loaded as text so 007 stays 007. "
    "Join them only to a text field with the same zeros."
)
PROJECTED_NOTE = (
    "The coordinate values are not longitude/latitude degrees; load_table needs the crs they were written in."
)


class PreviewTableTool(BaseTool):
    name = "preview_table"
    description = (
        "Read the head of a CSV/TSV/TXT file without loading it: delimiter, encoding, columns with the "
        "types QGIS will give them, the first rows and the columns that look like coordinates."
    )
    skill = "tables"
    safety = SAFETY_READ
    egress = EGRESS_FEATURE_VALUES
    external_effect = False
    network_access = False
    constraints = ["The file must exist and end in .csv, .tsv or .txt"]
    examples = ["What columns does /data/population.csv have?"]
    params_schema = [
        {"name": "path", "type": "string", "description": "Path to the file", "required": True},
        {
            "name": "rows",
            "type": "integer",
            "description": f"Rows to show, {DEFAULT_ROWS} by default, at most {MAX_ROWS}",
            "required": False,
        },
        {
            "name": "delimiter",
            "type": "string",
            "description": "Force the delimiter: , ; tab or |. Detected when omitted.",
            "required": False,
        },
    ]

    def summarize_call(self, params: dict[str, Any]) -> str:
        return tr("Reading table file {0}.").format(str(params.get("path") or "").strip())

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        table = read_table(params.get("path") or "", str(params.get("delimiter") or ""))
        limit = clamp_limit(params.get("rows"), DEFAULT_ROWS, MAX_ROWS)
        result: dict[str, Any] = {
            "path": table.path,
            "delimiter": table.delimiter_name,
            "encoding": table.encoding,
            "columns": [{"name": column, "type": table.column_type(column)} for column in table.header],
            "rows": [[cell[:MAX_CELL_CHARS] for cell in row] for row in table.rows[:limit]],
        }
        if table.complete:
            result["row_count"] = len(table.rows)
        else:
            result["row_count_note"] = f"The file is large; the types come from its first {len(table.rows)} rows."
        if table.decimal_comma:
            result["decimal_comma"] = True
        notes = []
        codes = table.text_codes()
        if codes:
            notes.append(LEADING_ZEROS_NOTE.format(", ".join(codes)))
        coordinates = guess_coordinates(table)
        if coordinates.found:
            fields = {
                "x_field": coordinates.x_field,
                "y_field": coordinates.y_field,
                "wkt_field": coordinates.wkt_field,
            }
            result["coordinates"] = {key: value for key, value in fields.items() if value}
            result["coordinates"]["crs"] = coordinates.crs or None
            if not coordinates.crs:
                notes.append(PROJECTED_NOTE)
        if notes:
            result["notes"] = notes
        return result
