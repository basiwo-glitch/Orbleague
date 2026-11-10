"""ORB LEAGUE – Markenidentität: Name, Farben, Charaktere (die "Orbs")."""
from pathlib import Path

BRAND_NAME = "ORB LEAGUE"
HANDLE_CANDIDATES = ["orbleague", "orb.league", "orbleague.tv", "theorbleague"]
TAGLINE = "Physics decides. You pick."
BIO = "8 orbs. 1 league. Zero scripts. 🟠🔵🟣\nPhysics decides who wins – you pick the next fight 👇"

ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = str(ROOT / "assets/fonts/Poppins-Bold.ttf")
FONT_MED = str(ROOT / "assets/fonts/Poppins-Medium.ttf")
FONT_BLACK = str(ROOT / "assets/fonts/Inter-Black.otf")

# Visuelle Identität
BG_TOP = (10, 12, 28)
BG_BOTTOM = (22, 10, 38)
GRID = (255, 255, 255, 14)
WHITE = (245, 246, 255)
MUTED = (150, 156, 190)
ACCENT = (255, 214, 64)  # Liga-Gold

# Die 8 Liga-Charaktere. Persönlichkeit steuert Storylines & Captions.
ORBS = {
    "BLAZE":  {"color": (255, 77, 61),   "personality": "Hitzkopf, geht immer auf Angriff", "eyes": "angry"},
    "CRUSH":  {"color": (255, 150, 30),  "personality": "Großmaul, Trash-Talk", "eyes": "smug"},
    "VOLT":   {"color": (255, 222, 60),  "personality": "hyperaktiv, unberechenbar", "eyes": "wide"},
    "VENOM":  {"color": (110, 255, 92),  "personality": "hinterhältig, gewinnt in letzter Sekunde", "eyes": "sly"},
    "FROST":  {"color": (77, 216, 255),  "personality": "eiskalt, ruhig, Titelverteidiger", "eyes": "calm"},
    "COBALT": {"color": (70, 110, 255),  "personality": "Underdog, verliert oft knapp", "eyes": "sad"},
    "NOVA":   {"color": (178, 107, 255), "personality": "mysteriös, Fan-Liebling", "eyes": "calm"},
    "CORAL":  {"color": (255, 110, 196), "personality": "fröhlich, Comeback-Queen", "eyes": "happy"},
}


def orb_color(name):
    return ORBS[name]["color"]
