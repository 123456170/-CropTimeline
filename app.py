"""
CropTimeline — AI-powered crop growth-stage & health tracker
============================================================
A single-file Streamlit app that tracks every field through the season from
periodic photos, compares actual vs expected growth stages, and exports a
PDF season report.

AI engine
---------
* If GEMINI_API_KEY is found (st.secrets or environment variable), the real
  Google Gemini model "gemini-2.0-flash" is used for stage plans, photo
  analysis and season summaries.
* If NO key is present, a built-in offline simulator produces the exact same
  strict-JSON outputs, so the whole app (and the auto-loaded demo farm) works
  instantly without any credentials.

Run:  streamlit run app.py
"""

import datetime as dt
import io
import json
import math
import os
import random
import re
import sqlite3
import uuid
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
DB_PATH = Path("croptimeline.db")
PHOTO_DIR = Path("data") / "photos"
GEMINI_MODEL = "gemini-2.0-flash"

ALLOWED_STRESS = ["yellowing", "wilting", "lodging", "weeds",
                  "pest damage", "nutrient deficiency", "none"]

STATUS_COLORS = {
    "On track": "#2e7d32",
    "Delayed": "#c62828",
    "Ahead": "#1565c0",
    "Needs manual confirmation": "#ef6c00",
}
STATUS_EMOJI = {
    "On track": "🟢", "Delayed": "🔴", "Ahead": "🔵",
    "Needs manual confirmation": "🟠", "No photos yet": "⚪",
}

# ----------------------------------------------------------------------------
# Translations (English / Urdu / Hindi) — used for UI chrome and AI text
# ----------------------------------------------------------------------------
TRANSLATIONS = {
    "English": {
        "tagline": "AI crop growth & health tracker",
        "lang_label": "Language",
        "nav_dashboard": "🏠 Dashboard",
        "nav_fields": "🌾 Fields & Cycles",
        "nav_obs": "📸 New Observation",
        "nav_timeline": "📅 Timeline",
        "nav_rem": "⏰ Reminders",
        "nav_reports": "📄 Reports",
        "nav_settings": "⚙️ Settings",
        "kpi_fields": "Fields", "kpi_cycles": "Active cycles",
        "kpi_ontrack": "On track", "kpi_delayed": "Delayed",
        "kpi_ahead": "Ahead", "kpi_confirm": "Needs confirmation",
        "st_ontrack": "On track", "st_delayed": "Delayed",
        "st_ahead": "Ahead", "st_confirm": "Needs manual confirmation",
        "rem_title": "Fields that need a photo (no photo in 7+ days)",
        "rem_none": "✅ Every field was photographed in the last 7 days.",
        "btn_load_demo": "Load demo farm",
        "btn_reset": "Reset database",
        "btn_simulate": "Simulate today's observation",
        "demo_loaded": "Demo farm auto-loaded! Explore the pages, simulate new observations, and download a PDF season report.",
    },
    "Urdu": {
        "tagline": "فصل کی نشوونما اور صحت کی نگرانی",
        "lang_label": "زبان",
        "nav_dashboard": "🏠 ڈیش بورڈ",
        "nav_fields": "🌾 فیلڈز اور سائیکل",
        "nav_obs": "📸 نیا مشاہدہ",
        "nav_timeline": "📅 ٹائم لائن",
        "nav_rem": "⏰ یاد دہانیاں",
        "nav_reports": "📄 رپورٹس",
        "nav_settings": "⚙️ ترتیبات",
        "kpi_fields": "فیلڈز", "kpi_cycles": "فعال سائیکل",
        "kpi_ontrack": "وقت پر", "kpi_delayed": "تاخیر کا شکار",
        "kpi_ahead": "پیش رفت", "kpi_confirm": "تصدیق درکار",
        "st_ontrack": "وقت پر", "st_delayed": "تاخیر کا شکار",
        "st_ahead": "پیش رفت", "st_confirm": "دستی تصدیق درکار ہے",
        "rem_title": "جن فیلڈز کی تصویر ضروری ہے (7 دن سے زائد)",
        "rem_none": "✅ تمام فیلڈز کی تصاویر گزشتہ 7 دنوں کے اندر لی جا چکی ہیں۔",
        "btn_load_demo": "ڈیمو فارم لوڈ کریں",
        "btn_reset": "ڈیٹا بیس ری سیٹ کریں",
        "btn_simulate": "آج کا مشاہدہ تیار کریں",
        "demo_loaded": "ڈیمو فارم خود بخود لوڈ ہو گیا! صفحات دیکھیں، نئے مشاہدے تیار کریں اور پی ڈی ایف رپورٹ ڈاؤن لوڈ کریں۔",
    },
    "Hindi": {
        "tagline": "फसल की बढ़वार और सेहत की निगरानी",
        "lang_label": "भाषा",
        "nav_dashboard": "🏠 डैशबोर्ड",
        "nav_fields": "🌾 फ़ील्ड और साइकल",
        "nav_obs": "📸 नया निरीक्षण",
        "nav_timeline": "📅 समयरेखा",
        "nav_rem": "⏰ रिमाइंडर",
        "nav_reports": "📄 रिपोर्ट",
        "nav_settings": "⚙️ सेटिंग्स",
        "kpi_fields": "फ़ील्ड", "kpi_cycles": "सक्रिय साइकल",
        "kpi_ontrack": "समय पर", "kpi_delayed": "विलंबित",
        "kpi_ahead": "समय से आगे", "kpi_confirm": "पुष्टि आवश्यक",
        "st_ontrack": "समय पर", "st_delayed": "विलंबित",
        "st_ahead": "समय से आगे", "st_confirm": "हाथ से पुष्टि आवश्यक",
        "rem_title": "जिन फ़ील्ड की फोटो लेनी है (7+ दिन से फोटो नहीं)",
        "rem_none": "✅ सभी फ़ील्ड की फ़ोटो पिछले 7 दिनों में ली जा चुकी है।",
        "btn_load_demo": "डेमो फ़ार्म लोड करें",
        "btn_reset": "डेटाबेस रीसेट करें",
        "btn_simulate": "आज का निरीक्षण बनाएं",
        "demo_loaded": "डेमो फ़ार्म अपने आप लोड हो गया! पेज देखें, नए निरीक्षण बनाएं और पीडीएफ रिपोर्ट डाउनलोड करें।",
    },
}

# Localised names for stress signs
STRESS_T = {
    "yellowing": {"Urdu": "پتوں کا پیلاپن", "Hindi": "पीलापन"},
    "wilting": {"Urdu": "مرجھانا", "Hindi": "मुरझाना"},
    "lodging": {"Urdu": "پودوں کا گرنا", "Hindi": "पौधों का गिरना"},
    "weeds": {"Urdu": "جڑی بوٹیاں", "Hindi": "खरपतवार"},
    "pest damage": {"Urdu": "کیڑوں کا نقصان", "Hindi": "कीट क्षति"},
    "nutrient deficiency": {"Urdu": "غذائی کمی", "Hindi": "पोषक तत्वों की कमी"},
    "none": {"Urdu": "کوئی مسئلہ نہیں", "Hindi": "कोई समस्या नहीं"},
}


def t(key: str) -> str:
    """Translate a UI string into the currently selected language."""
    lang = st.session_state.get("lang", "English")
    return TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["English"].get(key, key)


def stress_label(sign: str) -> str:
    lang = st.session_state.get("lang", "English")
    if lang == "English":
        return sign
    return STRESS_T.get(sign, {}).get(lang, sign)


def status_tkey(status: str) -> str:
    return {"On track": "st_ontrack", "Delayed": "st_delayed",
            "Ahead": "st_ahead",
            "Needs manual confirmation": "st_confirm"}.get(status, "st_ontrack")


