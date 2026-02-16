import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- INITIALISATION DE LA NAVIGATION ---
if 'page' not in st.session_state:
    st.session_state.page = "accueil"

# --- FONCTIONS UTILES (Communes) ---
def convertir_date(val):
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    if isinstance(val, pd.Timestamp): return val
    try:
        return pd.to_datetime(str(val).strip(), format="%d.%m.%Y", errors="coerce")
    except:
        return pd.NaT

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
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

# ==========================================
# 🏠 PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse de Facturation")
    st.write("Bienvenue dans votre outil d'analyse. Choisissez un module ci-dessous :")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("### 📊 Analyse des Factures")
        st.write("Suivi des liquidités, délais de paiement par assureur et analyse des retards.")
        if st.button("Accéder au module Factures", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
            
    with col2:
        st.success("### 👨‍⚕️ Analyse des Médecins")
        st.write("Analyse du chiffre d'affaires par médecin prescripteur et évolution mensuelle.")
        if st.button("Accéder au module Médecins", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour à l'accueil"):
        st.session_state.page = "accueil"
        st.rerun()
        
    st.title("📊 Analyse de la Facturation")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx", key="fact_file")

    if uploaded_file:
        df_brut = pd.read_excel(uploaded_file, header=0)
        # --- ICI TU INSÈRES TOUT TON CODE DE L'ANALYSE FACTURE (Partie 1 & 2) ---
        # (Filtres, calculs de délais, tabs 1 à 4, etc.)
        st.write("Le moteur d'analyse des factures est actif.")
    else:
        st.info("Veuillez charger un fichier dans la barre latérale.")

# ==========================================
# 👨‍⚕️ MODULE MÉDECINS
# ==========================================
elif st.session_state.page == "medecins":
    if st.sidebar.button("⬅️ Retour à l'accueil"):
        st.session_state.page = "accueil"
        st.rerun()
        
    st.title("👨‍⚕️ Analyse des Médecins Prescripteurs")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx", key="med_file")

    if uploaded_file:
        df_brut = pd.read_excel(uploaded_file, header=0)
        # --- ICI TU INSÈRES TON CODE MÉDECIN (Partie 3) ---
        # (Extraction colonnes H et O, CA par médecin, line_chart, etc.)
        st.write("Le moteur d'analyse des médecins est actif.")
    else:
        st.info("Veuillez charger un fichier dans la barre latérale.")
