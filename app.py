import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Analyseur Pro", layout="wide", page_icon="🏥")

# --- INITIALISATION DE LA NAVIGATION ---
if 'page' not in st.session_state:
    st.session_state.page = 'accueil'

# --- LOGIQUE TECHNIQUE COMMUNE ---
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
# PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == 'accueil':
    st.title("🏥 Plateforme d'Analyse de Facturation")
    st.markdown("---")
    st.write("### Choisissez le module d'analyse à lancer :")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("#### 📊 Analyse de Facturation\nAnalyse des délais, liquidités et retards assureurs.")
        if st.button("Lancer l'Analyse Facturation", type="primary", use_container_width=True):
            st.session_state.page = 'facturation'
            st.rerun()

    with col2:
        st.success("#### 🩺 Analyse Médecins\nAnalyse du chiffre d'affaires par prescripteur (Top 5-50).")
        if st.button("Lancer l'Analyse Médecins", type="primary", use_container_width=True):
            st.session_state.page = 'medecins'
            st.rerun()

# ==========================================
# PAGE : ANALYSE FACTURATION (SCRIPT 1)
# ==========================================
elif st.session_state.page == 'facturation':
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = 'accueil'
        st.rerun()
        
    st.title("📊 Analyse de Facturation")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx")

    if uploaded_file:
        df_brut = pd.read_excel(uploaded_file, header=0)
        # --- FILTRES ---
        fournisseurs = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", fournisseurs, default=fournisseurs)
        
        lois = sorted(df_brut.iloc[:, 4].dropna().unique().tolist())
        sel_lois = st.sidebar.multiselect("Types de Loi :", lois, default=lois)
        
        options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2}
        periods_sel = st.sidebar.multiselect("Périodes :", list(options_p.keys()), default=["Global", "4 mois"])

        # --- LOGIQUE SCRIPT 1 ---
        df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
        df = df.rename(columns={df.columns[2]: "date_facture", df.columns[13]: "montant", df.columns[15]: "date_paiement", df.columns[8]: "assureur", df.columns[9]: "fournisseur", df.columns[12]: "statut"})
        df["date_facture"] = df["date_facture"].apply(convertir_date)
        df["date_paiement"] = df["date_paiement"].apply(convertir_date)
        df = df[df["date_facture"].notna()].copy()
        df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        
        f_att = df[df["statut"].str.startswith("en attente")].copy()
        st.metric("💰 TOTAL EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
        
        tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
        # ... Insérer ici votre boucle 'for p_name in periods_sel' pour remplir les onglets ...

# ==========================================
# PAGE : ANALYSE MÉDECINS (SCRIPT 2)
# ==========================================
elif st.session_state.page == 'medecins':
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = 'accueil'
        st.rerun()

    st.title("🩺 Analyse des Médecins")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx")

    if uploaded_file:
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # Filtres Sidebar
        fournisseurs = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", fournisseurs, default=fournisseurs)
        
        options_p = {"Global": None, "12 mois": 12, "6 mois": 6, "3 mois": 3}
        p_sel = st.sidebar.selectbox("Période d'analyse :", list(options_p.keys()))

        # Logique Médecins
        df_m = df_brut[df_brut.iloc[:, 9].isin(sel_fournisseurs)].copy()
        df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
        df_m["dt"] = df_m.iloc[:, 2].apply(convertir_date)
        df_m["medecin"] = df_m.iloc[:, 7].astype(str).str.strip()
        
        # Filtre Date
        if options_p[p_sel]:
            limite = pd.Timestamp.now() - pd.DateOffset(months=options_p[p_sel])
            df_m = df_m[df_m["dt"] >= limite]
            
        df_m = df_m[(df_m["ca"] > 0) & (df_m["medecin"] != "nan")].copy()

        if not df_m.empty:
            top_n = st.radio("Afficher le Top :", options=[5, 10, 20, 50], index=1, horizontal=True)
            top_list = df_m.groupby("medecin")["ca"].sum().nlargest(top_n).index.tolist()
            
            choix = st.multiselect("Filtrer médecins :", sorted(df_m["medecin"].unique()), default=top_list)
            
            if choix:
                df_f = df_m[df_m["medecin"].isin(choix)].sort_values("dt")
                df_f["Mois"] = df_f["dt"].dt.to_period("M").astype(str)
                st.line_chart(df_f.groupby(["Mois", "medecin"])["ca"].sum().unstack().fillna(0))
                st.subheader("Chiffre d'affaires cumulé")
                st.table(df_f.groupby("medecin")["ca"].sum().sort_values(ascending=False).apply(lambda x: f"{x:,.2f} CHF"))
