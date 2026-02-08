import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- LOGIQUE DE CALCUL ---
def convertir_date(val):
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    if isinstance(val, pd.Timestamp): return val
    try:
        return pd.to_datetime(str(val).strip(), format="%d.%m.%Y", errors="coerce")
    except:
        return pd.NaT

def calculer_liquidites_precision(f_attente, p_hist, jours_horizons):
    """Calcule l'estimation pour un ou plusieurs horizons donnés"""
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    
    if p_hist.empty: return liq, taux_glob
    
    for h in jours_horizons:
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        taux_par_assur = p_hist.groupby("assureur")["delai"].apply(lambda x: (x <= h).mean())
        
        f_temp = f_attente.copy()
        f_temp["prob"] = f_temp["assureur"].map(taux_par_assur).fillna(taux_glob[h])
        liq[h] = (f_temp["montant"] * f_temp["prob"]).sum()
        
    return liq, taux_glob

# --- INTERFACE ---
st.title("🏥 Analyseur de Facturation Suisse")
st.markdown("---")

st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES ---
        st.sidebar.header("🔍 2. Filtres")
        fournisseurs = df_brut.iloc[:, 9].dropna().unique().tolist()
        selection = st.sidebar.multiselect("Fournisseurs :", options=sorted(fournisseurs), default=fournisseurs)
        
        # --- PÉRIODES ---
        st.sidebar.header("📅 3. Références Temporelles")
        options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect("Périodes à comparer :", list(options_p.keys()), default=["Global", "4 mois", "2 mois"])

        # --- SIMULATION ---
        st.sidebar.header("🎯 4. Simulation")
        date_cible = st.sidebar.date_input("Prédire pour le :", value=datetime.today())
        
        # --- BOUTONS ---
        st.sidebar.markdown("---")
        btn_analyser = st.sidebar.button("🚀 Analyse Complète (10-20-30j)", type="primary", use_container_width=True)
        btn_simuler = st.sidebar.button("🔮 Simuler la date cible", use_container_width=True)

        # --- PRÉ-TRAITEMENT ---
        df = df_brut[df_brut.iloc[:, 9].isin(selection)].copy()
        df = df.rename(columns={
            df.columns[2]: "date_facture", df.columns[8]: "assureur",
            df.columns[12]: "statut", df.columns[13]: "montant", 
            df.columns[15]: "date_paiement"
        })
        
        df["date_facture"] = df["date_facture"].apply(convertir_date)
        df["date_paiement"] = df["date_paiement"].apply(convertir_date)
        df = df[df["date_facture"].notna()].copy()
        df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
        
        # CORRECTION ICI : Ajout de .str avant .lower()
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        df["assureur"] = df["assureur"].fillna("Patient")
        
        ajd = pd.Timestamp(datetime.today().date())
        
        # Identification des factures en attente
        f_att = df[df["statut"].str.contains("en attente") & ~df["statut"].str.contains("annulé")].copy()
        
        total_brut = f_att["montant"].sum()
        st.metric(label="💰 TOTAL BRUT EN ATTENTE", value=f"{total_brut:,.2f} CHF")

        # --- LOGIQUE : SIMULATION MULTI-PÉRIODES ---
        if btn_simuler:
            jours_delta = (pd.Timestamp(date_cible) - ajd).days
            if jours_delta < 0:
                st.error("La date cible doit être dans le futur.")
            else:
                st.subheader(f"🔮 Simulation d'encaissement au {date_cible.strftime('%d.%m.%Y')} (+{jours_delta} jours)")
                
                sim_results = []
                for p_name in periods_sel:
                    val = options_p[p_name]
                    limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    
                    liq, t = calculer_liquidites_precision(f_att, p_hist, [jours_delta])
                    sim_results.append({
                        "Référence Historique": p_name,
                        "Estimation (CHF)": f"{round(liq[jours_delta]):,}",
                        "Probabilité de paiement": f"{round(t[jours_delta]*100)}%"
                    })
                
                st.table(pd.DataFrame(sim_results))

        # --- LOGIQUE : ANALYSE ---
        if btn_analyser:
            tab1, tab2 = st.tabs(["💰 Liquidités Estimées", "🕒 Délais Assureurs"])
            with tab1:
                for p_name in periods_sel:
                    val = options_p[p_name]
                    limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    
                    liq, t = calculer_liquidites_precision(f_att, p_hist, [10, 20, 30])
                    
                    st.write(f"**Période : {p_name}**")
                    data = {
                        "Horizon": ["10 jours", "20 jours", "30 jours"],
                        "Estimation (CHF)": [f"{round(liq[10]):,}", f"{round(liq[20]):,}", f"{round(liq[30]):,}"],
                        "Confiance": [f"{round(t[10]*100)}%", f"{round(t[20]*100)}%", f"{round(t[30]*100)}%"]
                    }
                    st.table(pd.DataFrame(data))

    except Exception as e:
        st.error(f"Erreur : {e}")
else:
    st.info("👋 Chargez votre export Excel pour démarrer.")