# ----------------------------------------------------------------------------
# SQLite database layer  (fields / cycles / expected_stages / observations)
# ----------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist yet."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS fields(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            area REAL DEFAULT 0,
            district TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')));
        CREATE TABLE IF NOT EXISTS cycles(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id INTEGER NOT NULL,
            crop TEXT NOT NULL,
            variety TEXT DEFAULT '',
            sowing_date TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            closed_at TEXT,
            FOREIGN KEY(field_id) REFERENCES fields(id));
        CREATE TABLE IF NOT EXISTS expected_stages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            start_day INTEGER NOT NULL,
            end_day INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL,
            obs_date TEXT NOT NULL,
            photo_path TEXT,
            photo_paths TEXT DEFAULT '[]',
            stage TEXT,
            canopy REAL,
            stress_signs TEXT DEFAULT '[]',
            confidence REAL,
            status TEXT,
            reason TEXT,
            needs_confirm INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')));
        """)


# ---- fields -----------------------------------------------------------------
def create_field(name, area, district) -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO fields(name, area, district) VALUES(?,?,?)",
                           (name, float(area or 0), district or ""))
        return cur.lastrowid


def list_fields():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM fields ORDER BY name").fetchall()]


def get_field(fid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM fields WHERE id=?", (fid,)).fetchone()
        return dict(row) if row else None


def update_field(fid, name, area, district):
    with get_conn() as conn:
        conn.execute("UPDATE fields SET name=?, area=?, district=? WHERE id=?",
                     (name, float(area or 0), district or "", fid))


def delete_field(fid):
    with get_conn() as conn:
        conn.execute("DELETE FROM fields WHERE id=?", (fid,))


# ---- cycles -----------------------------------------------------------------
def create_cycle(field_id, crop, variety, sowing_date, notes="") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO cycles(field_id, crop, variety, sowing_date, notes) "
            "VALUES(?,?,?,?,?)", (field_id, crop, variety, sowing_date, notes))
        return cur.lastrowid


def list_cycles(active_only=False):
    sql = ("SELECT c.*, f.name AS field_name, f.district AS field_district, "
           "f.area AS field_area FROM cycles c JOIN fields f ON f.id=c.field_id")
    if active_only:
        sql += " WHERE c.status='active'"
    sql += " ORDER BY c.sowing_date DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_cycle(cid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cycles WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None


def update_cycle(cid, crop, variety, sowing_date):
    with get_conn() as conn:
        conn.execute("UPDATE cycles SET crop=?, variety=?, sowing_date=? WHERE id=?",
                     (crop, variety, sowing_date, cid))


def close_cycle(cid):
    with get_conn() as conn:
        conn.execute("UPDATE cycles SET status='closed', closed_at=? WHERE id=?",
                     (dt.date.today().isoformat(), cid))


def delete_stages(cid):
    with get_conn() as conn:
        conn.execute("DELETE FROM expected_stages WHERE cycle_id=?", (cid,))


# ---- expected stages ----------------------------------------------------------
def save_stages(cid, stages):
    """Replace the expected stage plan of a cycle."""
    with get_conn() as conn:
        conn.execute("DELETE FROM expected_stages WHERE cycle_id=?", (cid,))
        conn.executemany(
            "INSERT INTO expected_stages(cycle_id, stage, start_day, end_day) "
            "VALUES(?,?,?,?)",
            [(cid, s["stage"], int(s["start_day"]), int(s["end_day"])) for s in stages])


def get_stages(cid):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT stage, start_day, end_day FROM expected_stages "
            "WHERE cycle_id=? ORDER BY start_day", (cid,)).fetchall()]


# ---- observations -------------------------------------------------------------
def add_observation(cycle_id, obs_date, photo_path, photo_paths_json, stage,
                    canopy, stress_signs, confidence, status, reason,
                    needs_confirm, notes=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO observations(cycle_id, obs_date, photo_path, photo_paths, "
            "stage, canopy, stress_signs, confidence, status, reason, needs_confirm, notes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (cycle_id, obs_date, photo_path, photo_paths_json, stage,
             float(canopy), json.dumps(stress_signs), float(confidence),
             status, reason, int(needs_confirm), notes))
        return cur.lastrowid


def list_observations(cid):
    """All observations of a cycle, oldest first, with computed DAS."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT o.*, CAST(julianday(o.obs_date)-julianday(c.sowing_date) AS INTEGER) AS das "
            "FROM observations o JOIN cycles c ON c.id=o.cycle_id "
            "WHERE o.cycle_id=? ORDER BY o.obs_date ASC, o.id ASC", (cid,)).fetchall()]


def latest_observation(cid):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT o.*, CAST(julianday(o.obs_date)-julianday(c.sowing_date) AS INTEGER) AS das "
            "FROM observations o JOIN cycles c ON c.id=o.cycle_id "
            "WHERE o.cycle_id=? ORDER BY o.obs_date DESC, o.id DESC LIMIT 1",
            (cid,)).fetchone()
        return dict(row) if row else None


def count_obs(cid) -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM observations WHERE cycle_id=?",
                            (cid,)).fetchone()[0]


def parse_stress(o) -> list:
    try:
        s = json.loads(o.get("stress_signs") or '["none"]')
        return s if isinstance(s, list) and s else ["none"]
    except (ValueError, TypeError):
        return ["none"]


def clear_all():
    """Wipe all rows and demo photos (used by Reset / demo re-seed)."""
    with get_conn() as conn:
        for tbl in ("observations", "expected_stages", "cycles", "fields"):
            conn.execute(f"DELETE FROM {tbl}")
    if PHOTO_DIR.exists():
        for p in PHOTO_DIR.glob("*"):
            try:
                p.unlink()
            except OSError:
                pass


# ----------------------------------------------------------------------------
# Gemini plumbing — falls back to the offline simulator when no key is set
# ----------------------------------------------------------------------------
def get_api_key():
    """Read the API key from st.secrets or the environment. Never hardcoded."""
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return str(key)
    except Exception:          # no secrets file present — that is fine
        pass
    return os.environ.get("GEMINI_API_KEY") or None


@st.cache_resource(show_spinner=False)
def gemini_model():
    """Return a configured Gemini model, or None when running offline."""
    key = get_api_key()
    if not key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        return genai.GenerativeModel(GEMINI_MODEL)
    except Exception:
        return None


def parse_gemini_json(text: str, required_keys=None) -> dict:
    """Robustly parse a model reply into JSON.

    Strips markdown code fences, falls back to the first {...} block and
    validates that all required keys are present. Raises ValueError otherwise.
    """
    if not text:
        raise ValueError("Empty response from model")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)   # leading ```json fence
    t = re.sub(r"\s*```$", "", t)            # trailing fence
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s == -1 or e <= s:
            raise ValueError("No JSON object found in model response")
        data = json.loads(t[s:e + 1])
    if required_keys:
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValueError(f"Missing keys in model JSON: {missing}")
    return data


# ----------------------------------------------------------------------------
# Agronomy knowledge base (used by the offline simulator and as fallback)
# ----------------------------------------------------------------------------
CROP_TEMPLATES = {
    "wheat": [("Germination", 0, 7), ("Tillering", 8, 30), ("Stem Extension", 31, 55),
              ("Heading", 56, 75), ("Flowering", 76, 90), ("Grain Filling", 91, 115),
              ("Maturity", 116, 130)],
    "rice": [("Establishment", 0, 10), ("Tillering", 11, 40), ("Panicle Initiation", 41, 60),
             ("Heading", 61, 75), ("Flowering", 76, 90), ("Grain Filling", 91, 115),
             ("Maturity", 116, 140)],
    "maize": [("Germination", 0, 7), ("Seedling", 8, 20), ("Vegetative Growth", 21, 45),
              ("Tasseling", 46, 55), ("Silking & Flowering", 56, 65),
              ("Grain Filling", 66, 90), ("Maturity", 91, 110)],
    "cotton": [("Germination", 0, 7), ("Seedling", 8, 25), ("Square Formation", 26, 55),
               ("Flowering", 56, 80), ("Boll Development", 81, 120),
               ("Maturity & Picking", 121, 160)],
    "potato": [("Germination", 0, 10), ("Vegetative Growth", 11, 30),
               ("Tuber Initiation", 31, 50), ("Tuber Bulking", 51, 75),
               ("Maturation", 76, 95)],
    "tomato": [("Transplant Establishment", 0, 10), ("Vegetative Growth", 11, 30),
               ("Flowering", 31, 50), ("Fruit Set & Development", 51, 70),
               ("Harvesting", 71, 100)],
    "onion": [("Germination", 0, 10), ("Leaf Development", 11, 35),
              ("Bulb Initiation", 36, 55), ("Bulb Development", 56, 85),
              ("Maturity", 86, 110)],
    "mustard": [("Germination", 0, 6), ("Rosette", 7, 30), ("Stem Elongation", 31, 50),
                ("Flowering", 51, 75), ("Siliqua Formation", 76, 100), ("Maturity", 101, 115)],
    "chickpea": [("Germination", 0, 8), ("Branching", 9, 35), ("Flowering", 36, 60),
                 ("Pod Development", 61, 90), ("Maturity", 91, 110)],
    "soybean": [("Germination", 0, 7), ("Vegetative Growth", 8, 35), ("Flowering", 36, 55),
                ("Pod Development", 56, 85), ("Maturity", 86, 105)],
    "sugarcane": [("Germination", 0, 30), ("Tillering", 31, 75),
                  ("Grand Growth", 76, 180), ("Maturity", 181, 300)],
    "sunflower": [("Germination", 0, 8), ("Vegetative Growth", 9, 35), ("Flowering", 36, 55),
                  ("Seed Filling", 56, 80), ("Maturity", 81, 100)],
    "generic": [("Germination", 0, 10), ("Vegetative Growth", 11, 40),
                ("Reproductive", 41, 70), ("Grain / Fruit Development", 71, 100),
                ("Maturity", 101, 120)],
}
CROP_TEMPLATES["paddy"] = CROP_TEMPLATES["rice"]
CROP_TEMPLATES["corn"] = CROP_TEMPLATES["maize"]
CROP_TEMPLATES["gram"] = CROP_TEMPLATES["chickpea"]


