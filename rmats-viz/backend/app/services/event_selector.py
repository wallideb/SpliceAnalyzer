"""Top-10 selection helper: sort by FDR ASC (NaN last), then |IncLevelDifference| DESC."""
import pandas as pd


def select_top10(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df with top_rank 1..10 assigned to the 10 best events.
    Events are ranked by:
      1. FDR ascending (NaN sorted last)
      2. abs_inc_level_diff descending (NaN sorted last)
    """
    if df.empty:
        return df

    # Ensure abs column exists
    if "abs_inc_level_diff" not in df.columns:
        df = df.copy()
        df["abs_inc_level_diff"] = df["inc_level_difference"].abs()

    sorted_df = df.sort_values(
        by=["fdr", "abs_inc_level_diff"],
        ascending=[True, False],
        na_position="last",
    )

    top10 = sorted_df.head(10).copy()
    top10["top_rank"] = range(1, len(top10) + 1)
    return top10
