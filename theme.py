# -*- coding: utf-8 -*-
"""Design tokens + QSS builder for the JV Bid Pro enterprise theme.

Modeled on the OpenConstructionERP aesthetic: high-density Zinc/Slate
neutrals, 32-36px control heights, 1px hairline borders, monospace
numerals, and a small semantic status palette (Emerald / Amber /
Crimson / Indigo).

Everything else in the app should pull colors/sizes from TOKENS rather
than hardcoding hex values, so the theme stays a single source of truth.
"""

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

RADIUS = {"sm": 4, "md": 6, "lg": 8}

SIZE = {
    "control_h": 32,      # inputs, combo boxes, list rows
    "control_h_lg": 36,   # primary buttons, top bar
    "sidebar_w": 232,
    "sidebar_w_collapsed": 56,
    "topbar_h": 44,
    "border": 1,
}

FONT = {
    "ui": "'Inter', 'Segoe UI', -apple-system, sans-serif",
    "mono": "'JetBrains Mono', 'Cascadia Mono', 'Consolas', 'Menlo', monospace",
    "size_sm": 11,
    "size_base": 12,
    "size_lg": 13,
}

# Tailwind-equivalent Zinc / Slate neutral ramps
ZINC = {
    50: "#fafafa", 100: "#f4f4f5", 200: "#e4e4e7", 300: "#d4d4d8",
    400: "#a1a1aa", 500: "#71717a", 600: "#52525b", 700: "#3f3f46",
    800: "#27272a", 900: "#18181b", 950: "#09090b",
}
SLATE = {
    50: "#f8fafc", 100: "#f1f5f9", 200: "#e2e8f0", 300: "#cbd5e1",
    400: "#94a3b8", 500: "#64748b", 600: "#475569", 700: "#334155",
    800: "#1e293b", 900: "#0f172a",
}

# Semantic status colors (fixed across themes)
STATUS = {
    "success": "#10b981",       # emerald-500
    "success_bg": "#064e3b33",  # emerald-900 @ 20%
    "warning": "#f59e0b",       # amber-500
    "warning_bg": "#78350f33",  # amber-900 @ 20%
    "danger": "#e11d48",        # rose/crimson-600
    "danger_bg": "#881337_33",
    "accent": "#6366f1",        # indigo-500
    "accent_bg": "#3730a333",
}

LIGHT = {
    "bg_app": ZINC[100], "bg_surface": "#ffffff", "bg_surface_alt": ZINC[50],
    "bg_sunken": ZINC[100], "bg_hover": ZINC[100], "bg_selected": "#eef2ff",
    "border": ZINC[200], "border_strong": ZINC[300],
    "text": ZINC[900], "text_muted": ZINC[500], "text_faint": ZINC[400],
    "sidebar_bg": ZINC[50], "sidebar_text": ZINC[600], "sidebar_active_bg": "#eef2ff",
    "sidebar_active_text": STATUS["accent"],
    "primary": ZINC[900], "primary_text": "#ffffff", "primary_hover": ZINC[800],
}

DARK = {
    "bg_app": ZINC[950], "bg_surface": ZINC[900], "bg_surface_alt": ZINC[900],
    "bg_sunken": ZINC[950], "bg_hover": ZINC[800], "bg_selected": "#312e81",
    "border": ZINC[800], "border_strong": ZINC[700],
    "text": ZINC[50], "text_muted": ZINC[400], "text_faint": ZINC[600],
    "sidebar_bg": ZINC[900], "sidebar_text": ZINC[400], "sidebar_active_bg": "#312e81",
    "sidebar_active_text": "#a5b4fc",
    "primary": ZINC[50], "primary_text": ZINC[900], "primary_hover": ZINC[200],
}

# Compatibility alias for older summary_panel.py revisions.
OBSIDIAN = DARK


def apply_elevation(widget, blur=20, y_offset=4, mode="Light"):
    """No-op: drop shadows are disabled for faster startup."""
    return None


def palette(mode: str) -> dict:
    return DARK if mode == "Dark" else LIGHT


