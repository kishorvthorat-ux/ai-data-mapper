import pandas as pd
from typing import List, Dict

class TransformationRegistry:
    """Hardcoded safe transformations. No eval() used."""
    
    @staticmethod
    def direct(df: pd.DataFrame, source_col: str, **kwargs) -> pd.Series:
        return df[source_col]

    @staticmethod
    def enum_map(df: pd.DataFrame, source_col: str, mapping: dict, **kwargs) -> pd.Series:
        return df[source_col].map(mapping)

    @staticmethod
    def concat(df: pd.DataFrame, source_cols: list, delimiter: str = " ", **kwargs) -> pd.Series:
        return df[source_cols].astype(str).agg(delimiter.join, axis=1)
        
    @staticmethod
    def static_default(df: pd.DataFrame, value: str, **kwargs) -> pd.Series:
        return pd.Series([value] * len(df), index=df.index)

def apply_mappings(df_source: pd.DataFrame, final_mappings: List[Dict]) -> pd.DataFrame:
    """Executes the approved mapping rules against a dataframe."""
    df_target = pd.DataFrame()
    
    for rule in final_mappings:
        target = rule["target_field"]
        func_name = rule["transformation_type"]
        params = rule["parameters"]
        
        if func_name == "unmapped":
            continue # Skip unmapped fields
            
        # Dynamically fetch the function from the registry class
        if hasattr(TransformationRegistry, func_name):
            func = getattr(TransformationRegistry, func_name)
            try:
                df_target[target] = func(df=df_source, **params)
            except Exception as e:
                print(f"❌ Execution failed for '{target}' using {func_name}: {e}")
        else:
            raise ValueError(f"CRITICAL: Transformation '{func_name}' is not registered.")
            
    return df_target