def mock_stage_plan(crop, variety):
    """Offline stage plan: pick the closest crop template."""
    c = (crop or "").lower()
    for key, stages in CROP_TEMPLATES.items():
        if key in c:
            return [{"stage": s, "start_day": a, "end_day": b} for s, a, b in stages]
    return [{"stage": s, "start_day": a, "end_day": b}
            for s, a, b in CROP_TEMPLATES["generic"]]


def canopy_curve(das, total_days):
    """Realistic S-shaped canopy development with late-season senescence."""
    total = max(total_days, 1)
    x = min(max(das / total, 0.0), 1.05)
    c = 100.0 / (1.0 + math.exp(-9.0 * (x - 0.45)))
    if x > 0.85:
        c *= max(0.55, 1.0 - 0.9 * (x - 0.85))
    return max(2.0, min(c, 98.0))


def expected_stage_index(stages, das):
    """Index of the expected stage at a given day-after-sowing."""
    if not stages:
        return 0
    for i, s in enumerate(stages):
        if s["start_day"] <= das <= s["end_day"]:
            return i
    if das < stages[0]["start_day"]:
        return 0
    return len(stages) - 1


def compute_status(stages, das, actual_stage):
    """Compare actual vs expected stage → On track / Delayed / Ahead."""
    names = [s["stage"] for s in stages]
    if not names or actual_stage not in names:
        return "Needs manual confirmation"
    exp = expected_stage_index(stages, das)
    act = names.index(actual_stage)
    if act < exp:
        return "Delayed"
    if act > exp:
        return "Ahead"
    return "On track"


def clean_stage_df(df):
    """Validate + normalise an edited stage-table DataFrame."""
    try:
        out = []
        for _, r in df.iterrows():
            stage = str(r.get("stage", "")).strip()
            if not stage:
                continue
            s, e = int(float(r.get("start_day", 0))), int(float(r.get("end_day", 0)))
            if e < s:
                s, e = e, s
            out.append({"stage": stage, "start_day": max(0, s), "end_day": e})
        out.sort(key=lambda x: x["start_day"])
        return out
    except Exception:
        return []


# ----------------------------------------------------------------------------
# AI FEATURES — stage plans, photo analysis, season summaries
# ----------------------------------------------------------------------------
STAGE_PLAN_PROMPT = (
    "You are an expert agronomist. Create the expected growth-stage schedule for a "
    "{crop} crop (variety: {variety}).\n"
    "Return STRICT JSON only — no markdown, no code fences, no commentary — in this "
    'exact shape: {{"stages": [{{"stage": "<name>", "start_day": <int>, '
    '"end_day": <int>}}, ...]}}\n'
    "Rules: days are days-after-sowing; stages are contiguous with no gaps or "
    "overlaps; use 5 to 8 stages; cover the full season from sowing to maturity."
)


def ai_stage_plan(crop, variety):
    """Expected growth stages as (stages_list, source_label). Retries once."""
    model = gemini_model()
    if model is None:
        return mock_stage_plan(crop, variety), "Offline simulator"
    prompt = STAGE_PLAN_PROMPT.format(crop=crop, variety=variety or "local")
    last_err = "unknown error"
    try:
        for _attempt in range(2):                       # one retry on failure
            resp = model.generate_content(prompt, generation_config={"temperature": 0.3})
            try:
                data = parse_gemini_json(resp.text, required_keys=["stages"])
                stages = clean_stage_df(pd.DataFrame(data["stages"]))
                if stages:
                    return stages, f"Gemini ({GEMINI_MODEL})"
                last_err = "empty stage list"
            except Exception as e:                      # validation failed → retry
                last_err = str(e)
    except Exception as e:
        last_err = str(e)
    st.warning(f"Gemini could not produce a valid stage plan ({last_err}). "
               "Falling back to the built-in agronomy simulator.")
    return mock_stage_plan(crop, variety), "Offline simulator (fallback)"


def mock_reason(stress, language):
    """One-sentence analysis reason in the selected language."""
    if not stress or stress == ["none"]:
        return {
            "English": "Crop appears healthy with normal canopy development for this stage.",
            "Urdu": "فصل صحت مند نظر آتی ہے اور نشوونما اس مرحلے کے لیے معمول کے مطابق ہے۔",
            "Hindi": "फसल स्वस्थ दिख रही है और इस चरण के लिए वृद्धि सामान्य है।",
        }[language]
    names = ", ".join(stress_label(s) for s in stress)
    return {
        "English": f"Visible signs of {', '.join(stress)} suggest the field needs attention.",
        "Urdu": f"فصل میں {names} کی علامات نظر آتی ہیں، توجہ درکار ہے۔",
        "Hindi": f"फसल में {names} के लक्षण दिख रहे हैं, ध्यान देने की आवश्यकता है।",
    }[language]


def mock_analysis(cycle, stages, das, obs_date, language):
    """Offline photo analysis returning the exact Gemini JSON schema."""
    rng = random.Random(f'{cycle["id"]}:{cycle["crop"]}:{das}:{obs_date.isoformat()}')
    names = [s["stage"] for s in stages] or ["Vegetative Growth"]
    total = stages[-1]["end_day"] if stages else 120
    exp_idx = expected_stage_index(stages, das) if stages else 0
    idx = max(0, min(len(names) - 1, exp_idx + rng.choice([-1, 0, 0, 0, 0, 1])))
    canopy = round(max(1.0, min(99.0, canopy_curve(max(das, 0), total) + rng.uniform(-6, 6))), 1)
    stress = ["none"]
    if rng.random() < 0.28:
        stress = rng.sample(["yellowing", "wilting", "lodging", "weeds",
                             "pest damage", "nutrient deficiency"],
                            k=rng.choice([1, 1, 2]))
    conf = round(rng.uniform(0.42, 0.58) if rng.random() < 0.12
                 else rng.uniform(0.72, 0.95), 2)
    return {"growth_stage": names[idx], "canopy_cover_percent": int(canopy),
            "stress_signs": stress, "confidence": conf,
            "reason": mock_reason(stress, language)}


def _normalize_analysis(raw, stage_names, language):
    """Validate one Gemini analysis response against the strict schema."""
    if not isinstance(raw, dict):
        raise ValueError("Response is not a JSON object")
    stage = str(raw.get("growth_stage", "")).strip()
    if stage not in stage_names:
        raise ValueError(f"growth_stage '{stage}' is not in the cycle plan")
    try:
        canopy = int(round(float(raw.get("canopy_cover_percent", 0))))
    except (TypeError, ValueError):
        canopy = 0
    canopy = max(0, min(100, canopy))
    stress = raw.get("stress_signs") or ["none"]
    if isinstance(stress, str):
        stress = [stress]
    stress = [s for s in stress if s in ALLOWED_STRESS]
    stress = ["none"] if (not stress or "none" in stress) else stress
    try:
        conf = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    reason = str(raw.get("reason", "")).strip()[:300] or mock_reason(stress, language)
    return {"growth_stage": stage, "canopy_cover_percent": canopy,
            "stress_signs": stress, "confidence": round(conf, 2), "reason": reason}


def ai_analyze_photos(cycle, stages, image_paths, obs_date, notes=""):
    """Vision analysis of 1-5 photos. Returns (analysis_dict, source_label)."""
    language = st.session_state.get("lang", "English")
    sowing = dt.date.fromisoformat(cycle["sowing_date"])
    das = (obs_date - sowing).days
    model = gemini_model()
    if model is None:
        return mock_analysis(cycle, stages, das, obs_date, language), "Offline simulator"

    stage_names = [s["stage"] for s in stages]
    prompt = (
        f"You are an expert agronomist vision model inspecting field photos.\n"
        f"Crop: {cycle['crop']} (variety: {cycle['variety'] or 'local'}). "
        f"Days after sowing: {das}. Allowed growth stages: {stage_names}.\n"
        f"Field notes from the farmer: {notes or 'none'}.\n"
        "Analyse the photo(s) and return STRICT JSON only — no markdown, no code "
        "fences — with exactly these keys:\n"
        '{"growth_stage": <one of the allowed stages>, '
        '"canopy_cover_percent": <integer 0-100>, '
        f'"stress_signs": <list with any of {ALLOWED_STRESS}, use ["none"] if healthy>, '
        '"confidence": <float 0-1>, '
        f'"reason": <one short sentence written in {language}>}}'
    )
    parts = []
    for p in image_paths[:5]:
        try:
            parts.append(Image.open(p).convert("RGB"))
        except Exception:
            continue
    parts.append(prompt)

    last_err = "unknown error"
    try:
        for _attempt in range(2):                       # one retry on failure
            resp = model.generate_content(parts, generation_config={"temperature": 0.2})
            try:
                raw = parse_gemini_json(
                    resp.text,
                    required_keys=["growth_stage", "canopy_cover_percent",
                                   "stress_signs", "confidence", "reason"])
                return _normalize_analysis(raw, stage_names, language), f"Gemini ({GEMINI_MODEL})"
            except Exception as e:                      # bad JSON → retry once
                last_err = str(e)
    except Exception as e:
        last_err = str(e)
    st.warning(f"Gemini photo analysis failed ({last_err}). "
               "Showing the offline simulator result instead.")
    return mock_analysis(cycle, stages, das, obs_date, language), "Offline simulator (fallback)"