# ---------------------------------------------------------------------------
# QSS builder
# ---------------------------------------------------------------------------

_qss_cache = {}

def build_qss(mode: str = "Light") -> str:
    if mode in _qss_cache:
        return _qss_cache[mode]
    p = palette(mode)
    r, sz, f = RADIUS, SIZE, FONT

    qss = f"""
    * {{ font-family: {f['ui']}; font-size: {f['size_base']}px; }}

    QMainWindow, QWidget {{
        background-color: {p['bg_app']}; color: {p['text']};
    }}

    /* ---------- Sidebar ---------- */
    QFrame#Sidebar {{
        background-color: {p['sidebar_bg']};
        border-right: {sz['border']}px solid {p['border']};
    }}
    QLabel#SidebarLogo {{
        color: {p['text']}; font-weight: 700; font-size: 14px;
    }}
    QLabel#SidebarTagline {{ color: {p['text_muted']}; font-size: {f['size_sm']}px; }}
    QPushButton#NavItem {{
        text-align: left; padding: 0 10px; border: none; border-radius: {r['sm']}px;
        color: {p['sidebar_text']}; background: transparent;
        min-height: {sz['control_h']}px; max-height: {sz['control_h']}px;
        font-size: {f['size_base']}px;
    }}
    QPushButton#NavItem:hover {{ background-color: {p['bg_hover']}; color: {p['text']}; }}
    QPushButton#NavItem:checked {{
        background-color: {p['sidebar_active_bg']}; color: {p['sidebar_active_text']};
        font-weight: 600;
    }}
    QPushButton#CollapseToggle {{
        border: {sz['border']}px solid {p['border']}; border-radius: {r['sm']}px;
        background: {p['bg_surface']}; min-height: 28px; max-height: 28px; min-width: 28px;
    }}
    QPushButton#CollapseToggle:hover {{ background-color: {p['bg_hover']}; }}

    /* ---------- Top bar ---------- */
    QFrame#TopBar {{
        background-color: {p['bg_surface']};
        border-bottom: {sz['border']}px solid {p['border']};
    }}
    QLabel#Breadcrumb {{ color: {p['text_muted']}; font-size: {f['size_base']}px; }}
    QLabel#BreadcrumbCurrent {{ color: {p['text']}; font-weight: 600; font-size: {f['size_base']}px; }}
    QPushButton#CmdKHint {{
        border: {sz['border']}px solid {p['border']}; border-radius: {r['sm']}px;
        background: {p['bg_surface_alt']}; color: {p['text_muted']};
        padding: 0 8px; min-height: 24px; max-height: 24px;
        font-family: {f['mono']}; font-size: {f['size_sm']}px;
    }}
    QPushButton#CmdKHint:hover {{ background-color: {p['bg_hover']}; color: {p['text']}; }}

    /* ---------- Buttons ---------- */
    QPushButton {{
        background-color: {p['bg_surface']}; color: {p['text']};
        border: {sz['border']}px solid {p['border_strong']}; border-radius: {r['sm']}px;
        padding: 0 12px; min-height: {sz['control_h']}px; max-height: {sz['control_h']}px;
    }}
    QPushButton:hover {{ background-color: {p['bg_hover']}; }}
    QPushButton:disabled {{ color: {p['text_faint']}; border-color: {p['border']}; }}
    QPushButton#Primary {{
        background-color: {p['primary']}; color: {p['primary_text']};
        border: none; font-weight: 600; min-height: {sz['control_h_lg']}px; max-height: {sz['control_h_lg']}px;
    }}
    QPushButton#Primary:hover {{ background-color: {p['primary_hover']}; }}
    QPushButton#Danger {{ background-color: transparent; color: {STATUS['danger']}; border-color: {STATUS['danger']}; }}
    QPushButton#Danger:hover {{ background-color: {STATUS['danger']}; color: white; }}

    /* ---------- Inputs ---------- */
    QLineEdit, QComboBox {{
        background-color: {p['bg_surface']}; color: {p['text']};
        border: {sz['border']}px solid {p['border_strong']}; border-radius: {r['sm']}px;
        padding: 0 8px; min-height: {sz['control_h']}px; max-height: {sz['control_h']}px;
    }}
    QLineEdit:focus, QComboBox:focus {{ border: {sz['border']}px solid {STATUS['accent']}; }}
    QLineEdit::placeholder {{ color: {p['text_faint']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QLineEdit[mono="true"], QLabel[mono="true"] {{
        font-family: {f['mono']};
    }}

    /* ---------- Tabs / Stacked pages share this pane style ---------- */
    QWidget#PageSurface {{ background-color: {p['bg_app']}; }}
    QFrame#Card {{
        background-color: {p['bg_surface']}; border: {sz['border']}px solid {p['border']};
        border-radius: {r['md']}px;
    }}


    /* ---------- Form cards ---------- */
    QFrame#FormCard {{
        background-color: {p['bg_surface']};
        border: {sz['border']}px solid {p['border']};
        border-radius: {r['lg']}px;
    }}
    QLabel#CardTitle {{
        color: {p['text']}; font-size: 14px; font-weight: 700;
    }}
    QLabel#CardSubtitle {{
        color: {p['text_muted']}; font-size: {f['size_sm']}px;
    }}

    /* ---------- Scroll areas ---------- */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {p['border_strong']}; border-radius: 5px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {p['text_faint']}; }}

    /* ---------- Splitter ---------- */
    QSplitter::handle {{ background-color: {p['border']}; width: {sz['border']}px; }}
    QSplitter::handle:hover {{ background-color: {STATUS['accent']}; }}

    /* ---------- Summary panel ---------- */
    QFrame#SummaryPanel {{
        background-color: {p['bg_surface_alt']};
        border-left: {sz['border']}px solid {p['border']};
    }}
    QLabel#SummaryHeading {{ color: {p['text']}; font-weight: 700; font-size: {f['size_lg']}px; }}
    QLabel#MetricLabel {{ color: {p['text_muted']}; font-size: {f['size_sm']}px; }}
    QLabel#MetricValue {{ color: {p['text']}; font-weight: 600; font-family: {f['mono']}; }}

    QLabel#Badge {{
        border-radius: {r['sm']}px; padding: 2px 8px; font-weight: 600;
        font-family: {f['mono']}; font-size: {f['size_sm']}px;
    }}
    QLabel#Badge[status="success"] {{ background-color: {STATUS['success']}22; color: {STATUS['success']}; }}
    QLabel#Badge[status="warning"] {{ background-color: {STATUS['warning']}22; color: {STATUS['warning']}; }}
    QLabel#Badge[status="danger"]  {{ background-color: {STATUS['danger']}22;  color: {STATUS['danger']}; }}
    QLabel#Badge[status="accent"]  {{ background-color: {STATUS['accent']}22;  color: {STATUS['accent']}; }}

    QLabel#PercentageBadge {{
        border-radius: {r['sm']}px; padding: 2px 8px; font-weight: 600;
        font-family: {f['mono']}; font-size: {f['size_sm']}px;
        background-color: #ffffff; color: #000000;
    }}

    /* ---------- Labels / misc ---------- */
    QLabel {{ color: {p['text']}; }}
    QLabel#FieldLabel {{ color: {p['text_muted']}; font-size: {f['size_base']}px; }}
    QFrame#HSep {{ background-color: {p['border']}; max-height: 1px; min-height: 1px; }}

    /* ---------- Command palette ---------- */
    QDialog#CommandPalette {{
        background-color: {p['bg_surface']}; border: {sz['border']}px solid {p['border_strong']};
        border-radius: {r['lg']}px;
    }}
    QListWidget#CommandList {{
        background-color: {p['bg_surface']}; border: none; outline: none;
    }}
    QListWidget#CommandList::item {{ padding: 6px 10px; border-radius: {r['sm']}px; color: {p['text']}; }}
    QListWidget#CommandList::item:selected {{ background-color: {p['bg_selected']}; color: {STATUS['accent']}; }}
    """
    _qss_cache[mode] = qss
    return qss