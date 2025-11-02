# -*- coding: utf-8 -*-
import re
import pandas as pd
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="CWR Extractor", layout="wide")

st.title("CWR Extractor - ACKs y Obras")
st.write("Extrae ACKs con códigos de sociedad y obras con sus códigos")

# ==================== EXPRESIONES REGULARES ====================
CU_RE = re.compile(r"\bCU\d+\b")
ESCU_RE = re.compile(r"\bESCU\d+\b")
SOCIETY_CODE_RE = re.compile(r"\b(\d{6,15})\b")
DATE_STATUS_RE = re.compile(r"\b(\d{8})([A-Z]{2,3})?\b")
ACK_PREFIX_RE = re.compile(r"^ACK[0-9 ]*")
REV_PREFIX_RE = re.compile(r"^REV[0-9 ]*")

# ==================== FUNCIONES ====================

def clean_spaces(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s.strip())

def detect_encoding(file_bytes):
    for encoding in ['utf-8', 'iso-8859-1', 'cp1252', 'ascii']:
        try:
            file_bytes.decode(encoding)
            return encoding
        except:
            continue
    return 'utf-8'

def parse_ack_line(line: str) -> dict:
    """Extrae título, submitter y código de sociedad"""
    data = {
        "title": "", 
        "submitter": "", 
        "society_code": "",
        "date": "", 
        "status": ""
    }
    
    cu = CU_RE.search(line)
    if not cu:
        return data
    
    data["submitter"] = cu.group(0)
    
    left = line[:cu.start()]
    title_guess = ACK_PREFIX_RE.sub("", left)
    title_guess = clean_spaces(title_guess)
    
    if len(title_guess) > 140:
        title_guess = title_guess[-140:]
    
    right = line[cu.end():]
    society_match = SOCIETY_CODE_RE.search(right)
    if society_match:
        data["society_code"] = society_match.group(1)
        
        right2 = right[society_match.end():]
        ds = DATE_STATUS_RE.search(right2)
        if ds:
            data["date"] = ds.group(1)
            if ds.group(2):
                data["status"] = ds.group(2)
    
    data["title"] = title_guess
    return data

def parse_nwr_line(line: str) -> dict:
    """Extrae info de obra (NWR)"""
    cu_match = CU_RE.search(line) or ESCU_RE.search(line)
    codigo_obra = cu_match.group(0) if cu_match else ""
    
    if cu_match:
        titulo = line[:cu_match.start()]
        titulo = re.sub(r'^NWR\d*\s*', '', titulo)
        titulo = clean_spaces(titulo)[:80]
    else:
        titulo = clean_spaces(line[10:80])
    
    return {
        "titulo": titulo,
        "codigo_obra": codigo_obra
    }

def parse_rev_line(line: str) -> str:
    """Extrae título de REV"""
    m = re.search(r"\b(ESCU\d+|CU\d+)\b", line)
    if not m:
        return ""
    left = line[:m.start()]
    left = REV_PREFIX_RE.sub("", left)
    return clean_spaces(left)

def to_date_human(d: str) -> str:
    if not d or len(d) != 8:
        return ""
    try:
        return datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d")
    except:
        return ""

# ==================== UPLOAD ====================
uploaded = st.file_uploader(
    "Selecciona archivos CWR/TXT",
    type=["cwr", "txt", "v21", "v22", "v23"],
    accept_multiple_files=True
)

if uploaded:
    all_acks = []
    all_obras = []
    
    for up in uploaded:
        name = up.name
        file_bytes = up.read()
        encoding = detect_encoding(file_bytes)
        content = file_bytes.decode(encoding, errors="replace")
        lines = content.splitlines()
        
        last_rev_title = ""
        
        for i, raw in enumerate(lines, start=1):
            line = raw.rstrip("\r\n").strip()
            
            if not line or len(line) < 3:
                continue
            
            record_type = line[:3]
            
            # REV
            if record_type == "REV":
                last_rev_title = parse_rev_line(line)
            
            # ACK
            elif record_type == "ACK":
                data = parse_ack_line(line)
                
                if len(data.get("title", "")) < 3 and last_rev_title:
                    data["title"] = last_rev_title
                
                data["title"] = clean_spaces(data.get("title", ""))
                data["file"] = name
                data["line_no"] = i
                data["date_human"] = to_date_human(data.get("date", ""))
                
                all_acks.append(data)
            
            # NWR (Obra)
            elif record_type == "NWR":
                data = parse_nwr_line(line)
                data["file"] = name
                data["line_no"] = i
                
                all_obras.append(data)
    
    # ==================== RESULTADOS ====================
    
    tabs = st.tabs(["ACKs", "Obras"])
    
    # TAB: ACKs
    with tabs[0]:
        if all_acks:
            df = pd.DataFrame(all_acks)
            
            st.success(f"ACKs detectados: {len(df)}")
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Descargar ACKs CSV",
                data=csv,
                file_name="acks_extraidos.csv",
                mime="text/csv"
            )
            
            with st.expander("Resumen por estatus"):
                st.write(df.groupby("status", dropna=False)["file"].count().rename("conteo"))
        else:
            st.info("No se detectaron líneas ACK en los archivos subidos.")
    
    # TAB: Obras
    with tabs[1]:
        if all_obras:
            df = pd.DataFrame(all_obras)
            
            st.success(f"Obras detectadas: {len(df)}")
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Descargar Obras CSV",
                data=csv,
                file_name="obras_extraidas.csv",
                mime="text/csv"
            )
        else:
            st.info("No se detectaron líneas NWR en los archivos subidos.")

else:
    st.info("Sube uno o varios archivos CWR para comenzar")