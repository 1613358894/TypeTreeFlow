from __future__ import annotations

from pathlib import Path

from typetreeflow.ani.parse import SPECIES_ANI_THRESHOLD
from typetreeflow.ani.summary import REQUIRED_ANI_QUERY_VS_REFS_FIELDS


def plot_ani_query_vs_refs(
    input_tsv: str | Path,
    output_png: str | Path,
    title: str | None = None,
) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
        import seaborn as sns
    except ImportError as exc:
        raise RuntimeError(
            "ANI PNG plotting requires pandas, seaborn, and matplotlib."
        ) from exc

    input_path = Path(input_tsv)
    output_path = Path(output_png)
    dataframe = pd.read_csv(input_path, sep="\t")

    missing_fields = REQUIRED_ANI_QUERY_VS_REFS_FIELDS.difference(dataframe.columns)
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"Missing required ANI result field(s): {missing}.")
    if dataframe.empty:
        raise ValueError(f"No ANI hits found in {input_path}; PNG was not generated.")

    plot_data = dataframe.copy()
    try:
        plot_data["ani"] = pd.to_numeric(plot_data["ani"])
        plot_data["fraction"] = pd.to_numeric(plot_data["fraction"])
    except ValueError as exc:
        raise ValueError(f"ANI TSV contains non-numeric ani or fraction values: {input_path}.") from exc

    plot_data["above_species_threshold"] = plot_data["above_species_threshold"].map(
        _normalize_threshold_value
    )
    if plot_data["above_species_threshold"].isna().any():
        raise ValueError(
            f"ANI TSV contains invalid above_species_threshold values: {input_path}."
        )

    plot_data["display_label"] = plot_data.apply(_display_label, axis=1)
    plot_data = plot_data.sort_values(
        by=["ani", "fraction", "display_label"],
        ascending=[False, False, True],
    )

    sns.set_theme(style="whitegrid")
    height = max(3.2, min(12.0, 1.0 + 0.55 * len(plot_data)))
    width = 9.0
    fig, ax = plt.subplots(figsize=(width, height))

    palette = {True: "#2a9d8f", False: "#8d99ae"}
    sns.barplot(
        data=plot_data,
        x="ani",
        y="display_label",
        hue="above_species_threshold",
        dodge=False,
        palette=palette,
        ax=ax,
    )

    ax.axvline(
        SPECIES_ANI_THRESHOLD,
        color="#d62828",
        linestyle="--",
        linewidth=1.2,
    )
    ax.text(
        SPECIES_ANI_THRESHOLD,
        1.01,
        f"{SPECIES_ANI_THRESHOLD:g}% threshold",
        transform=ax.get_xaxis_transform(),
        ha="right",
        va="bottom",
        color="#d62828",
        fontsize=9,
    )

    x_min = max(0.0, min(float(plot_data["ani"].min()) - 1.0, SPECIES_ANI_THRESHOLD - 2.0))
    x_max = min(100.0, max(float(plot_data["ani"].max()) + 1.0, SPECIES_ANI_THRESHOLD + 2.0))
    ax.set_xlim(x_min, x_max)
    ax.set_xlabel("ANI (%)")
    ax.set_ylabel("Reference")
    ax.set_title(title or "Query genome ANI vs references")

    for patch, (_, row) in zip(ax.patches, plot_data.iterrows()):
        value = float(row["ani"])
        fraction = float(row["fraction"])
        ax.text(
            min(value + 0.08, x_max - 0.05),
            patch.get_y() + patch.get_height() / 2,
            f"{value:.2f}%  f={fraction:.3g}",
            va="center",
            ha="left",
            fontsize=8.5,
        )

    legend = ax.get_legend()
    if legend is not None:
        legend.set_title("ANI >= 95")
        for text, label in zip(legend.texts, ["No", "Yes"]):
            text.set_text(label)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def _display_label(row) -> str:
    reference_name = str(row.get("reference_name", "") or "").strip()
    normalized_id = str(row.get("normalized_id", "") or "").strip()
    return reference_name or normalized_id or "unknown reference"


def _normalize_threshold_value(value) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None
