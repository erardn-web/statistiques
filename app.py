import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- LOGIQUE DE CALCUL PAR FOURNISSEUR ---

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
    """
    Calcule l'estimation en croisant l'Assureur ET le Fournisseur.
    """
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    
    if p_hist.empty: return liq, taux_glob
    
    for h in jours_horizons:
        # 1. Taux par couple (Assureur, Fournisseur)
        stats_croisees = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        
        # 2. Taux par Fournisseur uniquement
        stats_fournisseur_seul = p_hist.groupby("fournisseur")["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        
        # 3. Taux de secours global
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        
        total_h = 0.0
        for _, row in f_attente.iterrows():
            key = (row["assureur"], row["fournisseur"])
            # Cascade : Couple -> Fournisseur -> Global
            prob = stats_croisees.get(key, stats_fournisseur_seul.get(row["fournisseur"], taux_glob[h]))
            total_h += row["montant"] * prob
            
        liq[h] = total_h
        
    return liq, taux_glob

# --- INTERFACE ---
st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx")

if uploaded_file:
    try:
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- MAPPING ---
        df = df_brut.copy()
        df = df.rename(columns={
            df.columns[2]: "date_facture", 
            df.columns[8]: "assureur",
            df.columns[9]: "fournisseur", 
            df.columns[12]: "statut", 
            df.columns[13]: "montant", 
            df.columns[15]: "date_paiement"
        })

        # Nettoyage des données
        for col in ["date_facture", "date_paiement"]:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
        
        df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        df["assureur"] = df["assureur"].fillna("Patient")
        df["fournisseur"] = df["fournisseur"].fillna("Inconnu")

        # --- FILTRES SIDEBAR ---
        st.sidebar.header("🔍 2. Sélection Fournisseurs")
        fournisseurs_dispo = sorted(df["fournisseur"].unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", fournisseurs_dispo, default=fournisseurs_dispo)
        
        df = df[df["fournisseur"].isin(sel_fournisseurs)]

        # Périodes
        st.sidebar.header("📅 3. Analyse & Simulation")
        options_p = {"Global": None, "4 mois": 4, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect("Périodes de référence :", list(options_p.keys()), default=["Global", "4 mois"])
        
        date_cible = st.sidebar.date_input("Date cible (simulation) :", value=datetime.today())
        
        btn_analyser = st.sidebar.button("🚀 Analyse Complète", type="primary", use_container_width=True)
        btn_simuler = st.sidebar.button("🔮 Simuler la date cible", use_container_width=True)

        # Identification Attente
        ajd = pd.Timestamp.now().normalize()
        f_att = df[df["statut"].str.contains("en attente") & ~df["statut"].str.contains("annulé")].copy()
        
        # --- AFFICHAGE HEADER ---
        total_attente = f_att['montant'].sum()
        st.metric("💰 TOTAL BRUT EN ATTENTE", f"{total_attente:,.2f} CHF")
        st.markdown("---")

        # LOGIQUE : SIMULATION
        if btn_simuler:
            jours_delta = (pd.Timestamp(date_cible) - ajd).days
            if jours_delta < 0:
                st.error("Choisissez une date dans le futur.")
            else:
                st.subheader(f"🔮 Simulation au {date_cible.strftime('%d.%m.%Y')} (+{jours_delta}j)")
                res_sim = []
                for p_nom in periods_sel:
                    val = options_p[p_nom]
                    limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    
                    # Appel correct avec jours_delta
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, [jours_delta])
                    res_sim.append({
                        "Référence": p_nom, 
                        "Estimation (CHF)": f"{round(liq[jours_delta]):,}", 
                        "Probabilité": f"{t[jours_delta]:.1%}"
                    })
                
                st.table(pd.DataFrame(res_sim))

        # LOGIQUE : ANALYSE
        if btn_analyser:
            tab1, tab2 = st.tabs(["💰 Cash-Flow Estimé", "🕒 Performance par Fournisseur"])
            
            horizons_std = [10, 20, 30]
            
            with tab1:
                for p_nom in periods_sel:
                    val = options_p[p_nom]
                    limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    
                    # FIX ICI : Ajout de horizons_std comme argument
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons_std)
                    
                    st.write(f"**Période : {p_name if 'p_name' in locals() else p_nom}**")
                    data = {
                        "Horizon": [f"Sous {h} jours" for h in horizons_std],
                        "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons_std],
                        "Probabilité globale": [f"{t[h]:.1%}" for h in horizons_std]
                    }
                    st.table(pd.DataFrame(data))
            
            with tab2:
                st.subheader("Délai de paiement moyen par fournisseur")
                p_hist_all = df[df["date_paiement"].notna()].copy()
                p_hist_all["delai"] = (p_hist_all["date_paiement"] - p_hist_all["date_facture"]).dt.days
                if not p_hist_all.empty:
                    stats_f = p_hist_all.groupby("fournisseur")["delai"].mean().sort_values()
                    st.bar_chart(stats_f)
                    st.dataframe(stats_f.rename("Délai Moyen (jours)"))

    except Exception as e:
        st.error(f"Erreur d'analyse : {e}")
else:
    st.info("👋 Chargez votre fichier Excel pour démarrer.")
