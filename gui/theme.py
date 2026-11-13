# gui/theme.py
def get_theme_config(is_dark_theme):
    themes = {
        True: {
            "bm": "#121214", "bp": "#1a1a20", "bi": "#2d2d38", "bt": "#1e1e24", "bo": "#0c0c0f",
            "ft": "#ffffff", "fl": "#95a5a6", "fo": "#2ecc71", "ib": "white", "tc": "#2a2a32",
            "cb": "#2ecc71", "rb": "#3498db", "tb": "#2a2a32", "cpb": "#34495e", "sh": "#34495e"
        },
        False: {
            "bm": "#f0f2f5", "bp": "#ffffff", "bi": "#e4e6eb", "bt": "#ffffff", "bo": "#f5f6f7",
            "ft": "#000000", "fl": "#4b4f56", "fo": "#000000", "ib": "black", "tc": "#e4e6eb",
            "cb": "#0078d4", "rb": "#e1dfdd", "tb": "#e1dfdd", "cpb": "#e1dfdd", "sh": "#c8c6c4"
        }
    }
    return themes[is_dark_theme]