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

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
    """Estimation croisée Assureur ET Fournisseur pour la précision métiers"""
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    if p_hist.empty: return liq, taux_glob
    
    for h in jours_horizons:
        stats_croisees = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        stats_fourn_seul = p_hist.groupby("fournisseur")["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        
        total_h = 0.0
        for _, row in f_attente.iterrows():
            key = (row["assureur"], row["fournisseur"])
            prob = stats_croisees.get(key, stats_fourn_seul.get(row["fournisseur"], taux_glob[h]))
            total_h += row["montant"] * prob
        liq[h] = total_h
    return liq, taux_glob

# --- INTERFACE ---
st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx")

if uploaded_file:
    try:
        df_brut = pd.read_excel(uploaded_file, header=0)
        df = df_brut.copy()
        df = df.rename(columns={
            df.columns[2]: "date_facture", df.columns[8]: "assureur",
            df.columns[9]: "fournisseur", df.columns[12]: "statut", 
            df.columns[13]: "montant", df.columns[15]: "date_paiement"
        })

        # Nettoyage
        for col in ["date_facture", "date_paiement"]:
            df[col] = df[col].apply(convertir_date)
        df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        df["assureur"] = df["assureur"].fillna("Patient")
        df["fournisseur"] = df["fournisseur"].fillna("Inconnu")

        # --- FILTRES ---
        st.sidebar.header("🔍 2. Filtres")
        fournisseurs_dispo = sorted(df["fournisseur"].unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", fournisseurs_dispo, default=fournisseurs_dispo)
        df = df[df["fournisseur"].isin(sel_fournisseurs)]

        # --- OPTIONS & SIMULATION ---
        st.sidebar.header("📊 3. Analyse & Simulation")
        options_p = {"Global": None, "4 mois": 4, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect("Périodes :", list(options_p.keys()), default=["Global", "4 mois"])
        date_cible = st.sidebar.date_input("Date cible :", value=datetime.today())
        
        btn_analyser = st.sidebar.button("🚀 Lancer l'analyse complète", type="primary", use_container_width=True)
        btn_simuler = st.sidebar.button("🔮 Simuler la date cible", use_container_width=True)

        ajd = pd.Timestamp.now().normalize()
        f_att = df[df["statut"].str.contains("en attente") & ~df["statut"].str.contains("annulé")].copy()
        f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
        
        st.metric("💰 TOTAL BRUT EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
        st.markdown("---")

        # LOGIQUE : SIMULATION
        if btn_simuler:
            jours_delta = (pd.Timestamp(date_cible) - ajd).days
            if jours_delta < 0:
                st.error("Date future requise.")
            else:
                st.subheader(f"🔮 Simulation au {date_cible.strftime('%d.%m.%Y')} (+{jours_delta}j)")
                res_sim = []
                for p_nom in periods_sel:
                    val = options_p[p_nom]
                    limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, [jours_delta])
                    res_sim.append({"Période": p_nom, "Estimation (CHF)": f"{round(liq[jours_delta]):,}", "Probabilité": f"{t[jours_delta]:.1%}"})
                st.table(pd.DataFrame(res_sim))

        # LOGIQUE : ANALYSE COMPLETE
        if btn_analyser:
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités", "🕒 Délais Assureurs", "⚠️ Retards"])
            
            for p_nom in periods_sel:
                val = options_p[p_nom]
                limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                
                with tab1:
                    st.subheader(f"Période : {p_nom}")
                    horizons = 
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                    st.table(pd.DataFrame({
                        "Horizon": [f"Sous {h}j" for h in horizons],
                        "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons],
                        "Confiance": [f"{t[h]:.1%}" for h in horizons]
                    }))

                with tab2:
                    st.subheader(f"Délais par assureur ({p_nom})")
                    if not p_hist.empty:
                        stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median']).reset_index()
                        stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)"]
                        st.dataframe(stats.sort_values("Moyenne (j)", ascending=False), use_container_width=True)

                with tab3:
                    st.subheader(f"Factures > 30j ({p_nom})")
                    df_att_30 = f_att[f_att["delai_actuel"] > 30].copy()
                    if not df_att_30.empty:
                        st.warning(f"Total à relancer : {df_att_30['montant'].sum():,.2f} CHF")
                        st.dataframe(df_att_30[["date_facture", "assureur", "fournisseur", "montant", "delai_actuel"]].sort_values("delai_actuel", ascending=False))
                    else:
                        st.success("Aucun retard critique sur cette sélection.")

    except Exception as e:
        st.error(f"Erreur : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel pour démarrer.")
