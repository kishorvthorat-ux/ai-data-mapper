import pandas as pd
import numpy as np
from asteval import Interpreter
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
        # Convert columns to string, then join
        return df[source_cols].astype(str).agg(delimiter.join, axis=1)
        
    @staticmethod
    def static_default(df: pd.DataFrame, value: str, **kwargs) -> pd.Series:
        return pd.Series([value] * len(df), index=df.index)

    @staticmethod
    def calculated(df: pd.DataFrame, expression: str, **kwargs) -> pd.Series:
        """Securely evaluates math and if-else logic using asteval and numpy."""
        aeval = Interpreter()
        # Inject standard numpy logical functions
        aeval.symtable['where'] = np.where
        aeval.symtable['ifelse'] = np.where
        
        # Inject Source Columns as Variables
        for col in df.columns:
            aeval.symtable[col] = df[col]
            
        try:
            result = aeval.eval(expression)
            if len(aeval.error) > 0:
                raise ValueError(f"Syntax Error: {aeval.error[0].get_error()}")
            return pd.Series(result, index=df.index)
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression '{expression}': {e}")

    @staticmethod
    def regex(df: pd.DataFrame, source_col: str, operation: str = "extract", pattern: str = "", replacement: str = "", **kwargs) -> pd.Series:
        """Secure regex string operations via Pandas built-in string methods."""
        series = df[source_col].astype(str)
        if operation == "extract":
            # Extracts the first capturing group
            return series.str.extract(pattern, expand=False)
        elif operation == "replace":
            return series.str.replace(pattern, replacement, regex=True)
        elif operation == "match":
            return series.str.contains(pattern, regex=True)
        return series


def apply_mappings(df_source: pd.DataFrame, final_mappings: List[Dict]) -> pd.DataFrame:
    """
    Executes approved rules. 
    Any errors occurring during transformation will propagate up to be displayed in the UI.
    """
    df_target = pd.DataFrame()
    
    for rule in final_mappings:
        target = rule["target_field"]
        func_name = rule["transformation_type"]
        params = rule["parameters"]
        
        if func_name == "unmapped":
            continue
            
        if hasattr(TransformationRegistry, func_name):
            func = getattr(TransformationRegistry, func_name)
            # Exceptions (like syntax errors in calculations) will propagate automatically
            df_target[target] = func(df=df_source, **params)
        else:
            raise ValueError(f"CRITICAL: Transformation '{func_name}' is not registered.")
            
    return df_target
