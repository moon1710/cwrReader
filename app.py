# -*- coding: utf-8 -*-
import re
import io
from datetime import datetime
from typing import List, Dict
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CWR ACK Extractor", layout="wide")

st.title("📄 CWR ACK Extractor (SADAIC y otras sociedades)")
st.write(
    "Sube uno o varios archivos CWR/TXT. "
    "El visor localizará registros **ACK** y extraerá Título, Submitter Creation #, "
    "Recipient Creation #, Fecha y Estatus."
)

uploaded = st.file_uploader(
    "Selecciona archivos .v21 / .cwr / .txt",
    type=["cwr", "txt", "v21"],
    accept_multiple_files=True
)

# ----------------- Utilidades -----------------
CU_RE = re.compile(r"\bCU\d+\b")
RECIPIENT_RE = re.compile(r"\b(\d{6,15})\b")         # 6-15 dígitos contínuos
DATE_STATUS_RE = re.compile(r"\b(\d{8})([A-Z]{2})?\b")
ACK_PREFIX_RE = re.compile(r"^ACK[0-9 ]*")

def clean_spaces(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s.strip())

def guess_title_from_segment(seg: str) -> str:
    """
    Intenta limpiar el 'header' de ACK para dejar el título.
    Elimina el prefijo 'ACK' + números si aparecen al inicio.
    """
    s = ACK_PREFIX_RE.sub("", seg)       # quita "ACK0000..."
    s = clean_spaces(s)
    return s

def parse_ack_line(line: str) -> Dict:
    """
    Extrae {title, submitter, recipient, date, status} de una línea ACK.
    Usa heurísticas robustas basadas en tokens (CU####, fecha, etc.).
    """
    out = {"title": "", "submitter": "", "recipient": "", "date": "", "status": ""}

    cu = CU_RE.search(line)
    if not cu:
        return out

    out["submitter"] = cu.group(0)

    # Lo que hay antes del CU suele contener el título (con ruido)
    left = line[:cu.start()]
    title_guess = guess_title_from_segment(left)

    # En ocasiones el left contiene más texto técnico; acota tomando las últimas ~120 chars
    if len(title_guess) > 140:
        title_guess = title_guess[-140:]

    # Busca recipient (número largo) DESPUÉS del CU
    right = line[cu.end():]

    # 1) recipient = primer bloque de dígitos "largo"
    rec_m = RECIPIENT_RE.search(right)
    if rec_m:
        out["recipient"] = rec_m.group(1)

        # 2) fecha (+estatus) típicamente viene después del recipient
        right2 = right[rec_m.end():]
        ds = DATE_STATUS_RE.search(right2)
        if ds:
            out["date"] = ds.group(1)
            if ds.group(2):
                out["status"] = ds.group(2)

    out["title"] = title_guess
    return out

def parse_rev_title(line: str) -> str:
    """
    Extrae un posible título de la línea REV, como respaldo.
    Muchas REV llevan '...<TÍTULO> ... ESCU#### ...'
    """
    # Busca el token ESCU#### o CU#### y toma lo que hay antes como título bruto.
    m = re.search(r"\b(ESCU\d+|CU\d+)\b", line)
    if not m:
        return ""
    left = line[:m.start()]
    # Quita prefijo 'REV' + números
    left = re.sub(r"^REV[0-9 ]*", "", left)
    return clean_spaces(left)

def to_date_human(d: str) -> str:
    if not d or len(d) != 8:
        return ""
    try:
        return datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return ""

# ----------------- Lógica principal -----------------
if uploaded:
    rows: List[Dict] = []

    for up in uploaded:
        name = up.name
        content = up.read().decode("ascii", errors="ignore")
        lines = content.splitlines()

        last_rev_title = ""  # por si un ACK no trae título claro, usamos el de la REV cercana

        for i, raw in enumerate(lines, start=1):
            line = raw.rstrip("\r\n")

            if line.startswith("REV"):
                # Guarda título de la REV por si luego el ACK es críptico
                last_rev_title = parse_rev_title(line)
                continue

            if not line.startswith("ACK"):
                continue

            data = parse_ack_line(line)

            # Si el título quedó vacío o muy corto, usa el último título REV visto
            if len(data.get("title", "")) < 3 and last_rev_title:
                data["title"] = last_rev_title

            # Limpieza final
            data["title"] = clean_spaces(data.get("title", ""))
            data["file"] = name
            data["line_no"] = i
            data["date_human"] = to_date_human(data.get("date", ""))

            rows.append(data)

    if not rows:
        st.info("No se detectaron líneas ACK en los archivos subidos.")
    else:
        df = pd.DataFrame(rows, columns=[
            "file", "line_no", "title", "submitter", "recipient", "date", "date_human", "status"
        ])

        st.success(f"ACKs detectados: {len(df)}")
        st.dataframe(df, use_container_width=True)

        # Descarga CSV
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar CSV",
            data=csv_bytes,
            file_name="acks_extraidos.csv",
            mime="text/csv"
        )

        # Pequeño resumen por estatus
        with st.expander("Resumen por estatus"):
            st.write(df.groupby("status", dropna=False)["file"].count().rename("conteo"))