# ---- season summary -----------------------------------------------------------
def _summary_ctx(field, cycle, obs):
    return {
        "field": field["name"], "crop": cycle["crop"],
        "variety": cycle["variety"] or "local", "sowing_date": cycle["sowing_date"],
        "observations": len(obs),
        "latest_das": obs[-1]["das"] if obs else None,
        "latest_stage": obs[-1]["stage"] if obs else None,
        "peak_canopy": round(max((o["canopy"] for o in obs), default=0)),
        "stress_events": sum(1 for o in obs if parse_stress(o) != ["none"]),
        "latest_status": ("Needs manual confirmation" if obs and obs[-1]["needs_confirm"]
                          else (obs[-1]["status"] if obs else "unknown")),
    }


def mock_summary(field, cycle, stages, obs, language):
    """Deterministic season summary in the selected language (offline mode)."""
    if not obs:
        return {
            "English": f"No photo observations have been recorded yet for {field['name']} ({cycle['crop']}).",
            "Urdu": f"{field['name']} ({cycle['crop']}) کے لیے ابھی کوئی تصویری مشاہدہ ریکارڈ نہیں ہوا۔",
            "Hindi": f"{field['name']} ({cycle['crop']}) के लिए अभी तक कोई फोटो निरीक्षण दर्ज नहीं हुआ है।",
        }[language]
    x = _summary_ctx(field, cycle, obs)
    if language == "Urdu":
        pos = {"On track": "بالکل وقت پر", "Delayed": "پیچھے", "Ahead": "آگے"}.get(x["latest_status"], "پیچھے")
        return (f"فیلڈ '{x['field']}' پر {x['crop']} (قسم: {x['variety']}) کی بوئائی {x['sowing_date']} کو ہوئی۔ "
                f"{x['observations']} تصویری مشاہدوں کے دوران فصل بوئائی کے {x['latest_das']} دن بعد "
                f"'{x['latest_stage']}' کے مرحلے پر ہے اور زیادہ سے زیادہ کینپی کور {x['peak_canopy']}% ریکارڈ کیا گیا۔ "
                f"تناؤ کی علامات {x['stress_events']} مرتبہ دیکھی گئیں۔ فصل اس وقت متوقع شیڈول سے {pos} ہے۔ "
                "سفارش: ہفتہ وار تصویری معائنہ جاری رکھیں اور بار بار آنے والے تناؤ کے علامات کا جلد علاج کریں۔")
    if language == "Hindi":
        pos = {"On track": "समय पर", "Delayed": "पीछे", "Ahead": "आगे"}.get(x["latest_status"], "पीछे")
        return (f"फ़ील्ड '{x['field']}' पर {x['crop']} (किस्म: {x['variety']}) की बुवाई {x['sowing_date']} को हुई थी। "
                f"{x['observations']} फोटो निरीक्षणों के दौरान फसल बुवाई के {x['latest_das']} दिन बाद "
                f"'{x['latest_stage']}' चरण में है और अधिकतम कैनोपी कवर {x['peak_canopy']}% दर्ज किया गया। "
                f"तनाव के लक्षण {x['stress_events']} बार देखे गए। फसल वर्तमान में अपेक्षित कार्यक्रम से {pos} है। "
                "सिफारश: साप्ताहिक फोटो निरीक्षण जारी रखें और दोहराए जाने वाले तनाव के लक्षणों का जल्द उपचार करें।")
    phrase = {"On track": "on track with", "Delayed": "behind", "Ahead": "ahead of"}.get(x["latest_status"], "behind")
    return (f"{x['crop']} (variety: {x['variety']}) on '{x['field']}' was sown on {x['sowing_date']}. "
            f"Across {x['observations']} photo observations the crop has reached the '{x['latest_stage']}' stage "
            f"at {x['latest_das']} days after sowing, with peak canopy cover of {x['peak_canopy']}%. "
            f"Stress signs were recorded on {x['stress_events']} occasion(s). "
            f"The field is currently {phrase} the expected schedule. "
            "Recommendation: keep weekly photo scouting and address recurring stress symptoms early.")


def ai_season_summary(field, cycle, stages, obs, language):
    """Season summary text in the chosen language. Returns (text, source)."""
    memo = f"summary_{cycle['id']}_{language}_{len(obs)}"
    if memo in st.session_state:
        return st.session_state[memo]
    model = gemini_model()
    text, source = None, "Offline simulator"
    if model is not None:
        ctx = _summary_ctx(field, cycle, obs)
        ctx["expected_stages"] = [s["stage"] for s in stages]
        prompt = ("You are a senior agronomist writing the season-summary section of a farm report.\n"
                  f"Farm data (JSON): {json.dumps(ctx)}\n"
                  f"Write a 4-6 sentence summary entirely in {language}. Cover overall progress vs the "
                  "expected schedule, canopy development, stress events observed, and one practical "
                  "recommendation. Return plain text only, no markdown.")
        try:
            for _attempt in range(2):                   # one retry on failure
                resp = model.generate_content(prompt, generation_config={"temperature": 0.4})
                txt = (resp.text or "").strip()
                if txt:
                    text, source = txt, f"Gemini ({GEMINI_MODEL})"
                    break
        except Exception as e:
            st.warning(f"Gemini summary failed ({e}). Using the offline simulator text.")
    if text is None:
        text = mock_summary(field, cycle, stages, obs, language)
    st.session_state[memo] = (text, source)
    return text, source


# ----------------------------------------------------------------------------
# Synthetic demo photos (PIL) — let the app demo itself without a camera
# ----------------------------------------------------------------------------
def make_demo_photo(crop, stage, canopy, stress, seed_key, path):
    """Draw a plausible synthetic field photo reflecting stage/canopy/stress."""
    rng = random.Random(str(seed_key))
    W, H = 360, 240
    img = Image.new("RGB", (W, H), (101, 67, 33))       # soil base
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 70], fill=(126, 188, 233))    # sky
    base = (52, 120, 45)
    if "yellowing" in stress:
        base = (154, 160, 50)
    if "nutrient deficiency" in stress:
        base = (96, 128, 58)
    n = int((W / 5) * (max(canopy, 4) / 100)) + 4       # plant density ~ canopy %
    for _ in range(n):
        x = rng.randint(0, W)
        yb = rng.randint(95, H - 20)
        h = rng.randint(25, 80)
        sway = rng.randint(-6, 6)
        col = tuple(max(0, min(255, c + rng.randint(-18, 18))) for c in base)
        d.line([(x, yb), (x + sway, yb - h)], fill=col, width=rng.randint(2, 4))
    if "weeds" in stress:
        for _ in range(25):
            x = rng.randint(0, W)
            yb = rng.randint(150, H - 8)
            d.line([(x, yb), (x + rng.randint(-4, 4), yb - rng.randint(6, 14))],
                   fill=(70, 90, 40), width=2)
    if "pest damage" in stress:
        for _ in range(40):
            x, y = rng.randint(0, W), rng.randint(80, H - 25)
            d.ellipse([x, y, x + 3, y + 3], fill=(90, 60, 30))
    d.rectangle([0, H - 20, W, H], fill=(20, 20, 20))
    d.text((6, H - 16), f"{crop} | {stage} | canopy {int(canopy)}%", fill=(255, 255, 255))
    img.save(path, "JPEG", quality=85)


