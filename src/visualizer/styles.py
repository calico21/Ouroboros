"""
Visual Styles and Dark-Slate Institutional Palette for AlphaForge.
Aesthetics: #0B0F19 background, #111827 panels, #10B981 emerald, #EF4444 ruby, #06B6D4 cyan, #F59E0B gold.
"""
import matplotlib as mpl
import matplotlib.pyplot as plt

# Color Palette Constants
BG_MAIN = "#0B0F19"
BG_PANEL = "#111827"
BG_BORDER = "#1F2937"
TEXT_PRIMARY = "#F9FAFB"
TEXT_SECONDARY = "#9CA3AF"
TEXT_MUTED = "#6B7280"

COLOR_PROFIT = "#10B981"      # Emerald Green
COLOR_LOSS = "#EF4444"        # Ruby Red
COLOR_CYAN = "#06B6D4"        # Electric Cyan
COLOR_GOLD = "#F59E0B"        # Institutional Gold
COLOR_PURPLE = "#8B5CF6"      # Violet
COLOR_FLOOR = "#DC2626"       # Crimson floor warning line
COLOR_GRID = "#1E293B"


def apply_dark_theme():
    """Applies institutional dark-slate theme across all matplotlib plots."""
    plt.style.use("dark_background")
    mpl.rcParams["figure.facecolor"] = BG_MAIN
    mpl.rcParams["axes.facecolor"] = BG_PANEL
    mpl.rcParams["axes.edgecolor"] = BG_BORDER
    mpl.rcParams["axes.labelcolor"] = TEXT_PRIMARY
    mpl.rcParams["text.color"] = TEXT_PRIMARY
    mpl.rcParams["xtick.color"] = TEXT_SECONDARY
    mpl.rcParams["ytick.color"] = TEXT_SECONDARY
    mpl.rcParams["grid.color"] = COLOR_GRID
    mpl.rcParams["grid.alpha"] = 0.6
    mpl.rcParams["grid.linestyle"] = "--"
    mpl.rcParams["font.sans-serif"] = ["DejaVu Sans", "Helvetica", "Arial"]
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["figure.autolayout"] = False
