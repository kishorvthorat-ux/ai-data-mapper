from pydantic import BaseModel, Field
from typing import Literal, List

class FieldMapping(BaseModel):
    target_field: str = Field(description="Name of the target schema field.")
    transformation_type: Literal["direct", "enum_map", "concat", "static_default", "calculated", "regex", "unmapped"] = Field(
        description="The function to apply."
    )
    parameters_json: str = Field(
        description="""
        A valid JSON string containing parameters. Rules:
        - direct: '{"source_col": "col_name"}'
        - enum_map: '{"source_col": "col_name", "mapping": {"Old": "New"}}'
        - concat: '{"source_cols": ["col1", "col2"], "delimiter": " "}'
        - static_default: '{"value": "val"}'
        - calculated: '{"expression": "where(status == \\"1\\", \\"Active\\", \\"Inactive\\")"}'
        - regex: '{"source_col": "col_name", "operation": "extract", "pattern": "[0-9]+"}'
        - unmapped: '{}'
        """
    )
    logic_description: str = Field(description="Plain English explanation of this mapping.")
    confidence_score: float = Field(description="Float between 0.0 and 1.0 indicating AI certainty.")

class MappingResult(BaseModel):
    mappings: List[FieldMapping]
