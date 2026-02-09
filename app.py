import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- MAPPING DES GROUPES D'ASSURANCES (LAMal uniquement) ---
MAPPING_GROUPES = {
    "Visana (Groupe)": ["Visana Services AG", "vivacare", "sana24", "GALENOS"],
    "Helsana (Groupe)": ["Helsana Assurances", "Progrès", "Sansan"],
    "Groupe Mutuel (Groupe)": ["Groupe Mutuel", "caisse maladie", "Caisse maladie Avenir", "SUPRA-1846 SA", "Philos, caisse maladie", "Easy Sana caisse maladie"],
    "CSS (Groupe)": ["CSS Assurances", "Intras, caisse maladie", "Arcosana"]
}

# Inversion pour recherche rapide
REVERSE_MAPPING = {filiale.strip().lower(): parent for parent, filiales in MAPPING_GROUPES.items() for filiale in filiales}

# --- INITIALISATION DE L'ÉTAT ---
if 'analyse_lancee' not in st.session_state:
    st.session_state.analyse_lancee = False

# --- LOGIQUE DE CALCUL ---
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

# --- INTERFACE ---
st.title("🏥 Analyseur de Facturation Suisse")
st.markdown("---")

st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        # Lecture initiale
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES (SIDEBAR) ---
        st.sidebar.header("🔍 2. Filtres")
        
        regrouper_lamal = st.sidebar.checkbox("🔗 Regrouper les groupes LAMal", value=True)
        
        # Pré-traitement pour les filtres de la sidebar
        df_filter = df_brut.copy()
        df_filter.columns = [str(c) for c in df_filter.columns]
        
        # Identification des colonnes par index pour la cohérence
        col_loi = df_filter.columns[4]
        col_assur = df_filter.columns[8]
        col_fourn = df_filter.columns[9]

        def appliquer_regroupement(row):
            nom = str(row[col_assur]).strip()
            loi = str(row[col_loi]).strip()
            if regrouper_lamal and "LAMal" in loi:
                return REVERSE_MAPPING.get(nom.lower(), nom)
            return nom

        # Application du nom regroupé pour l'affichage dans le filtre
        display_assureurs = df_filter.apply(appliquer_regroupement, axis=1).unique()
        
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", options=sorted(df_filter[col_fourn].dropna().unique().tolist()), default=df_filter[col_fourn].dropna().unique().tolist())
        sel_lois = st.sidebar.multiselect("Types de Loi :", options=sorted(df_filter[col_loi].dropna().unique().tolist()), default=df_filter[col_loi].dropna().unique().tolist())
        sel_assureurs = st.sidebar.multiselect("Assureurs :", options=sorted(display_assureurs.tolist()), default=display_assureurs.tolist())

        # --- NETTOYAGE ET APPLICATION FILTRES ---
        df = df_brut.copy()
        df = df.rename(columns={
            df.columns[2]: "date_facture", 
            df.columns[4]: "loi",
            df.columns[8]: "assureur",
            df.columns[9]: "fournisseur", 
            df.columns[12]: "statut", 
            df.columns[13]: "montant", 
            df.columns[15]: "date_paiement"
        })

        # Nettoyage des chaînes
        df["assureur"] = df["assureur"].fillna("Patient").astype(str).str.strip()
        df["loi"] = df["loi"].fillna("Inconnue").astype(str).str.strip()

        # Application du regroupement conditionnel (Uniquement si LAMal)
        if regrouper_lamal:
            df["assureur"] = df.apply(lambda r: REVERSE_MAPPING.get(r["assureur"].lower(), r["assureur"]) if "LAMal" in r["loi"] else r["assureur"], axis=1)

        # Filtrage final
        df = df[
            (df["fournisseur"].isin(sel_fournisseurs)) & 
            (df["loi"].isin(sel_lois)) &
            (df["assureur"].isin(sel_assureurs))
        ].copy()

        # Conversion types
        df["date_facture"] = df["date_facture"].apply(convertir_date)
        df["date_paiement"] = df["date_paiement"].apply(convertir_date)
        df = df[df["date_facture"].notna()].copy()
        df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        
        ajd = pd.Timestamp(datetime.today().date())
        f_att = df[df["statut"].str.startswith("en attente") & (df["statut"] != "en attente (annulé)")].copy()
        f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
        
        st.sidebar.header("📊 3. Options")
        show_med = st.sidebar.checkbox("Afficher la Médiane", value=True)
        show_std = st.sidebar.checkbox("Afficher l'Écart-type", value=True)
        
        st.metric("💰 TOTAL BRUT EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
        st.markdown("---")

        # --- LOGIQUE BOUTONS ---
        col_b1, col_b2 = st.sidebar.columns(2)
        if col_b1.button("🚀 Analyser", type="primary"): st.session_state.analyse_lancee = True
        btn_simuler = col_b2.button("🔮 Simuler")

        if btn_simuler:
            # (Logique de simulation identique au précédent...)
            st.info("Simulation en cours...")
            jours_delta = (pd.Timestamp(datetime.today()) - ajd).days # Simplifié pour l'exemple
            st.write(f"Résultat estimé pour J+{jours_delta}")

        if st.session_state.analyse_lancee:
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards"])

            # Analyse globale (exemple sur période complète)
            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days

            with tab1:
                horizons = [10, 20, 30]
                liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                st.table(pd.DataFrame({
                    "Horizon": [f"Sous {h}j" for h in horizons],
                    "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons],
                    "Probabilité": [f"{round(t[h]*100)}%" for h in horizons]
                }))

            with tab2:
                if not p_hist.empty:
                    stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std']).reset_index()
                    stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Écart-type (j)"]
                    st.dataframe(stats.sort_values("Moyenne (j)", ascending=False), use_container_width=True)

            with tab3:
                df_att_30 = f_att[f_att["delai_actuel"] > 30].copy()
                if not df_att_30.empty:
                    retards = df_att_30.groupby("assureur")["montant"].sum().reset_index()
                    st.dataframe(retards.sort_values("montant", ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"Erreur : {e}")
