
import streamlit as st
import pandas as pd
from datetime import datetime
import os
from io import BytesIO
from streamlit_quill import st_quill
import re
import html
import base64
import textwrap
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont
from urllib.parse import urlparse

st.set_page_config(layout="wide")
st.markdown("""
<style>
.block-container {
    max-width: 900px;
    margin: auto;
}    
</style>
""", unsafe_allow_html=True)
st.markdown("""
<style>
/* layout */
.block-container { max-width: 1100px; padding-top: 1rem; }

/* font e titoli */
h1, h2, h3 { font-weight: 800; }

/* bottoni grandi */
.stButton>button, .stDownloadButton>button, .stLinkButton>button {
  width: 100%;
  padding: 16px 18px;
  font-size: 18px;
  font-weight: 800;
  border-radius: 14px;
}

/* input più grandi */
.stTextInput input, .stTextArea textarea, .stSelectbox div, .stDateInput input {
  font-size: 16px;
}

/* card effetto intranet */
.intra-card {
  border: 1px solid rgba(255,255,255,0.25);
  border-radius: 16px;
  padding: 14px 14px;
  background: rgba(255,255,255,0.06);
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# 🔒 STORAGE PERSISTENTE RENDER — MOUNT: /var/dati
# =========================================================
DATA_DIR = "/var/dati"
UPLOAD_DIR = "/var/dati/uploads"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

LOG_FILE = "/var/dati/log.csv"
MSG_FILE = "/var/dati/messaggi.csv"
PDV_FILE = "/var/dati/pdv.csv"

HOME_URL = "https://eu.jotform.com/it/app/build/253605296903360"


# =========================================================
# 🎨 CSS DASHBOARD ADMIN
# =========================================================
CSS_ADMIN = """
<style>
.stApp { background-color: #E6E6E6 !important; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }
hr { border: 1px solid #000 !important; }
input, textarea, select {
  background: #fff !important;
  color: #D50000 !important;
  border: 2px solid #000 !important;
  border-radius: 8px !important;
}
label { color:#000 !important; font-weight:800 !important; }

.stButton > button, .stDownloadButton > button {
  background: #D50000 !important;
  color: #fff !important;
  border: 1px solid #000 !important;
  font-weight: 800 !important;
  border-radius: 10px !important;
  padding: 10px 16px !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: #B30000 !important;
}

div[data-testid="stSuccess"] {
  background-color: #E3F2FD !important;
  color: #D50000 !important;
  font-weight: 800 !important;
  border: 2px solid #000 !important;
}
div[data-testid="stSuccess"] p,
div[data-testid="stSuccess"] span { color: #D50000 !important; }

div[data-testid="stAlert"] { border: 2px solid #000 !important; }
div[data-testid="stAlert"] p {
  color: #D50000 !important;
  font-weight: 800 !important;
}

h1, h2, h3, .stMarkdown, label {
  color: #000 !important;
  font-weight: 800 !important;
}
/* Testo file caricato leggibile */
div[data-testid="stFileUploader"] span {
  color: #000 !important;
}

div[data-testid="stFileUploader"] p {
  color: #000 !important;
}

</style>
"""


# =========================================================
# UTILS
# =========================================================
def load_csv(path, cols):
    if os.path.exists(path):
        return pd.read_csv(path, dtype=str).fillna("")
    return pd.DataFrame(columns=cols)


def save_csv(df, path):
    df.to_csv(path, index=False)


def now_str():
    return datetime.now().strftime("%d-%m-%Y %H:%M:%S")


def excel_bytes(df):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return out.getvalue()


def normalize_lines(text: str) -> str:
    return text or ""

def strip_html_to_text(s: str) -> str:
    s = s or ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    return s.strip()


def first_line_title(html_msg: str) -> str:
    txt = strip_html_to_text(html_msg)
    if not txt:
        return "SENZA TITOLO"
    return txt.splitlines()[0].strip() or "SENZA TITOLO"


def stato_msg(inizio: str, fine: str) -> str:
    try:
        di = datetime.strptime(inizio, "%d-%m-%Y").date()
        df = datetime.strptime(fine, "%d-%m-%Y").date()
        oggi = datetime.now().date()
        return "ATTIVO" if di <= oggi <= df else "CHIUSO"
    except Exception:
        return ""


def stato_da_fullmsg(full_msg: str, msg_df: pd.DataFrame) -> str:
    if full_msg in ("PRESENZA", "GENERICO"):
        return "nm"
    if msg_df.empty:
        return ""
    m = msg_df[msg_df["msg"] == full_msg]
    if m.empty:
        return ""
    r = m.iloc[0]
    return stato_msg(r["inizio"], r["fine"])

def extract_urls_from_html(html_msg: str) -> list[str]:
    s = html_msg or ""
    # prende URL sia da href che da testo incollato
    urls = re.findall(r'href=[\'"]([^\'"]+)[\'"]', s, flags=re.IGNORECASE)
    urls += re.findall(r'(https?://[^\s"<>\]]+)', s, flags=re.IGNORECASE)

    # pulizia e dedup mantenendo ordine
    out = []
    seen = set()
    for u in urls:
        u = u.strip().rstrip(").,;")
        if not u:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def classify_url(u: str):
    u_low = (u or "").lower()

    if "youtube.com" in u_low or "youtu.be" in u_low:
        return ("🎬 Guarda video", "video")

    if u_low.endswith(".pdf"):
        return ("📄 Apri PDF", "pdf")

    if "drive.google.com" in u_low or "docs.google.com" in u_low:
        return ("☁️ Apri Drive", "drive")

    if "teams.microsoft.com" in u_low:
        return ("🧩 Apri Teams", "teams")

    if "wa.me" in u_low or "whatsapp.com" in u_low:
        return ("💬 Apri WhatsApp", "whatsapp")

    return ("🌐 Apri sito", "web")

# =========================================================
# 🖼️ RENDER MESSAGGIO → IMMAGINE
# =========================================================
def render_msg_image(html_msg: str, logo_path="logo.png"):

    text = strip_html_to_text(html_msg)

    # --- PARAMETRI GRAFICI ---
    width = 900
    padding = 40
    bg_color = "white"
    border_color = "#C00000"
    text_color = "black"

    # --- FONT ---
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        font_text = ImageFont.truetype("DejaVuSans.ttf", 26)
        font_date = ImageFont.truetype("DejaVuSans.ttf", 20)
    except:
        font_title = font_text = font_date = ImageFont.load_default()

    # --- TITOLO AUTOMATICO ---
    title = first_line_title(html_msg)

    # --- WRAP TESTO ---
    wrapper = textwrap.TextWrapper(width=60)
    lines = wrapper.wrap(text)

    # --- CALCOLO ALTEZZA ---
    line_h = font_text.getbbox("A")[3] + 8
    text_height = len(lines) * line_h

    header_h = 120
    height = header_h + text_height + padding * 2

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # --- BORDO ---
    draw.rounded_rectangle(
        (5, 5, width - 5, height - 5),
        radius=20,
        outline=border_color,
        width=4
    )

    # --- LOGO ---
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((220, 80))
        img.paste(logo, (padding, 20), logo)

    # --- DATA ---
    data_txt = datetime.now().strftime("%d/%m/%Y")
    draw.text(
        (width - 160, 35),
        data_txt,
        font=font_date,
        fill=text_color
    )

    # --- TITOLO ---
    draw.text(
        (padding, 110),
        title,
        font=font_title,
        fill=border_color
    )

    # --- TESTO ---
    y = 160
    for line in lines:
        draw.text((padding, y), line, font=font_text, fill=text_color)
        y += line_h

    return img


# =========================================================
# ADMIN
# =========================================================
def admin():
    st.markdown(CSS_ADMIN, unsafe_allow_html=True)

    if os.path.exists("logo.png"):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.image("logo.png", width=260)

    st.title("DASHBOARD ADMIN")

    if st.text_input("Password", type="password") != "GianAri2026":
        st.warning("Inserire password admin")
        return

    if st.button("AGGIORNA"):
        st.rerun()

    # ===== DIVISIONE PAGINE ADMIN =====
    tab_operativo, tab_report = st.tabs(["OPERATIVO", "REPORT"])

    # ================= OPERATIVO =================
    with tab_operativo:

        st.header("IMPORTA LISTA PDV")

        pdv_existing = load_csv(PDV_FILE, ["ID", "PDV"])
        prefill = "\n".join([f"{r['ID']};{r['PDV']}" for _, r in pdv_existing.iterrows()])
        pdv_text = st.text_area("", value=prefill, height=140)

        c1, c2 = st.columns(2)

        with c1:
            if st.button("SALVA LISTA PDV"):
                rows = []
                for line in pdv_text.splitlines():
                    if ";" in line:
                        a, b = line.split(";", 1)
                        rows.append([a.strip(), b.strip()])
                save_csv(pd.DataFrame(rows, columns=["ID", "PDV"]), PDV_FILE)
                st.success("Lista PDV salvata")

        with c2:
            if st.button("PULISCI LISTA PDV"):
                save_csv(pd.DataFrame(columns=["ID", "PDV"]), PDV_FILE)
                st.success("Lista PDV pulita")

        st.markdown("---")

        st.header("CREA NUOVO MESSAGGIO")
        st.caption("Scrivi il messaggio e aggiungi eventuali link. Usa lo stile solo se serve.")
        
        msg = st_quill(
            html=True,
            toolbar=[
            [{"header": [1, 2, 3, False]}],
            ["bold", "italic", "underline", "strike"],
            [{"color": []}, {"background": []}],
            [{"align": []}],
            [{"list": "ordered"}, {"list": "bullet"}],
            [{"indent": "-1"}, {"indent": "+1"}],
            ["blockquote", "code-block"],
            ["link", "clean"]
        ]
    )           
        uploaded = st.file_uploader(
            "ALLEGATO (immagine o PDF)",
            type=["png", "jpg", "jpeg", "pdf"]
        )

        c1, c2 = st.columns(2)
        with c1:
            data_inizio = st.date_input("DATA INIZIO")
        with c2:
            data_fine = st.date_input("DATA FINE")

        pdv_ids = st.text_area("ID PDV (uno per riga)", height=140)

        if st.button("SALVA MESSAGGIO"):
            df = load_csv(MSG_FILE, ["msg", "inizio", "fine", "pdv_ids", "file"])

            filename = ""
            if uploaded:
                filename = uploaded.name
                with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
                    f.write(uploaded.getbuffer())

            new = pd.DataFrame([[
                msg,
                data_inizio.strftime("%d-%m-%Y"),
                data_fine.strftime("%d-%m-%Y"),
                normalize_lines(pdv_ids),
                filename
            ]], columns=df.columns)

            save_csv(pd.concat([df, new], ignore_index=True), MSG_FILE)
            st.success("Messaggio salvato")
        if st.button("LOGOUT", key="logout_operativo"):
            st.session_state["admin_ok"] = False
            st.rerun()

    # ================= REPORT =================
    with tab_report:

        st.header("STORICO MESSAGGI")

        msg_df = load_csv(MSG_FILE, ["msg", "inizio", "fine", "pdv_ids", "file"])

        view = msg_df.copy()
        if not view.empty:
            view.insert(0, "N°", range(1, len(view) + 1))
            view["MESSAGGIO"] = view["msg"].apply(first_line_title)
            view["STATO"] = view.apply(lambda r: stato_msg(r["inizio"], r["fine"]), axis=1)
            view = view[["N°", "MESSAGGIO", "inizio", "fine", "STATO", "pdv_ids"]]

        st.dataframe(view)

        if not msg_df.empty:
            idx_open = st.number_input("Apri messaggio (N°)", min_value=0, max_value=len(msg_df), value=0, step=1)
            if idx_open and 1 <= idx_open <= len(msg_df):
                r = msg_df.iloc[idx_open - 1]

        # 👇 BLOCCO OPZIONALE - Consigliato
                msg_edit = st_quill(
                value=r["msg"],
                html=True,
                toolbar=[
                [{"header": [1, 2, 3, False]}],
                ["bold", "italic", "underline", "strike"],
                [{"color": []}, {"background": []}],
                [{"align": []}],
                [{"list": "ordered"}, {"list": "bullet"}],
                [{"indent": "-1"}, {"indent": "+1"}],
                ["blockquote", "code-block"],
                ["link", "clean"]
        ]
    )

        if not msg_df.empty:
            del_idx = st.multiselect(
                "Rimuovi manualmente messaggi (seleziona N°)",
                options=list(range(1, len(msg_df) + 1))
            )
            if st.button("ELIMINA RIGHE MESSAGGI SELEZIONATE"):
                if del_idx:
                    keep = msg_df.drop(index=[i - 1 for i in del_idx]).reset_index(drop=True)
                    save_csv(keep, MSG_FILE)
                    st.success("Righe messaggi eliminate")
                    st.rerun()

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button("SCARICA CSV", msg_df.to_csv(index=False), "messaggi.csv")
        with c2:
            st.download_button("SCARICA EXCEL", excel_bytes(msg_df), "messaggi.xlsx")
        with c3:
            if st.button("PULISCI MESSAGGI"):
                save_csv(msg_df.iloc[0:0], MSG_FILE)
                st.success("Messaggi puliti")
                st.rerun()

        st.markdown("---")

        st.header("REPORT LOG")

        log = load_csv(LOG_FILE, ["data", "pdv", "msg"])

        log_view = log.copy()
        if not log_view.empty:
            log_view.insert(0, "N°", range(1, len(log_view) + 1))
            log_view["messaggio"] = log_view["msg"].apply(
                lambda m: "GENERICO" if m in ("PRESENZA", "GENERICO") else first_line_title(m)
            )
            log_view["stato"] = log_view["msg"].apply(lambda m: stato_da_fullmsg(m, msg_df))
            log_view = log_view[["N°", "data", "pdv", "messaggio", "stato"]]

        st.dataframe(log_view)

        if not log.empty:
            del_log_idx = st.multiselect(
                "Rimuovi manualmente righe LOG (seleziona N°)",
                options=list(range(1, len(log) + 1))
            )
            if st.button("ELIMINA RIGHE LOG SELEZIONATE"):
                if del_log_idx:
                    keep = log.drop(index=[i - 1 for i in del_log_idx]).reset_index(drop=True)
                    save_csv(keep, LOG_FILE)
                    st.success("Righe log eliminate")
                    st.rerun()

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button("SCARICA CSV", log.to_csv(index=False), "report.csv")
        with c2:
            st.download_button("SCARICA EXCEL", excel_bytes(log), "report.xlsx")
        with c3:
            if st.button("PULISCI LOG"):
                save_csv(log.iloc[0:0], LOG_FILE)
                st.success("Log pulito")
                st.rerun()
            if st.button("LOGOUT", key="logout_report"):
                st.session_state["admin_ok"] = False
                st.rerun()


# =========================================================
# DIPENDENTI
# =========================================================
def dipendenti():
    st.markdown("""
    <style>
    .stApp {background:#f4f4f4;}
    label, h1, h2, h3 {color:white;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <style>
    .msgbox{
    background:#ffffff;
    color:#000000;
    padding:24px;
    border-radius:12px;
    box-sizing:border-box;
    overflow-wrap:anywhere;
}

    .msgbox p,
    .msgbox ul,
    .msgbox ol,
    .msgbox li,
    .msgbox h1,
    .msgbox h2,
    .msgbox h3 {
       margin: 0 !important;   
}

</style>
""", unsafe_allow_html=True)
    
    st.markdown("""
<style>
.msgbox a {
    color: #0066cc !important;
    text-decoration: underline !important;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

    if os.path.exists("logo.png"):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.image("logo.png", width=240)

    st.markdown("<h1 style='text-align:center;'>INDICAZIONI OPERATIVE</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;'>SELEZIONA IL TUO PDV</h3>", unsafe_allow_html=True)

    pdv_df = load_csv(PDV_FILE, ["ID", "PDV"])
    if pdv_df.empty:
        st.warning("Archivio PDV vuoto")
        return

    scelta = st.selectbox("", pdv_df["PDV"], index=None, placeholder="Digita la città...")

    st.markdown(
        "<p style='text-align:center;'><b>"
        "digita le prime lettere della Città"
        "</b></p>",
        unsafe_allow_html=True
    )

    if not scelta:
        return

    pdv_id = pdv_df.loc[pdv_df["PDV"] == scelta, "ID"].values[0]
    pdv_id = str(pdv_id).strip()

    msg_df = load_csv(MSG_FILE, ["msg", "inizio", "fine", "pdv_ids", "file"])
    oggi = datetime.now().date()
    mostrati = []

    for _, r in msg_df.iterrows():
        ids = [x.strip() for x in (r["pdv_ids"] or "").splitlines() if x.strip()]
        if pdv_id in ids:
            try:
                di = datetime.strptime(r["inizio"], "%d-%m-%Y").date()
                df = datetime.strptime(r["fine"], "%d-%m-%Y").date()
                if di <= oggi <= df:
                    mostrati.append(r)
            except Exception:
                pass

    log_df = load_csv(LOG_FILE, ["data", "pdv", "msg"])

    # ===== MESSAGGIO GENERICO =====
    if not mostrati:
        st.markdown("""
        <div class='msgbox' style='text-align:center;font-weight:800;font-size:18px;'>
        QUESTA MATTINA NON SONO PREVISTE PROMO-ATTIVITA' PARTICOLARI. BUON LAVORO
        </div>
        """, unsafe_allow_html=True)

        if st.checkbox("Spunta CONFERMA DI PRESENZA"):
            new = pd.DataFrame([[now_str(), scelta, "PRESENZA"]], columns=log_df.columns)
            save_csv(pd.concat([log_df, new], ignore_index=True), LOG_FILE)
            st.success("Presenza registrata")

        return

        # ===== MESSAGGI OPERATIVI =====
    for i, r in enumerate(mostrati):

        # 🖼️ RENDER IMMAGINE
                st.markdown(f"""
                <div lang="it" translate="no" style="
                background-color: white;
                padding: 25px;
                border-radius: 12px;
                margin-bottom: 20px;
                color: black;
                box-shadow: 0 6px 18px rgba(0,0,0,0.18);
                border-top: 6px solid #d50000;
                border: 2px solid #e5e5e5;
                ">

               <div style="display:flex;justify-content:space-between;alig-items:center;">
               <img src="URL_LOGO" width="130">
               <div style=font-size:14px;
               color:#555;">
               {now_str().split(" ")[0]}
               </div>
               </div>

               <hr style="margin:15px 0; border:none; border-top:2px solid #e5e5e5;">
                
                <div style="font-size:22px; 
                font-weight:700; margin-bottom:10px;">
                MESSAGGIO OPERATIVO
                </div>

                """, unsafe_allow_html=True)

                st.markdown(r["msg"],unsafe_allow_html=True)

                st.markdown("<"/div>",unsafe_allow_html=True)

        # ===== ALLEGATO =====
        if r["file"]:
            path = os.path.join(UPLOAD_DIR, r["file"])

            if os.path.exists(path):

                # Immagine extra
                if not r["file"].lower().endswith(".pdf"):
                    st.image(path)

                # PDF scaricabile
                if r["file"].lower().endswith(".pdf"):
                    with open(path, "rb") as f:
                        st.download_button(
                            label="Scarica allegato PDF",
                            data=f.read(),
                            file_name=r["file"]
                        )

    # ===== CHECKBOX =====
    lettura = st.checkbox(
        "Spunta di PRESA VISIONE",
        key=f"l_{pdv_id}_{i}"
    )

    presenza = st.checkbox(
        "Spunta CONFERMA DI PRESENZA",
        key=f"p_{pdv_id}_{i}"
    )

    if lettura and presenza:

        gia_registrato = (
            (log_df["pdv"] == scelta) &
            (log_df["msg"] == r["msg"])
        ).any()

        if not gia_registrato:

            new_row = pd.DataFrame(
                [[now_str(), scelta, r["msg"]]],
                columns=log_df.columns
            )

            updated_df = pd.concat(
                [log_df, new_row],
                ignore_index=True
            )

            save_csv(updated_df, LOG_FILE)
            st.success("Registrato")

        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("---")
    st.link_button("HOME", HOME_URL)

# =========================================================
# ROUTER
# =========================================================
if st.query_params.get("admin") == "1":
    admin()
else:
    dipendenti()





















































































