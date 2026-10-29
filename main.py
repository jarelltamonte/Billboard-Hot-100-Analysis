# %% [markdown]
# # How do hit songs behave? A Billboard Hot 100 analysis
# Questions a label's analytics team would ask:
# 1. How long does a song take to peak, and has that changed?
# 2. Are songs staying on the chart longer or shorter than they used to?
# 3. How much does the chart churn, and are hits getting more concentrated?

# %% Setup
import re
import unicodedata
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

DATA_DIR = Path(".")         
FIG_DIR = Path("figures")
FIG_DIR.mkdir(exist_ok=True)

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update({
    "figure.dpi": 110,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 13,
    "axes.titlelocation": "left",
})
ACCENT = "#1f6feb"
MUTED = "#8b949e"

# Chart-methodology changes, annotated on the plots because they can shift trends for reasons unrelated to listener behaviour.
EVENTS = {
    1991: "SoundScan data replaces surveys (Nov 1991)",
    1998: "Airplay-only songs eligible (Dec 1998)",
    2012: "Streaming (2012) and YouTube (2013) added",
}


SHOW = False   # True opens each plot in a window and pauses the script until you close it


def finish(fig, name):
    """Save the figure, optionally display it, then free the memory."""
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    if SHOW:
        plt.show()
    plt.close(fig)


def add_events(ax, xmin, xmax, events=EVENTS):
    """Vertical dashed lines with short labels for chart-rule changes."""
    for yr, label in events.items():
        if xmin <= yr <= xmax:
            ax.axvline(yr, color=MUTED, ls="--", lw=1)
            ax.text(yr + 0.4, ax.get_ylim()[1], label, rotation=90,
                    va="top", ha="left", fontsize=8, color=MUTED,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.7, pad=1))


# %% Cleaning helpers
def norm(s):
    """Light normalisation so the same song gets the same key every week."""
    if pd.isna(s):
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.strip().strip('"').lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" & ", " and ")
    return s


def load_chart(path):
    c = pd.read_csv(path, low_memory=False)
    c.columns = (c.columns.str.strip().str.lower()
                 .str.replace(r"[\s\-]+", "_", regex=True))
    c = c.rename(columns={"title": "song"})          # handles title/song naming
    c["date"] = pd.to_datetime(c["date"])
    c["rank"] = pd.to_numeric(c["rank"], errors="coerce")
    c["artist_n"] = c["artist"].map(norm)
    c["song_n"] = c["song"].map(norm)
    c = c[(c["artist_n"] != "") & (c["song_n"] != "")]
    c = c.dropna(subset=["date", "rank"])
    c["song_id"] = c["artist_n"] + " | " + c["song_n"]
    c["year"] = c["date"].dt.year
    return c


# %% Load Hot 100
df = load_chart(DATA_DIR / "hot100.csv")
last_date = df["date"].max()
first_year = df["year"].min()
print(f"{len(df):,} rows | {df['song_id'].nunique():,} songs | "
      f"{df['date'].min().date()} to {last_date.date()}")

# Sanity check: is the chart weekly with no gaps?
gaps = df["date"].drop_duplicates().sort_values().diff().dt.days.value_counts()
print("Days between chart weeks:\n", gaps.head())

dates = df["date"].drop_duplicates().sort_values().reset_index(drop=True)
gap = dates.diff().dt.days
for i in gap[gap > 7].index:
    print(f"Missing chart week(s) between {dates[i - 1].date()} and {dates[i].date()}")

# Consistent "week N on chart" counter (independent of the weeks_on_chart column)
df = df.sort_values(["song_id", "date"])
df["chart_week_no"] = df.groupby("song_id").cumcount() + 1

# %% One row per song
songs_all = df.groupby("song_id").agg(
    first_week=("date", "min"),
    last_seen=("date", "max"),
    best_rank=("rank", "min"),
    chart_weeks=("date", "nunique"),
)

df["best_rank"] = df["song_id"].map(songs_all["best_rank"])    # safe to re-run
peak_rows = (df[df["rank"] == df["best_rank"]]
             .sort_values("date")
             .drop_duplicates("song_id")
             .set_index("song_id"))

