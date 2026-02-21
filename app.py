import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import altair as alt

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- CONSTANTES ET LOGIQUE MÉTIER ---
MOTS_EXCLUSION = {"BERNOIS", "NEUCHATELOIS", "VALAISANS", "GENEVOIS", "VAUDOIS", "FRIBOURGEOIS"}
COULEURS_PROF = {"Physiothérapie": "#00CCFF", "Ergothérapie": "#FF9900", "Massage": "#00CC96", "Autre": "#AB63FA"}

def assigner_profession(code):
    """Logique métier spécifique au module Tarifs"""
    c = str(code).strip().lower()
    if 'rem' in c: return "Autre"
    if any(x in c for x in ['privé', 'abo', 'thais']) or c.startswith(('73', '25', '15.30')): 
        return "Physiothérapie"
    if any(x in c for x in ['foyer']) or c.startswith(('76', '31', '32')): 
        return "Ergothérapie"
    if c.startswith('1062'): 
        return "Massage"
    return "Autre"

def convertir_date(val):
    """Conversion robuste des dates pour tous les modules"""
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    if isinstance(val, pd.Timestamp): return val
    try:
        return pd.to_datetime(str(val).strip(), format="%d.%m.%Y", errors="coerce")
    except:
        return pd.to_datetime(val, errors="coerce")

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
    """Calcul de probabilité de paiement pour le module Facturation"""
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    if p_hist.empty: return liq, taux_glob
    for h in jours_horizons:
        stats_croisees = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        stats_fourn = p_hist.groupby("fournisseur")["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        total_h = 0.0
        for _, row in f_attente.iterrows():
            key = (row["assureur"], row["fournisseur"])
            prob = stats_croisees.get(key, stats_fourn.get(row["fournisseur"], taux_glob[h]))
            total_h += row["montant"] * prob
        liq[h] = total_h
    return liq, taux_glob

# --- INITIALISATION DE L'ÉTAT ---
if 'page' not in st.session_state:
    st.session_state.page = "accueil"
if 'analyse_lancee' not in st.session_state:
    st.session_state.analyse_lancee = False

# ==========================================
# 🏠 PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse de Santé")
    st.markdown("---")
    st.write("### Choisissez le module d'analyse souhaité :")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info("📊 **MODULE FACTURATION**")
        st.write("Analyse des liquidités et délais.")
        if st.button("Accéder à la Facturation", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
            
    with col2:
        st.success("🩺 **MODULE MÉDECINS**")
        st.write("Analyse du CA et tendances.")
        if st.button("Accéder aux Médecins", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()

    with col3:
        st.warning("🏷️ **MODULE TARIFS**")
        st.write("Revenus mensuels par métier.")
        if st.button("Accéder aux Tarifs", use_container_width=True):
            st.session_state.page = "tarifs"
            st.rerun()

    with col4:
        st.info("🏦 **BILAN COMPTABLE**")
        st.write("Clôture CA et Impayés au 31.12.")
        if st.button("Accéder au Bilan", use_container_width=True, type="primary"):
            st.session_state.page = "bilan"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES (ORIGINAL)
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("📊 Analyse de la Facturation")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx", key="fact_file")

    if uploaded_file:
        try:
            df_brut =
