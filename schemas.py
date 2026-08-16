from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Any

class FieldMapping(BaseModel):
    target_field: str = Field(description="Name of the target schema field.")
    transformation_type: Literal["direct", "enum_map", "concat", "static_default", "unmapped"] = Field(
        description="The function to apply."
    )
    parameters: Dict[str, Any] = Field(
        description="""
        Parameters for the function. Rules:
        - direct: {"source_col": "col_name"}
        - enum_map: {"source_col": "col_name", "mapping": {"Old": "New"}}
        - concat: {"source_cols": ["col1", "col2"], "delimiter": " "}
        - static_default: {"value": "static_string_or_number"}
        - unmapped: {}
        """
    )
    logic_description: str = Field(description="Plain English explanation of this mapping.")
    confidence_score: float = Field(description="Float between 0.0 and 1.0 indicating AI certainty.")

class MappingResult(BaseModel):
    mappings: List[FieldMapping]