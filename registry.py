import pandas as pd
import numpy as np
from asteval import Interpreter
from typing import List, Dict

class TransformationRegistry:
    """Hardcoded safe transformations with smart auto-healing fallbacks."""
    
    @staticmethod
    def direct(df: pd.DataFrame, source_col: str, **kwargs) -> pd.Series:
        if not source_col or source_col not in df.columns:
            str_cols = df.select_dtypes(include=['object']).columns.tolist()
            source_col = str_cols[0] if str_cols else df.columns[0]
        return df[source_col]

    @staticmethod
    def enum_map(df: pd.DataFrame, source_col: str, mapping: dict, **kwargs) -> pd.Series:
        if not source_col or source_col not in df.columns:
            str_cols = df.select_dtypes(include=['object']).columns.tolist()
            source_col = str_cols[0] if str_cols else df.columns[0]
        
        s = df[source_col].astype(str)
        mapped = s.map(mapping)
        return mapped.fillna(s)

    @staticmethod
    def concat(df: pd.DataFrame, source_cols=None, source_columns=None, columns=None, delimiter: str = " ", **kwargs) -> pd.Series:
        cols = source_cols or source_columns or columns or []
        valid_cols = [c for c in cols if c in df.columns]
        
        if not valid_cols:
            auto_cols = [c for c in df.columns if any(k in c.lower() for k in ['fname', 'lname', 'first', 'last', 'name', 'cust'])]
            if len(auto_cols) >= 2:
                valid_cols = auto_cols[:2]
            else:
                str_cols = df.select_dtypes(include=['object']).columns.tolist()
                valid_cols = str_cols[:2] if len(str_cols) >= 2 else str_cols
                
        if not valid_cols:
            return pd.Series([""] * len(df), index=df.index)
            
        return df[valid_cols].astype(str).agg(delimiter.join, axis=1)
        
    @staticmethod
    def static_default(df: pd.DataFrame, value: str, **kwargs) -> pd.Series:
        return pd.Series([value] * len(df), index=df.index)

    @staticmethod
    def calculated(df: pd.DataFrame, expression: str, **kwargs) -> pd.Series:
        """Securely evaluates math and if-else logic using asteval and numpy."""
        aeval = Interpreter()
        aeval.symtable['where'] = np.where
        aeval.symtable['ifelse'] = np.where
        
        for col in df.columns:
            aeval.symtable[col] = df[col]
            
        try:
            result = aeval.eval(expression)
            if len(aeval.error) > 0:
                err_msg = aeval.error[0].get_error()
                raise ValueError(f"{err_msg}. (Hint: Ensure text values like 'CAD' are wrapped in quotes!)")
            return pd.Series(result, index=df.index)
        except Exception as e:
            raise ValueError(f"Expression Error in '{expression}': {e}")

    @staticmethod
    def regex(df: pd.DataFrame, source_col: str, operation: str = "extract", pattern: str = "", replacement: str = "", **kwargs) -> pd.Series:
        if not source_col or source_col not in df.columns:
            str_cols = df.select_dtypes(include=['object']).columns.tolist()
            source_col = str_cols[0] if str_cols else df.columns[0]
            
        series = df[source_col].astype(str)
        if operation == "extract":
            return series.str.extract(pattern, expand=False)
        elif operation == "replace":
            return series.str.replace(pattern, replacement, regex=True)
        elif operation == "match":
            return series.str.contains(pattern, regex=True)
        return series


def apply_mappings(df_source: pd.DataFrame, final_mappings: List[Dict]) -> pd.DataFrame:
    df_target = pd.DataFrame()
    
    for rule in final_mappings:
        target = rule["target_field"]
        func_name = rule["transformation_type"]
        params = rule["parameters"]
        
        if func_name == "unmapped":
            continue
            
        if hasattr(TransformationRegistry, func_name):
            func = getattr(TransformationRegistry, func_name)
            df_target[target] = func(df=df_source, **params)
        else:
            raise ValueError(f"CRITICAL: Transformation '{func_name}' is not registered.")
            
    return df_target