# ----------------------------------------------------------------------------
# Demo seed data — a realistic 5-field farm loaded automatically on first run
# ----------------------------------------------------------------------------
def seed_demo_data():
    """Populate the database with a realistic multi-field demo farm."""
    clear_all()
    today = dt.date.today()
    rng = random.Random(20261008)
    specs = [
        # name, area, district, crop, variety, DAS today, stage bias, days since last photo
        ("North Field", 4.5, "Ludhiana", "Wheat", "HD-2967", 78, 0, 2),
        ("East Field", 3.2, "Karnal", "Rice", "Basmati-1121", 96, -1, 3),     # Delayed
        ("West Field", 5.0, "Hisar", "Maize", "Hybrid NK-6240", 34, 1, 10),   # Ahead + reminder
        ("South Field", 2.4, "Jalandhar", "Potato", "Kufri Jyoti", 56, -1, 12),  # Delayed + reminder
        ("River Field", 6.1, "Abohar", "Cotton", "F-1842", 47, 0, None),      # never photographed
    ]
    for name, area, dist, crop, var, das_today, bias, gap in specs:
        fid = create_field(name, area, dist)
        sowing = today - dt.timedelta(days=das_today)
        cid = create_cycle(fid, crop, var, sowing.isoformat(), notes="Demo crop cycle")
        stages = mock_stage_plan(crop, var)
        save_stages(cid, stages)
        if gap is None:                                 # reminder demo: no photos at all
            continue
        total = stages[-1]["end_day"]
        obs_days, d, last_day = [], 8, das_today - gap  # observations every ~10-14 days
        while d < last_day:
            obs_days.append(d)
            d += rng.randint(10, 14)
        obs_days.append(last_day)
        for i, das in enumerate(obs_days):
            exp_idx = expected_stage_index(stages, das)
            idx = max(0, min(len(stages) - 1, exp_idx + bias))
            stage = stages[idx]["stage"]
            canopy = round(max(2, min(98, canopy_curve(das, total) + rng.uniform(-6, 6))), 1)
            stress = ["none"]
            if rng.random() < (0.45 if bias < 0 else 0.12):
                stress = rng.sample(["yellowing", "wilting", "weeds",
                                     "pest damage", "nutrient deficiency"],
                                    k=rng.choice([1, 1, 2]))
            conf, needs = round(rng.uniform(0.72, 0.95), 2), 0
            if name == "East Field" and i == len(obs_days) - 1:
                conf, needs = 0.55, 1                   # demos manual-confirmation flow
            status = compute_status(stages, das, stage)
            obs_date = (sowing + dt.timedelta(days=das)).isoformat()
            photo = PHOTO_DIR / f"demo_c{cid}_d{das}.jpg"
            make_demo_photo(crop, stage, canopy, stress, f"{cid}-{das}", photo)
            add_observation(cid, obs_date, str(photo), json.dumps([str(photo)]),
                            stage, canopy, stress, conf, status,
                            mock_reason(stress, "English"), needs,
                            "Auto-generated demo observation")


def create_simulated_observation(cyc, stages, obs_date):
    """One-click demo: generate a photo, run the AI, save the observation."""
    sowing = dt.date.fromisoformat(cyc["sowing_date"])
    das = (obs_date - sowing).days
    est_idx = expected_stage_index(stages, max(0, das)) if stages else 0
    est_stage = stages[est_idx]["stage"] if stages else "Vegetative Growth"
    total = stages[-1]["end_day"] if stages else 120
    p = PHOTO_DIR / f"sim_{uuid.uuid4().hex[:10]}.jpg"
    make_demo_photo(cyc["crop"], est_stage, canopy_curve(max(0, das), total),
                    ["none"], uuid.uuid4().hex, p)
    analysis, _src = ai_analyze_photos(cyc, stages, [str(p)], obs_date, "")
    status = compute_status(stages, das, analysis["growth_stage"])
    low = analysis["confidence"] < 0.6
    add_observation(cyc["id"], obs_date.isoformat(), str(p), json.dumps([str(p)]),
                    analysis["growth_stage"], analysis["canopy_cover_percent"],
                    analysis["stress_signs"], analysis["confidence"], status,
                    analysis["reason"], 1 if low else 0, "Simulated observation")
    return analysis, low


def reminders_data():
    """Active cycles with no photo in the last 7 days (or never).

    Each item carries both 'id' and a 'cycle_id' alias so either key works
    safely in the UI layer.
    """
    today = dt.date.today()
    out = []
    for c in list_cycles(active_only=True):
        last = latest_observation(c["id"])
        if last:
            gap = (today - dt.date.fromisoformat(last["obs_date"])).days
            never = False
        else:
            gap = (today - dt.date.fromisoformat(c["sowing_date"])).days
            never = True
        if never or gap > 7:
            out.append({**c, "cycle_id": c["id"], "gap": gap, "never": never})
    return out


# ----------------------------------------------------------------------------
# PDF season report (ReportLab) — English text for font compatibility
# ----------------------------------------------------------------------------
def _pdf_chart(stages, obs):
    """Canopy-vs-DAS line chart with shaded expected stage bands."""
    from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
    from reportlab.lib import colors
    W, H, pl, pr, pt, pb = 520, 190, 34, 10, 14, 22
    pw, ph = W - pl - pr, H - pt - pb
    max_das = max([s["end_day"] for s in stages] + [o["das"] for o in obs] + [30])
    d = Drawing(W, H)
    palette = ["#dcedc8", "#fff9c4", "#bbdefb", "#e1bee7", "#ffe0b2", "#b2dfdb"]
    for i, s in enumerate(stages):
        x0 = pl + pw * s["start_day"] / max_das
        x1 = pl + pw * min(s["end_day"], max_das) / max_das
        d.add(Rect(x0, pb, max(1, x1 - x0), ph,
                   fillColor=colors.HexColor(palette[i % len(palette)]), strokeColor=None))
        d.add(String(x0 + 2, H - pt + 2, s["stage"], fontSize=6,
                     fillColor=colors.HexColor("#555555")))
    d.add(Line(pl, pb, W - pr, pb, strokeColor=colors.black))
    d.add(Line(pl, pb, pl, H - pt, strokeColor=colors.black))
    d.add(String(4, pb, "0", fontSize=7))
    d.add(String(4, H - pt - 6, "100%", fontSize=7))
    d.add(String(pl, 6, "0 DAS", fontSize=7))
    d.add(String(W - pr - 46, 6, f"{max_das} DAS", fontSize=7))
    pts = [(pl + pw * o["das"] / max_das, pb + ph * o["canopy"] / 100) for o in obs]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#2e7d32"), strokeWidth=2))
    for x, y in pts:
        d.add(Circle(x, y, 2.6, fillColor=colors.HexColor("#1b5e20"), strokeColor=None))
    return d


