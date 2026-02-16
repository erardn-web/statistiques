import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- INITIALISATION DE L'ÉTAT ---
if 'analyse_lancee' not in st.session_state:
    st.session_state.analyse_lancee = False
if 'calcul_medecin_lance' not in st.session_state:
    st.session_state.calcul_medecin_lance = False

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

# --- INTERFACE SIDEBAR ---
st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        st.sidebar.header("🔍 2. Filtres Globaux")
        fournisseurs = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", options=fournisseurs, default=fournisseurs)
        
        lois = sorted(df_brut.iloc[:, 4].dropna().unique().tolist())
        sel_lois = st.sidebar.multiselect("Types de Loi :", options=lois, default=lois)
        
        st.sidebar.header("📅 3. Période d'analyse")
        options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect("Périodes à analyser :", list(options_p.keys()), default=["Global", "4 mois"])
        
        st.sidebar.header("🚀 4. Lancer")
        c_b1, c_b2 = st.sidebar.columns(2)
        if c_b1.button("📊 Facturation", type="primary", use_container_width=True):
            st.session_state.analyse_lancee = True
            st.session_state.calcul_medecin_lance = False
        if c_b2.button("🩺 Médecins", use_container_width=True):
            st.session_state.calcul_medecin_lance = True
            st.session_state.analyse_lancee = False

        # --- BLOC 1 : ANALYSE FACTURATION ---
        if st.session_state.analyse_lancee:
            st.title("🏥 Analyse de Facturation")
            # [Ici votre code initial complet avec onglets tab1-tab4]
            # ... (Logique de nettoyage et boucles périodes) ...
            st.info("Analyse de facturation active selon les filtres sidebar.")

        # --- BLOC 2 : ANALYSE MÉDECINS (SÉPARÉ) ---
        if st.session_state.calcul_medecin_lance:
            st.title("👨‍⚕️ Analyse des Médecins")
            
            # Filtres de base
            df_m = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df_m["dt"] = df_m.iloc[:, 2].apply(convertir_date)
            df_m["medecin"] = df_m.iloc[:, 7].astype(str).str.strip()
            df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
            
            # Application du filtre de date selon la sidebar
            ajd = pd.Timestamp(datetime.today().date())
            # On prend la période la plus large sélectionnée dans la sidebar pour ce graphique
            p_val = [options_p[p] for p in periods_sel if options_p[p] is not None]
            if p_val and "Global" not in periods_sel:
                limit = ajd - pd.DateOffset(months=max(p_val))
                df_m = df_m[df_m["dt"] >= limit]
            
            df_m = df_m[(df_m["ca"] > 0) & (df_m["dt"].notna()) & (df_m["medecin"] != "nan")].copy()
            
            if not df_m.empty:
                col1, col2 = st.columns([1, 3])
                with col1:
                    top_n = st.radio("Top à afficher :", options=[5, 10, 20, 50], index=1)
                
                top_names = df_m.groupby("medecin")["ca"].sum().nlargest(top_n).index.tolist()
                
                with col2:
                    choix = st.multiselect("Sélection personnalisée :", options=sorted(df_m["medecin"].unique()), default=top_names)
                
                if choix:
                    df_plot = df_m[df_m["medecin"].isin(choix)].sort_values("dt")
                    df_plot["Mois"] = df_plot["dt"].dt.to_period("M").astype(str)
                    
                    st.line_chart(df_plot.groupby(["Mois", "medecin"])["ca"].sum().unstack().fillna(0))
                    st.subheader("Détail du Chiffre d'Affaires")
                    st.table(df_plot.groupby("medecin")["ca"].sum().sort_values(ascending=False).apply(lambda x: f"{x:,.2f} CHF"))
            else:
                st.warning("Aucune donnée pour la période sélectionnée.")

    except Exception as e:
        st.error(f"Erreur : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel.")
