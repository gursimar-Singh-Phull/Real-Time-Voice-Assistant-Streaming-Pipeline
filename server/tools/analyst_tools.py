"""Voice-invoked CSV/Excel analysis. Pandas is imported lazily for clear errors."""
import os
from pathlib import Path

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

MAX_ROWS = 200_000


def _load(path_string):
    import pandas as pd
    path = Path(path_string).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, nrows=MAX_ROWS)
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, nrows=MAX_ROWS)
    else:
        raise ValueError("Supported dataset formats are CSV, XLSX, and XLS.")
    return path, frame


async def analyze_dataset(params: FunctionCallParams):
    path_string = (params.arguments.get("path") or "").strip()
    operation = (params.arguments.get("operation") or "summary").strip().lower()
    column = (params.arguments.get("column") or "").strip()
    query = (params.arguments.get("query") or "").strip()
    try:
        path, df = _load(path_string)
        if df.empty:
            await params.result_callback(f"{path.name} contains no data rows.")
            return
        if operation == "summary":
            out = f"Dataset: {path.name}\nRows: {len(df):,}; columns: {len(df.columns)}\nColumns: {', '.join(map(str, df.columns))}\n\nTypes:\n{df.dtypes.to_string()}\n\nMissing values:\n{df.isna().sum().to_string()}"
        elif operation == "describe":
            out = df.describe(include="all").fillna("").to_string(max_rows=30, max_cols=15)
        elif operation == "duplicates":
            out = f"Duplicate rows: {int(df.duplicated().sum()):,} of {len(df):,} rows."
        elif operation == "missing":
            missing = df.isna().sum().sort_values(ascending=False)
            out = "Missing values by column:\n" + missing[missing > 0].to_string() if (missing > 0).any() else "No missing values found."
        elif operation == "top":
            if column not in df.columns:
                raise ValueError(f"Column '{column}' not found. Available: {', '.join(map(str, df.columns))}")
            out = df[column].value_counts(dropna=False).head(10).to_string()
        elif operation == "correlation":
            numeric = df.select_dtypes(include="number")
            if numeric.shape[1] < 2:
                raise ValueError("At least two numeric columns are required for correlation.")
            out = numeric.corr(numeric_only=True).round(3).to_string()
        elif operation == "query":
            if not query:
                raise ValueError("Provide a query such as 'show rows where Age > 30' is not yet supported; use a column summary, top values, missing, duplicates, or correlation.")
            lowered = query.lower()
            if lowered.startswith("count rows"):
                out = f"Row count: {len(df):,}"
            elif lowered.startswith("list columns"):
                out = "Columns: " + ", ".join(map(str, df.columns))
            elif lowered.startswith("average ") or lowered.startswith("mean "):
                target = query.split(" ", 1)[1].strip()
                if target not in df.columns:
                    raise ValueError(f"Column '{target}' not found.")
                out = f"Mean of {target}: {df[target].mean()}"
            else:
                raise ValueError("Supported natural-language queries: 'count rows', 'list columns', 'average <column>'.")
        elif operation == "chart":
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            if column not in df.columns:
                raise ValueError(f"Column '{column}' not found.")
            out_dir = Path.home() / ".nova_ai" / "reports"
            out_dir.mkdir(parents=True, exist_ok=True)
            output = out_dir / f"{path.stem}_{column.replace(' ', '_')}_chart.png"
            series = df[column].dropna()
            plt.figure(figsize=(9, 5))
            if str(series.dtype) == "object" or str(series.dtype).startswith("category"):
                series.value_counts().head(15).plot(kind="bar")
            else:
                series.plot(kind="hist", bins=20)
            plt.title(f"{column} — {path.name}")
            plt.tight_layout()
            plt.savefig(output)
            plt.close()
            out = f"Chart saved to {output}"
        elif operation == "report":
            out_dir = Path.home() / ".nova_ai" / "reports"
            out_dir.mkdir(parents=True, exist_ok=True)
            report = out_dir / f"{path.stem}_analysis.txt"
            report.write_text(
                f"Dataset: {path}\nRows: {len(df)}\nColumns: {len(df.columns)}\n\nSchema:\n{df.dtypes}\n\nDescribe:\n{df.describe(include='all').fillna('')}\n\nMissing values:\n{df.isna().sum()}\n\nDuplicate rows: {int(df.duplicated().sum())}\n",
                encoding="utf-8",
            )
            out = f"Analysis report saved to {report}"
        else:
            raise ValueError("Operations: summary, describe, missing, duplicates, top, correlation, query, chart, report.")
        await params.result_callback(out[:9000])
    except ImportError as exc:
        await params.result_callback(f"Analysis dependency missing: {exc}. Install pandas, openpyxl, and matplotlib.")
    except Exception as exc:
        await params.result_callback(f"Dataset analysis failed: {exc}")


analyst_tools = ToolsSchema(standard_tools=[
    FunctionSchema(
        name="analyze_dataset",
        description="Analyze a local CSV or Excel dataset. Supports summary, describe, missing values, duplicates, top values, numeric correlation, simple natural-language queries, chart generation, and report generation.",
        properties={
            "path":{"type":"string","description":"Full path to CSV/XLSX/XLS file."},
            "operation":{"type":"string","enum":["summary","describe","missing","duplicates","top","correlation","query","chart","report"],"description":"Analysis operation."},
            "column":{"type":"string","description":"Column name for top or chart."},
            "query":{"type":"string","description":"For query operation: count rows, list columns, or average <column>."}
        },
        required=["path","operation"],
        handler=analyze_dataset,
    )
])