songs_all["peak_week"] = peak_rows["date"]
songs_all["weeks_to_peak"] = (
    (songs_all["peak_week"] - songs_all["first_week"]).dt.days // 7)
songs_all["debuted_at_peak"] = songs_all["weeks_to_peak"] == 0
songs_all["year"] = songs_all["first_week"].dt.year

# Cross-check: chart weeks (counted) vs calendar span. Big gaps = re-entries
songs_all["span_weeks"] = (
    (songs_all["last_seen"] - songs_all["first_week"]).dt.days // 7 + 1)
songs_all["reentered"] = songs_all["span_weeks"] > songs_all["chart_weeks"]
print(f"Songs with a gap in their run (re-entries): "
      f"{songs_all['reentered'].mean():.1%}")

# Guard against right-censoring: a song that debuted recently may still be
# climbing or charting, so keep only songs with at least two years of follow-up.
# The chart's first year is also dropped (every song in 1958 looks "new").
FOLLOW_UP_WEEKS = 104
cutoff = last_date - pd.Timedelta(weeks=FOLLOW_UP_WEEKS)
songs = songs_all[(songs_all["first_week"] <= cutoff)
                  & (songs_all["year"] > first_year)].copy()
print(f"Songs analysed: {len(songs):,} | longest total chart time: "
      f"{songs['chart_weeks'].max()} weeks | songs above {FOLLOW_UP_WEEKS} weeks: "
      f"{(songs['chart_weeks'] > FOLLOW_UP_WEEKS).sum()}")
print(songs.nlargest(5, "chart_weeks")[["first_week", "chart_weeks", "span_weeks"]])

# %% Q1: How long does a song take to peak?
q1 = songs.groupby("year").agg(
    median_weeks_to_peak=("weeks_to_peak", "median"),
    pct_debut_at_peak=("debuted_at_peak", "mean"),
    n_songs=("weeks_to_peak", "size"),
)
q1["pct_debut_at_peak"] *= 100
# Once most songs debut at their peak the overall median is stuck at 0, so also
# show the median for songs that had to climb.
q1["median_if_climbed"] = (songs[~songs["debuted_at_peak"]]
                           .groupby("year")["weeks_to_peak"].median())

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                               gridspec_kw={"height_ratios": [2, 1]})
ax1.plot(q1.index, q1["median_weeks_to_peak"], color=ACCENT, lw=2,
         label="All songs")
ax1.plot(q1.index, q1["median_if_climbed"], color=MUTED, lw=1.5, ls="--",
         label="Songs that did not debut at their peak")
ax1.legend(frameon=False, loc="lower left")
ax1.set_ylabel("Median weeks to peak")
ax1.set_title("Most new songs now peak in their first week on the chart")
add_events(ax1, q1.index.min(), q1.index.max())

ax2.fill_between(q1.index, q1["pct_debut_at_peak"], color=ACCENT, alpha=0.25)
ax2.plot(q1.index, q1["pct_debut_at_peak"], color=ACCENT, lw=1.5)
ax2.set_ylabel("% debuting at peak")
ax2.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax2.set_xlabel("Year of chart debut")
fig.text(0.01, -0.01, "Songs with 2+ years of follow-up; first chart year excluded. "
         "Weeks = calendar weeks from first appearance to first week at best rank.",
         fontsize=8, color=MUTED)
fig.tight_layout()
finish(fig, "q1_weeks_to_peak")

# %% Q2: Are songs staying on the chart longer?
q2 = songs.groupby("year").agg(
    median_weeks=("chart_weeks", "median"),
    pct_20plus=("chart_weeks", lambda s: (s >= 20).mean() * 100),
    n_songs=("chart_weeks", "size"),
)

# Many more songs now enter each week (see Q3), and many leave quickly, which can
# drag the overall median down. Look at hits separately: songs that reached the Top 10.
hits_only = songs[songs["best_rank"] <= 10]
q2["hits_median_weeks"] = hits_only.groupby("year")["chart_weeks"].median()
q2["hits_pct_20plus"] = (hits_only.groupby("year")["chart_weeks"]
                         .apply(lambda s: (s >= 20).mean() * 100))
q2["n_hits"] = hits_only.groupby("year").size()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
ax1.plot(q2.index, q2["median_weeks"], color=ACCENT, lw=2, label="All songs")
ax1.plot(q2.index, q2["hits_median_weeks"], color="#d29922", lw=2,
         label="Songs that reached the Top 10")
ax1.legend(frameon=False, loc="upper left")
ax1.set_ylabel("Median weeks on chart")
ax1.set_title("Typical chart entries now last 2-3 weeks, but Top 10 hits still last about 20")
add_events(ax1, q2.index.min(), q2.index.max())

ax2.plot(q2.index, q2["pct_20plus"], color=ACCENT, lw=2)
ax2.plot(q2.index, q2["hits_pct_20plus"], color="#d29922", lw=2)
ax2.set_ylabel("% of songs lasting 20+ weeks")
ax2.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax2.set_xlabel("Year of chart debut")
fig.text(0.01, -0.01, "Songs with 2+ years of follow-up. Chart rules for removing older "
         "songs changed over time, so part of any shift reflects the rules.",
         fontsize=8, color=MUTED)
fig.tight_layout()
finish(fig, "q2_longevity")

# Distribution view by era (violin/box)
songs["era"] = (songs["year"] // 10 * 10).astype(int).astype(str) + "s"
fig, ax = plt.subplots(figsize=(10, 5))
order = sorted(songs["era"].unique())
sns.boxplot(data=songs, x="era", y="chart_weeks", order=order, color="#a5c8ff",
            fliersize=1.5, ax=ax)
ax.set_title("Distribution of chart longevity by decade")
ax.set_xlabel("Decade of chart debut")
ax.set_ylabel("Weeks on chart")
fig.tight_layout()
finish(fig, "q2_longevity_by_decade")

# %% Q3: Churn and concentration
df["year"] = df["date"].dt.year
weeks_per_year = df.groupby("year")["date"].nunique()

new_per_week = (songs_all.groupby("year").size() / weeks_per_year).dropna()
new_per_week = new_per_week[new_per_week.index > first_year]

top10 = df[df["rank"] <= 10]
q3 = pd.DataFrame({
    "new_songs_per_week": new_per_week,
    "top10_median_age": top10.groupby("year")["chart_week_no"].median(),
    "top10_share_old": top10.groupby("year")["chart_week_no"]
                            .apply(lambda s: (s > 20).mean() * 100),
}).dropna()

fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
axes[0].plot(q3.index, q3["new_songs_per_week"], color=ACCENT, lw=2)
axes[0].set_ylabel("New songs / chart week")
axes[0].set_title("Chart churn: how many new songs enter each week?")

axes[1].plot(q3.index, q3["top10_median_age"], color="#d29922", lw=2)
axes[1].set_ylabel("Median age of Top 10 (weeks)")

axes[2].plot(q3.index, q3["top10_share_old"], color="#8250df", lw=2)
axes[2].set_ylabel("% of Top 10 older than 20 wks")
axes[2].yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
axes[2].set_xlabel("Year")
for ax in axes:
    add_events(ax, q3.index.min(), q3.index.max())
fig.text(0.01, -0.01, "All chart rows used. The final year is partial.",
         fontsize=8, color=MUTED)
fig.tight_layout()
finish(fig, "q3_churn_concentration")

# Heatmap: average song age by year and rank bucket
bins = [0, 10, 50, 100]
labels = ["Top 10", "11-50", "51-100"]
df["rank_bucket"] = pd.cut(df["rank"], bins=bins, labels=labels)
heat = (df[df["year"] > first_year]
        .pivot_table(index="rank_bucket", columns="year",
                     values="chart_week_no", aggfunc="mean", observed=True)
        .loc[labels])

fig, ax = plt.subplots(figsize=(12, 3.2))
sns.heatmap(heat, cmap="mako_r", cbar_kws={"label": "Avg weeks on chart so far"},
            xticklabels=5, ax=ax)
ax.set_title("How long songs have been on the chart, by position and year")
ax.set_xlabel("Year")
ax.set_ylabel("")
fig.tight_layout()
finish(fig, "q3_age_heatmap")

# %% Summary tables for the README
print(q1.round(1).tail())
print(q2.round(1).tail())
print(q3.round(1).tail())