def build_pdf(field, cycle, stages, obs, summary_en) -> bytes:
    """Render the full season report as PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="CropTimeline season report",
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    story = [Paragraph("CropTimeline - Season Report", styles["Title"]),
             Paragraph(f"Generated {dt.date.today().isoformat()}", styles["Normal"]),
             Spacer(1, 6)]

    # 1 — field & crop details
    story.append(Paragraph("1. Field & crop details", styles["Heading2"]))
    detail = [["Field", field["name"]], ["District / location", field["district"]],
              ["Area", f'{field["area"]} acres'], ["Crop", cycle["crop"]],
              ["Variety", cycle["variety"] or "-"], ["Sowing date", cycle["sowing_date"]],
              ["Cycle status", cycle["status"]], ["Observations", str(len(obs))]]
    td = Table(detail, colWidths=[45 * mm, 125 * mm])
    td.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4e8")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    story += [td, Spacer(1, 10)]

    # 2 — expected stages
    story.append(Paragraph("2. Expected growth stages (days after sowing)", styles["Heading2"]))
    rows = [["#", "Stage", "Start day", "End day"]] + \
           [[i + 1, s["stage"], s["start_day"], s["end_day"]] for i, s in enumerate(stages)]
    ts = Table(rows, colWidths=[12 * mm, 80 * mm, 30 * mm, 30 * mm])
    ts.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
    story += [ts, Spacer(1, 10)]

    # 3 — canopy chart
    story.append(Paragraph("3. Canopy cover vs days after sowing", styles["Heading2"]))
    story += [_pdf_chart(stages, obs), Spacer(1, 10)]

    # 4 — observation log
    story.append(Paragraph("4. Observation timeline", styles["Heading2"]))
    if obs:
        ohead = [["Date", "DAS", "Stage", "Canopy %", "Stress signs", "Conf.", "Status"]]
        obody = [[o["obs_date"], o["das"], o["stage"], f'{o["canopy"]:.0f}',
                  ", ".join(parse_stress(o)), f'{o["confidence"]:.2f}',
                  "Needs manual confirmation" if o["needs_confirm"] else o["status"]]
                 for o in obs]
        to = Table(ohead + obody, colWidths=[24 * mm, 12 * mm, 34 * mm, 16 * mm,
                                             44 * mm, 12 * mm, 28 * mm], repeatRows=1)
        to.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7)]))
        story.append(to)
    else:
        story.append(Paragraph("No observations recorded.", styles["Normal"]))
    story.append(Spacer(1, 10))

    # 5 — stress events
    story.append(Paragraph("5. Stress events", styles["Heading2"]))
    evs = [o for o in obs if parse_stress(o) != ["none"]]
    if evs:
        for o in evs:
            story.append(Paragraph(
                f'• {o["obs_date"]} ({o["das"]} DAS, stage {o["stage"]}): '
                f'{", ".join(parse_stress(o))}', styles["Normal"]))
    else:
        story.append(Paragraph("No stress signs were detected in any observation.",
                               styles["Normal"]))
    story.append(Spacer(1, 10))

    # 6 — AI summary
    story.append(Paragraph("6. AI season summary", styles["Heading2"]))
    story.append(Paragraph(summary_en.replace("\n", "<br/>"), styles["BodyText"]))

    doc.build(story)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Small UI helpers
# ----------------------------------------------------------------------------
def badge(text, color):
    return (f'<span style="background:{color};color:#fff;padding:2px 10px;'
            f'border-radius:12px;font-size:0.78rem;white-space:nowrap;">{text}</span>')


def status_chip(o):
    """Coloured HTML badge for an observation row."""
    if o["needs_confirm"]:
        return badge("🟠 " + t("st_confirm"), STATUS_COLORS["Needs manual confirmation"])
    s = o["status"]
    return badge(f"{STATUS_EMOJI.get(s, '⚪')} {t(status_tkey(s))}",
                 STATUS_COLORS.get(s, "#607d8b"))


def cycle_label(row):
    return f'{row["field_name"]} • {row["crop"]} ({row["variety"] or "-"}) • sown {row["sowing_date"]}'


def select_cycle(key, active_only=True):
    """Reusable cycle picker. Returns the selected cycle dict or None."""
    rows = list_cycles(active_only=active_only)
    if not rows:
        st.info("No crop cycles yet — create a field and a cycle under **Fields & Cycles** first.")
        return None
    mapping = {r["id"]: r for r in rows}
    cid = st.selectbox("Crop cycle", list(mapping),
                       format_func=lambda i: cycle_label(mapping[i]), key=key)
    return mapping[cid]


# ----------------------------------------------------------------------------
# PAGES
# ----------------------------------------------------------------------------
def page_dashboard():
    if st.session_state.pop("just_seeded", False):
        st.success("🎬 " + t("demo_loaded"))
    fields, active = list_fields(), list_cycles(active_only=True)
    today = dt.date.today()
    counts = {"On track": 0, "Delayed": 0, "Ahead": 0, "Needs manual confirmation": 0}
    rows = []
    for c in active:
        stages = get_stages(c["id"])
        das = (today - dt.date.fromisoformat(c["sowing_date"])).days
        exp = stages[expected_stage_index(stages, das)]["stage"] if stages else "-"
        last = latest_observation(c["id"])
        if last:
            disp = "Needs manual confirmation" if last["needs_confirm"] else last["status"]
            gap = (today - dt.date.fromisoformat(last["obs_date"])).days
            last_photo = "today" if gap == 0 else f"{gap} d ago"
            latest_stage = last["stage"]
        else:
            disp, last_photo, latest_stage = "No photos yet", "—", "—"
        if disp in counts:
            counts[disp] += 1
        rows.append({"Field": c["field_name"], "Crop": c["crop"],
                     "Variety": c["variety"], "DAS": max(0, das),
                     "Expected stage": exp, "Latest stage": latest_stage,
                     "Status": f"{STATUS_EMOJI.get(disp, '⚪')} {disp}",
                     "Last photo": last_photo})

    # KPI cards
    k = st.columns(4)
    k[0].metric(t("kpi_fields"), len(fields))
    k[1].metric(t("kpi_cycles"), len(active))
    k[2].metric("🟢 " + t("kpi_ontrack"), counts["On track"])
    k[3].metric("🔴 " + t("kpi_delayed"), counts["Delayed"])
    k2 = st.columns(4)
    k2[0].metric("🔵 " + t("kpi_ahead"), counts["Ahead"])
    k2[1].metric("🟠 " + t("kpi_confirm"), counts["Needs manual confirmation"])
    k2[2].metric("⏰ " + t("nav_rem"), len(reminders_data()))
    k2[3].metric("📸 Observations",
                 sum(count_obs(c["id"]) for c in active))

    st.markdown("##### " + t("kpi_cycles"))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Reminder panel
    st.markdown("### ⏰ " + t("rem_title"))
    rem = reminders_data()
    if rem:
        for r in rem:
            msg = ("📷 no photos yet this season" if r["never"]
                   else f"📷 last photo {r['gap']} days ago")
            st.warning(f"**{r['field_name']}** — {r['crop']} ({r['variety'] or '-'}): {msg}")
    else:
        st.success(t("rem_none"))


def page_fields():
    st.subheader(t("nav_fields"))
    col1, col2 = st.columns([1, 1.3])
    fields = list_fields()

    with col1:
        with st.expander("➕ Add a new field", expanded=not fields):
            with st.form("add_field"):
                name = st.text_input("Field name")
                area = st.number_input("Area (acres)", min_value=0.0, step=0.5)
                district = st.text_input("District / location")
                if st.form_submit_button("💾 Save field"):
                    if name.strip():
                        create_field(name.strip(), area, district.strip())
                        st.success("Field added ✅")
                        st.rerun()
                    else:
                        st.error("Please enter a field name.")
        if not fields:
            st.info("Add your first field to begin.")
            return
        fid = st.selectbox("Select field", [f["id"] for f in fields],
                           format_func=lambda i: next(f["name"] for f in fields if f["id"] == i))
        f = get_field(fid)
        st.markdown(f"**{f['name']}** — {f['area']} acres • 📍 {f['district'] or '-'}")
        with st.expander("✏️ Edit field details"):
            with st.form("edit_field"):
                n = st.text_input("Field name", value=f["name"])
                a = st.number_input("Area (acres)", value=float(f["area"] or 0.0), step=0.5)
                dd = st.text_input("District / location", value=f["district"])
                if st.form_submit_button("💾 Update field"):
                    update_field(fid, n.strip() or f["name"], a, dd.strip())
                    st.success("Saved ✅")
                    st.rerun()

    with col2:
        cycles = [c for c in list_cycles() if c["field_id"] == fid]
        st.markdown("##### Crop cycles on this field")
        today = dt.date.today()
        if cycles:
            table = []
            for c in cycles:
                last = latest_observation(c["id"])
                table.append({"Crop": c["crop"], "Variety": c["variety"] or "-",
                              "Sown": c["sowing_date"], "Status": c["status"],
                              "DAS": max(0, (today - dt.date.fromisoformat(c["sowing_date"])).days),
                              "Photos": count_obs(c["id"]),
                              "Last stage": last["stage"] if last else "-"})
            st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
        else:
            st.info("No cycles yet — start one below.")

        # ---- new cycle + AI stage plan ------------------------------------
        with st.expander("➕ Start a new crop cycle", expanded=True):
            with st.form("new_cycle"):
                nc1, nc2 = st.columns(2)
                crop = nc1.text_input("Crop", value="Wheat")
                variety = nc2.text_input("Variety", value="")
                sdate = st.date_input("Sowing date", value=today)
                if st.form_submit_button("🤖 Generate expected stage plan (AI)"):
                    if not crop.strip():
                        st.error("Please enter a crop name.")
                    else:
                        with st.spinner("Asking AI for the growth plan…"):
                            plan, src = ai_stage_plan(crop.strip(), variety.strip())
                        st.session_state["new_plan"] = {
                            "df": pd.DataFrame(plan), "source": src,
                            "crop": crop.strip(), "variety": variety.strip(),
                            "sowing": sdate.isoformat()}
                        st.rerun()

        if st.session_state.get("new_plan"):
            np = st.session_state["new_plan"]
            st.markdown(f"**Review & edit the AI stage plan** · source: `{np['source']}` · "
                        f"{np['crop']} / {np['variety'] or '-'} · sown {np['sowing']}")
            edited = st.data_editor(
                np["df"], num_rows="dynamic", use_container_width=True, key="plan_editor",
                column_config={
                    "stage": st.column_config.TextColumn("Stage"),
                    "start_day": st.column_config.NumberColumn("Start (DAS)", min_value=0),
                    "end_day": st.column_config.NumberColumn("End (DAS)", min_value=0)})
            s1, s2 = st.columns(2)
            if s1.button("✅ Save cycle with this plan", type="primary"):
                stages = clean_stage_df(edited)
                if not stages:
                    st.error("The plan is empty or invalid — please fix the table first.")
                else:
                    cid = create_cycle(fid, np["crop"], np["variety"], np["sowing"])
                    save_stages(cid, stages)
                    del st.session_state["new_plan"]
                    st.success(f"Crop cycle created ✅ (expected duration "
                               f"{stages[-1]['end_day']} days)")
                    st.rerun()
            if s2.button("✖ Cancel plan"):
                del st.session_state["new_plan"]
                st.rerun()

        # ---- manage an existing cycle --------------------------------------
        active_cycles = [c for c in cycles if c["status"] == "active"]
        if active_cycles:
            st.markdown("##### Manage a cycle")
            mapping = {c["id"]: c for c in active_cycles}
            mg = st.selectbox("Cycle to manage", list(mapping),
                              format_func=lambda i: cycle_label(mapping[i]),
                              key="manage_cycle")
            plan_df = pd.DataFrame(get_stages(mg))
            if not plan_df.empty:
                edited2 = st.data_editor(
                    plan_df, num_rows="dynamic", use_container_width=True,
                    key=f"plan_edit_{mg}",
                    column_config={
                        "stage": st.column_config.TextColumn("Stage"),
                        "start_day": st.column_config.NumberColumn("Start (DAS)", min_value=0),
                        "end_day": st.column_config.NumberColumn("End (DAS)", min_value=0)})
                if st.button("💾 Update stage plan", key=f"upd_{mg}"):
                    stages = clean_stage_df(edited2)
                    if stages:
                        save_stages(mg, stages)
                        st.success("Stage plan updated ✅")
                        st.rerun()
                    else:
                        st.error("Plan is empty or invalid.")
            with st.form(f"cycle_meta_{mg}"):
                c = mapping[mg]
                cc1, cc2 = st.columns(2)
                crop_e = cc1.text_input("Crop", value=c["crop"], key=f"ce_{mg}")
                var_e = cc2.text_input("Variety", value=c["variety"], key=f"ve_{mg}")
                sd_e = st.date_input("Sowing date",
                                     value=dt.date.fromisoformat(c["sowing_date"]),
                                     key=f"se_{mg}")
                if st.form_submit_button("💾 Update cycle details"):
                    update_cycle(mg, crop_e.strip(), var_e.strip(), sd_e.isoformat())
                    st.success("Cycle updated ✅")
                    st.rerun()
            if st.button("🔒 Close cycle (season finished)", key=f"close_{mg}"):
                close_cycle(mg)
                st.success("Cycle closed.")
                st.rerun()


def render_pending(cid, cyc, stages):
    """Show the AI analysis result and let the user confirm / save it."""
    pend = st.session_state.get(f"pending_{cid}")
    if not pend:
        st.markdown("*Analysis results will appear here.*")
        return
    a = pend["analysis"]
    st.markdown(f"**AI source:** `{pend['source']}`")
    thumbs = st.columns(min(3, len(pend["paths"])))
    for i, p in enumerate(pend["paths"]):
        with thumbs[i % len(thumbs)]:
            if Path(p).exists():
                st.image(p, use_container_width=True)
            else:
                st.markdown("🖼️")
    m1, m2, m3 = st.columns(3)
    m1.metric("Growth stage", a["growth_stage"])
    m2.metric("Canopy cover", f'{a["canopy_cover_percent"]}%')
    m3.metric("Confidence", f'{a["confidence"]:.0%}')
    st.markdown("**Stress signs:** " + ", ".join(stress_label(s) for s in a["stress_signs"]))
    st.caption("💬 " + a["reason"])

    low = a["confidence"] < 0.6
    stage_names = [s["stage"] for s in stages]
    das_p = (dt.date.fromisoformat(pend["date"])
             - dt.date.fromisoformat(cyc["sowing_date"])).days
    if low:
        st.warning("⚠️ " + t("st_confirm"))
        default_idx = stage_names.index(a["growth_stage"]) if a["growth_stage"] in stage_names else 0
        chosen = st.selectbox("Pick the correct growth stage", stage_names,
                              index=default_idx, key=f"fix_{cid}")
    else:
        chosen = a["growth_stage"]
        # Show the predicted schedule status for the AI's own pick
        st.success("✅ Predicted status: " + t(status_tkey(compute_status(stages, das_p, chosen))))

    c1, c2 = st.columns(2)
    if c1.button("💾 Save observation", type="primary", use_container_width=True):
        status = compute_status(stages, das_p, chosen)
        add_observation(cid, pend["date"], pend["paths"][0], json.dumps(pend["paths"]),
                        chosen, a["canopy_cover_percent"], a["stress_signs"],
                        a["confidence"], status, a["reason"], 1 if low else 0,
                        pend["notes"])
        del st.session_state[f"pending_{cid}"]
        st.session_state["flash"] = f"Observation saved — status: {status}"
        st.rerun()
    if c2.button("✖ Discard", use_container_width=True):
        del st.session_state[f"pending_{cid}"]
        st.rerun()


def page_observe():
    st.subheader(t("nav_obs"))
    cyc = select_cycle("obs_cycle", active_only=True)
    if not cyc:
        return
    cid = cyc["id"]
    stages = get_stages(cid)
    sowing = dt.date.fromisoformat(cyc["sowing_date"])
    today = dt.date.today()
    das = (today - sowing).days
    if stages and das >= 0:
        exp = stages[expected_stage_index(stages, das)]
        st.info(f"📆 **{das} days after sowing** — expected stage: **{exp['stage']}**")

    c1, c2 = st.columns([1, 1.1])
    with c1:
        obs_date = st.date_input("Observation date", value=today, max_value=today)
        files = st.file_uploader("Field photos (1–5)",
                                 type=["jpg", "jpeg", "png", "webp"],
                                 accept_multiple_files=True)
        sim = st.checkbox("🧪 Use simulated photo (demo mode — no camera needed)",
                          value=True)
        notes = st.text_area("Notes (optional)", height=70)
        b_analyze = st.button("🔍 Analyze with AI", type="primary",
                              use_container_width=True)
        b_sim = st.button("⚡ " + t("btn_simulate"), use_container_width=True)

        # ---- run the analysis when a button is pressed ---------------------
        if b_analyze or b_sim:
            paths = []
            if not b_sim:                               # real uploads (if any)
                for f in (files or [])[:5]:
                    try:
                        img = Image.open(f).convert("RGB")
                        p = PHOTO_DIR / f"up_{uuid.uuid4().hex[:10]}.jpg"
                        img.save(p, "JPEG", quality=85)
                        paths.append(str(p))
                    except Exception:
                        st.error(f"Could not read image '{f.name}'.")
            if b_sim or (sim and not paths):            # simulated photo
                das_obs = (obs_date - sowing).days
                est_idx = expected_stage_index(stages, max(0, das_obs)) if stages else 0
                est_stage = stages[est_idx]["stage"] if stages else "Vegetative Growth"
                total = stages[-1]["end_day"] if stages else 120
                p = PHOTO_DIR / f"sim_{uuid.uuid4().hex[:10]}.jpg"
                make_demo_photo(cyc["crop"], est_stage,
                                canopy_curve(max(0, das_obs), total),
                                ["none"], uuid.uuid4().hex, p)
                paths = [str(p)]
            if not paths:
                st.error("Please upload at least one photo, or enable the simulated photo option.")
            else:
                with st.spinner("🤖 AI is analysing the photos…"):
                    analysis, source = ai_analyze_photos(cyc, stages, paths, obs_date, notes)
                st.session_state[f"pending_{cid}"] = {
                    "paths": paths, "analysis": analysis, "source": source,
                    "date": obs_date.isoformat(), "notes": notes}
                st.rerun()

    with c2:
        render_pending(cid, cyc, stages)


def canopy_figure(stages, obs):
    """Plotly chart: canopy % vs DAS with shaded expected stage bands."""
    fig = go.Figure()
    palette = ["#dcedc8", "#fff9c4", "#bbdefb", "#e1bee7",
               "#ffe0b2", "#b2dfdb", "#f8bbd0", "#d7ccc8"]
    for i, s in enumerate(stages):
        fig.add_shape(type="rect", x0=s["start_day"], x1=s["end_day"], y0=0, y1=100,
                      fillcolor=palette[i % len(palette)], opacity=0.35, line_width=0)
        fig.add_annotation(x=(s["start_day"] + s["end_day"]) / 2, y=97,
                           text=s["stage"], showarrow=False, font=dict(size=9),
                           opacity=0.75)
    if obs:
        fig.add_trace(go.Scatter(
            x=[o["das"] for o in obs], y=[o["canopy"] for o in obs],
            mode="lines", name="Canopy trend",
            line=dict(color="#2e7d32", width=2, shape="spline")))
        fig.add_trace(go.Scatter(
            x=[o["das"] for o in obs], y=[o["canopy"] for o in obs],
            mode="markers", name="Observations",
            marker=dict(size=11,
                        color=[STATUS_COLORS["Needs manual confirmation"] if o["needs_confirm"]
                               else STATUS_COLORS.get(o["status"], "#607d8b") for o in obs]),
            text=[f'{o["obs_date"]} • {o["stage"]} • {o["canopy"]:.0f}% canopy' for o in obs],
            hoverinfo="text+x+y"))
    fig.update_layout(height=400, yaxis=dict(range=[0, 105], title="Canopy cover %"),
                      xaxis=dict(title="Days after sowing"),
                      legend=dict(orientation="h", y=1.08),
                      margin=dict(l=40, r=16, t=30, b=40))
    return fig


def page_timeline():
    st.subheader(t("nav_timeline"))
    cyc = select_cycle("tl_cycle", active_only=False)
    if not cyc:
        return
    cid = cyc["id"]
    stages, obs = get_stages(cid), list_observations(cid)
    if cyc["status"] == "closed":
        st.info("🔒 This cycle is closed.")
    if obs:
        st.markdown("##### Photo timeline")
        wrap = st.columns(4)
        for i, o in enumerate(obs):
            with wrap[i % 4]:
                p = o["photo_path"]
                if p and Path(p).exists():
                    st.image(p, use_container_width=True)
                else:
                    st.markdown("🖼️ *photo missing*")
                st.caption(f'{o["obs_date"]} • {o["das"]} DAS • conf {o["confidence"]:.0%}')
                st.markdown(badge(o["stage"], "#455a64"), unsafe_allow_html=True)
                st.markdown(status_chip(o), unsafe_allow_html=True)
                stress = parse_stress(o)
                if stress != ["none"]:
                    st.caption("⚠️ " + ", ".join(stress_label(s) for s in stress))
        st.markdown("##### Canopy cover vs days after sowing")
        st.plotly_chart(canopy_figure(stages, obs), use_container_width=True)
        st.dataframe(pd.DataFrame([{
            "Date": o["obs_date"], "DAS": o["das"], "Stage": o["stage"],
            "Canopy %": o["canopy"], "Stress": ", ".join(parse_stress(o)),
            "Confidence": o["confidence"],
            "Status": "Needs manual confirmation" if o["needs_confirm"] else o["status"]
        } for o in obs]), use_container_width=True, hide_index=True)
    else:
        st.info("No observations yet — add one from **New Observation** or simulate one below.")
    if st.button("⚡ " + t("btn_simulate")):
        analysis, low = create_simulated_observation(cyc, stages, dt.date.today())
        st.session_state["flash"] = (
            f"Simulated observation saved — stage '{analysis['growth_stage']}', "
            f"canopy {analysis['canopy_cover_percent']}%" +
            (" (low confidence — flagged for manual confirmation)" if low else ""))
        st.rerun()


def page_reminders():
    st.subheader(t("nav_rem"))
    rem = reminders_data()
    if not rem:
        st.success(t("rem_none"))
        return
    for r in rem:
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"**{r['field_name']}** — {r['crop']} ({r['variety'] or '-'})")
        col1.caption("📷 No photos yet this season" if r["never"]
                     else f"📷 Last photo {r['gap']} days ago")
        # Cycle rows carry their primary key as 'id'; 'cycle_id' is an alias
        # added in reminders_data() — both are safe to use here.
        cid = r["id"]
        if col2.button("📸 Add photos", key=f"go_{cid}", use_container_width=True):
            st.session_state["page"] = "New Observation"
            st.session_state["obs_cycle"] = cid
            st.rerun()


def page_reports():
    st.subheader(t("nav_reports"))
    cyc = select_cycle("rep_cycle", active_only=False)
    if not cyc:
        return
    cid = cyc["id"]
    field = get_field(cyc["field_id"])
    stages, obs = get_stages(cid), list_observations(cid)
    lang = st.session_state.get("lang", "English")

    with st.spinner("✍️ Writing AI season summary…"):
        summary, source = ai_season_summary(field, cyc, stages, obs, lang)
    st.markdown(f"**AI season summary** · source: `{source}` · language: {lang}")
    direction = "rtl" if lang == "Urdu" else "ltr"
    st.markdown(f'<div dir="{direction}" style="font-size:1.05rem;line-height:1.7;">{summary}</div>',
                unsafe_allow_html=True)

    # The downloadable PDF always embeds the English summary (ReportLab core
    # fonts cannot render Arabic/Devanagari script reliably).
    if lang == "English":
        summary_en = summary
    else:
        st.caption("Note: the PDF uses the English summary for font compatibility; "
                   "the on-screen text above follows your selected language.")
        with st.spinner("Preparing the summary used inside the PDF…"):
            summary_en, _ = ai_season_summary(field, cyc, stages, obs, "English")

    if st.button("🛠 Build PDF report", type="primary"):
        try:
            st.session_state[f"pdf_{cid}"] = build_pdf(field, cyc, stages, obs, summary_en)
        except Exception as e:
            st.error(f"PDF generation failed: {e}")
    if st.session_state.get(f"pdf_{cid}"):
        st.download_button(
            "⬇️ Download PDF report", data=st.session_state[f"pdf_{cid}"],
            file_name=f"CropTimeline_{field['name'].replace(' ', '_')}_c{cid}.pdf",
            mime="application/pdf", use_container_width=True)


def page_settings():
    st.subheader(t("nav_settings"))
    if gemini_model() is not None:
        st.success("🤖 **Live AI engine:** Google Gemini `gemini-2.0-flash` — stage plans, "
                   "photo analysis and summaries use the real model.")
    else:
        st.info("🤖 **Running with the built-in offline simulator** (no API key needed). "
                "To switch to live Gemini AI, set the `GEMINI_API_KEY` environment variable "
                "or add `GEMINI_API_KEY = \"...\"` to `.streamlit/secrets.toml`.")
    st.markdown("##### Database")
    with get_conn() as conn:
        counts = {tbl: conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                  for tbl in ("fields", "cycles", "expected_stages", "observations")}
    c = st.columns(4)
    c[0].metric("Fields", counts["fields"])
    c[1].metric("Cycles", counts["cycles"])
    c[2].metric("Stage plans", counts["expected_stages"])
    c[3].metric("Observations", counts["observations"])
    st.markdown("##### Demo controls")
    st.caption("Loading the demo farm replaces all current data.")
    b1, b2 = st.columns(2)
    if b1.button("🎬 " + t("btn_load_demo"), use_container_width=True):
        seed_demo_data()
        st.session_state["just_seeded"] = True
        st.rerun()
    if b2.button("🗑️ " + t("btn_reset"), use_container_width=True):
        clear_all()
        st.rerun()


# ----------------------------------------------------------------------------
# Sidebar / navigation
# ----------------------------------------------------------------------------
PAGES = ["Dashboard", "Fields & Cycles", "New Observation",
         "Timeline", "Reminders", "Reports", "Settings"]
PAGE_TKEY = {"Dashboard": "nav_dashboard", "Fields & Cycles": "nav_fields",
             "New Observation": "nav_obs", "Timeline": "nav_timeline",
             "Reminders": "nav_rem", "Reports": "nav_reports",
             "Settings": "nav_settings"}


def render_sidebar() -> str:
    st.sidebar.markdown("## 🌾 CropTimeline")
    st.sidebar.caption(t("tagline"))
    lang = st.sidebar.selectbox(
        "🌐 " + t("lang_label"), ["English", "Urdu", "Hindi"],
        index=["English", "Urdu", "Hindi"].index(st.session_state.get("lang", "English")),
        format_func=lambda l: {"English": "English", "Urdu": "اردو (Urdu)",
                               "Hindi": "हिन्दी (Hindi)"}[l])
    st.session_state["lang"] = lang
    page = st.sidebar.radio("", PAGES, format_func=lambda p: t(PAGE_TKEY[p]),
                            key="page", label_visibility="collapsed")
    st.sidebar.markdown("---")
    if gemini_model() is not None:
        st.sidebar.success("🤖 AI: Gemini 2.0 Flash (live)")
    else:
        st.sidebar.info("🤖 AI: offline simulator\n\n(add GEMINI_API_KEY for live AI)")
    if st.sidebar.button("🎬 " + t("btn_load_demo"), use_container_width=True):
        seed_demo_data()
        st.session_state["just_seeded"] = True
        st.rerun()
    st.sidebar.caption(f"📅 {dt.date.today().isoformat()} • data stored locally in SQLite")
    return page


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="CropTimeline 🌾", page_icon="🌾", layout="wide")
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    # First launch → auto-load the live demo farm (no blank dashboard!)
    if not list_fields():
        seed_demo_data()
        st.session_state["just_seeded"] = True

    page = render_sidebar()
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    router = {"Dashboard": page_dashboard, "Fields & Cycles": page_fields,
              "New Observation": page_observe, "Timeline": page_timeline,
              "Reminders": page_reminders, "Reports": page_reports,
              "Settings": page_settings}
    router.get(page, page_dashboard)()


main()