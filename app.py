import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- MAPPING DES GROUPES D'ASSURANCES (Ciblés LAMal) ---
MAPPING_GROUPES = {
    "Visana (Groupe LAMal)": ["Visana Services AG", "vivacare", "sana24", "GALENOS"],
    "Helsana (Groupe LAMal)": ["Helsana Assurances", "Progrès", "Sansan"],
    "Groupe Mutuel (Groupe LAMal)": ["Groupe Mutuel", "caisse maladie", "Caisse maladie Avenir", "SUPRA-1846 SA", "Philos, caisse maladie", "Easy Sana caisse maladie"],
    "CSS (Groupe LAMal)": ["CSS Assurances", "Intras, caisse maladie", "Arcosana"]
}

# Inversion pour recherche rapide (minuscules pour éviter les erreurs de saisie)
REVERSE_MAPPING = {filiale.lower().strip(): parent for parent, filiales in MAPPING_GROUPES.items() for filiale in filiales}

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
        # Lecture brute pour extraire les options de filtres
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES (SIDEBAR) ---
        st.sidebar.header("🔍 2. Configuration & Filtres")
        
        # CASE À COCHER : Activation du regroupement
        regrouper = st.sidebar.checkbox("🔗 Regrouper les groupes LAMal", value=True, help="Fusionne les filiales (ex: Philos, Avenir) sous leur groupe parent uniquement pour la loi LAMal.")
        
        # Extraction des noms pour les filtres (en tenant compte du regroupement ou non)
        col_loi_idx, col_assur_idx, col_fourn_idx = 4, 8, 9
        
        def obtenir_nom_traite(row):
            nom = str(row.iloc[col_assur_idx]).strip()
            loi = str(row.iloc[col_loi_idx]).strip()
            if regrouper and "LAMal" in loi:
                return REVERSE_MAPPING.get(nom.lower(), nom)
            return nom

        # Application du traitement sur une version temporaire pour les filtres
        df_temp_filtres = df_brut.copy()
        df_temp_filtres['assureur_traite'] = df_temp_filtres.apply(obtenir_nom_traite, axis=1)

        fournisseurs = sorted(df_temp_filtres.iloc[:, col_fourn_idx].dropna().unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", options=fournisseurs, default=fournisseurs)
        
        lois = sorted(df_temp_filtres.iloc[:, col_loi_idx].dropna().unique().tolist())
        sel_lois = st.sidebar.multiselect("Types de Loi :", options=lois, default=lois)
        
        assureurs = sorted(df_temp_filtres['assureur_traite'].unique().tolist())
        sel_assureurs = st.sidebar.multiselect("Assureurs :", options=assureurs, default=assureurs)

        # --- NETTOYAGE ET APPLICATION DES DONNÉES ---
        df = df_brut.rename(columns={
            df_brut.columns[2]: "date_facture", 
            df_brut.columns[4]: "loi",
            df_brut.columns[8]: "assureur",
            df_brut.columns[9]: "fournisseur", 
            df_brut.columns[12]: "statut", 
            df_brut.columns[13]: "montant", 
            df_brut.columns[15]: "date_paiement"
        }).copy()

        # Nettoyage initial
        df["assureur"] = df["assureur"].fillna("Patient").astype(str).str.strip()
        df["loi"] = df["loi"].fillna("Inconnue").astype(str).str.strip()

        # Application définitive du regroupement selon le choix
        if regrouper:
            df["assureur"] = df.apply(lambda r: REVERSE_MAPPING.get(r["assureur"].lower(), r["assureur"]) if "LAMal" in r["loi"] else r["assureur"], axis=1)

        # Filtrage basé sur les sélections sidebar
        df = df[
            (df["fournisseur"].isin(sel_fournisseurs)) & 
            (df["loi"].isin(sel_lois)) &
            (df["assureur"].isin(sel_assureurs))
        ].copy()

        # Conversion des formats
        df["date_facture"] = df["date_facture"].apply(convertir_date)
        df["date_paiement"] = df["date_paiement"].apply(convertir_date)
        df = df[df["date_facture"].notna()].copy()
        df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        
        ajd = pd.Timestamp(datetime.today().date())
        f_att = df[df["statut"].str.startswith("en attente") & (df["statut"] != "en attente (annulé)")].copy()
        f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
        
        st.metric("💰 TOTAL BRUT EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
        st.markdown("---")

        # --- ACTIONS ---
        st.sidebar.header("🚀 3. Actions")
        col_b1, col_b2 = st.sidebar.columns(2)
        if col_b1.button("Lancer l'Analyse", type="primary"):
            st.session_state.analyse_lancee = True
        
        if st.session_state.analyse_lancee:
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards"])

            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days

            with tab1:
                horizons = [10, 20, 30]
                liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                st.subheader("Prévisions de trésorerie")
                st.table(pd.DataFrame({
                    "Horizon": [f"Sous {h}j" for h in horizons],
                    "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons],
                    "Confiance": [f"{round(t[h]*100)}%" for h in horizons]
                }))

            with tab2:
                st.subheader("Performance de paiement par Assureur")
                if not p_hist.empty:
                    stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'count']).reset_index()
                    stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Volume"]
                    st.dataframe(stats.sort_values("Moyenne (j)", ascending=False), use_container_width=True)

            with tab3:
                st.subheader("Analyse des retards actifs (> 30 jours)")
                df_retard = f_att[f_att["delai_actuel"] > 30].copy()
                if not df_retard.empty:
                    agg_retard = df_retard.groupby("assureur")["montant"].sum().reset_index()
                    st.dataframe(agg_retard.sort_values("montant", ascending=False), use_container_width=True)
                else:
                    st.success("Aucun retard de plus de 30 jours détecté.")

    except Exception as e:
        st.error(f"Erreur lors du traitement : {e}")
