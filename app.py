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
        
        st.sidebar.header("📅 3. Lancer l'Analyse")
        if st.sidebar.button("🚀 Analyse Facturation", type="primary", use_container_width=True):
            st.session_state.analyse_lancee = True
            st.session_state.calcul_medecin_lance = False
            
        if st.sidebar.button("🩺 Analyse Médecins", use_container_width=True):
            st.session_state.calcul_medecin_lance = True
            st.session_state.analyse_lancee = False

        # --- BLOC 1 : ANALYSE FACTURATION (STRICTEMENT IDENTIQUE) ---
        if st.session_state.analyse_lancee and not st.session_state.calcul_medecin_lance:
            st.title("🏥 Analyse de Facturation")
            
            df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df = df.rename(columns={
                df.columns[2]: "date_facture", df.columns[4]: "loi",
                df.columns[8]: "assureur", df.columns[9]: "fournisseur", 
                df.columns[12]: "statut", df.columns[13]: "montant", df.columns[15]: "date_paiement"
            })
            df["date_facture"] = df["date_facture"].apply(convertir_date)
            df["date_paiement"] = df["date_paiement"].apply(convertir_date)
            df = df[df["date_facture"].notna()].copy()
            df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
            df["statut"] = df["statut"].astype(str).str.lower().str.strip()
            df["assureur"] = df["assureur"].fillna("Patient")
            
            ajd = pd.Timestamp(datetime.today().date())
            f_att = df[df["statut"].str.startswith("en attente") & (df["statut"] != "en attente (annulé)")].copy()
            f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
            
            st.metric("💰 TOTAL BRUT EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
            
            tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
            # Ici insérer votre boucle 'for p_name in periods_sel' habituelle pour les onglets
            # (Simplifié ici pour la structure, gardez votre code interne tab1-tab4)

        # --- BLOC 2 : ANALYSE MÉDECINS (TOTALEMENT SÉPARÉ) ---
        if st.session_state.calcul_medecin_lance:
            st.title("👨‍⚕️ Analyse des Prescripteurs")
            
            df_m = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df_m["medecin"] = df_m.iloc[:, 7].astype(str).str.strip()
            df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
            df_m["dt"] = df_m.iloc[:, 2].apply(convertir_date)
            
            df_m = df_m[(df_m["ca"] > 0) & (df_m["dt"].notna()) & (df_m["medecin"] != "nan")].copy()
            
            if not df_m.empty:
                c1, c2 = st.columns([1, 3])
                with c1:
                    top_n_choice = st.radio("Top à afficher :", options=[5, 10, 20, 50], index=1, horizontal=True)
                
                top_meds = df_m.groupby("medecin")["ca"].sum().nlargest(top_n_choice).index.tolist()
                
                with c2:
                    choix_final = st.multiselect("Filtrer manuellement :", options=sorted(df_m["medecin"].unique()), default=top_meds)
                
                if choix_final:
                    df_res = df_m[df_m["medecin"].isin(choix_final)].sort_values("dt")
                    df_res["Mois"] = df_res["dt"].dt.to_period("M").astype(str)
                    
                    st.line_chart(df_res.groupby(["Mois", "medecin"])["ca"].sum().unstack().fillna(0))
                    
                    st.subheader(f"Classement Top {len(choix_final)} (CHF)")
                    st.table(df_res.groupby("medecin")["ca"].sum().sort_values(ascending=False).apply(lambda x: f"{x:,.2f} CHF"))
            else:
                st.warning("Aucune donnée disponible pour ces filtres.")

    except Exception as e:
        st.error(f"Erreur : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel (.xlsx).")
