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
    """Estimation précise par Assureur ET Fournisseur"""
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
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES ---
        st.sidebar.header("🔍 2. Filtres")
        # Colonne 9 pour les fournisseurs selon votre structure
        fournisseurs = df_brut.iloc[:, 9].dropna().unique().tolist()
        selection = st.sidebar.multiselect("Sélectionner les fournisseurs :", options=sorted(fournisseurs), default=fournisseurs)
        
        # --- OPTIONS STATS ---
        st.sidebar.header("📊 3. Options Délais")
        show_med = st.sidebar.checkbox("Afficher la Médiane", value=True)
        show_std = st.sidebar.checkbox("Afficher l'Écart-type", value=True)

        # --- PÉRIODES & SIMULATION ---
        st.sidebar.header("📅 4. Analyse & Simulation")
        options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect("Périodes :", list(options_p.keys()), default=["Global", "4 mois"])
        date_cible = st.sidebar.date_input("Date cible (simulation) :", value=datetime.today())
        
        btn_analyser = st.sidebar.button("🚀 Lancer l'analyse", type="primary", use_container_width=True)
        btn_simuler = st.sidebar.button("🔮 Simuler la date cible", use_container_width=True)

        # --- PRÉ-TRAITEMENT ---
        df = df_brut[df_brut.iloc[:, 9].isin(selection)].copy()
        df = df.rename(columns={
            df.columns[2]: "date_facture", df.columns[8]: "assureur",
            df.columns[9]: "fournisseur", df.columns[12]: "statut", 
            df.columns[13]: "montant", df.columns[15]: "date_paiement"
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
        st.markdown("---")

        # LOGIQUE : SIMULATION
        if btn_simuler:
            jours_delta = (pd.Timestamp(date_cible) - ajd).days
            if jours_delta < 0: st.error("Date future requise.")
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
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards"])
            
            for p_nom in periods_sel:
                val = options_p[p_nom]
                df_p = df if val is None else df[df["date_facture"] >= ajd - pd.DateOffset(months=val)]
                p_hist = df_p[df_p["date_paiement"].notna()].copy()
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
                        stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std']).reset_index()
                        stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Écart-type (j)"]
                        cols = ["Assureur", "Moyenne (j)"]
                        if show_med: cols.append("Médiane (j)")
                        if show_std: cols.append("Écart-type (j)")
                        st.dataframe(stats[cols].sort_values("Moyenne (j)", ascending=False), use_container_width=True)

                with tab3:
                    st.subheader(f"Analyse des retards > 30j ({p_nom})")
                    df_att_30 = f_att[f_att["delai_actuel"] > 30].copy()
                    df_pay_30 = p_hist[p_hist["delai"] > 30].copy()
                    plus_30 = pd.concat([df_pay_30, df_att_30])
                    
                    total_assureur = df_p.groupby("assureur").size().reset_index(name="total")
                    ret_assur = plus_30.groupby("assureur").size().reset_index(name="nb_retard")
                    
                    merged = pd.merge(ret_assur, total_assureur, on="assureur", how="right").fillna(0)
                    merged["% retard"] = (merged["nb_retard"] / merged["total"] * 100).round(0).astype(int)
                    
                    st.write(f"Total des factures en retard (Payées > 30j + En attente > 30j) : **{len(plus_30)}**")
                    st.dataframe(merged[["assureur", "nb_retard", "% retard"]].sort_values("% retard", ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"Erreur : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel.")
