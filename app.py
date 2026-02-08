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
        # Probabilités par couple Assureur/Fournisseur
        stats_croisees = p_hist.groupby(["assureur", "fournisseur"])["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        # Probabilités par Fournisseur seul (secours 1)
        stats_fourn = p_hist.groupby("fournisseur")["delai"].apply(lambda x: (x <= h).mean()).to_dict()
        # Probabilité globale (secours 2)
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        
        total_h = 0.0
        for _, row in f_attente.iterrows():
            key = (row["assureur"], row["fournisseur"])
            prob = stats_croisees.get(key, stats_fourn.get(row["fournisseur"], taux_glob[h]))
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
        # Mapping strict selon vos index habituels
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

        # --- OPTIONS STATS ---
        st.sidebar.header("📊 3. Options d'affichage")
        show_med = st.sidebar.checkbox("Afficher la Médiane", value=True)
        show_std = st.sidebar.checkbox("Afficher l'Écart-type", value=True)

        # --- PÉRIODES & SIMULATION ---
        st.sidebar.header("📅 4. Analyse & Simulation")
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
                st.error("Veuillez choisir une date dans le futur.")
            else:
                st.subheader(f"🔮 Résultats de la simulation au {date_cible.strftime('%d.%m.%Y')} (+{jours_delta}j)")
                res_sim = []
                for p_nom in periods_sel:
                    val = options_p[p_nom]
                    limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, [jours_delta])
                    res_sim.append({
                        "Référence Historique": p_nom, 
                        "Estimation (CHF)": f"{round(liq[jours_delta]):,}", 
                        "Probabilité globale": f"{t[jours_delta]:.1%}"
                    })
                st.table(pd.DataFrame(res_sim))

        # LOGIQUE : ANALYSE COMPLETE
        if btn_analyser:
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités", "🕒 Délais Assureurs", "⚠️ Analyse Retards"])
            
            for p_nom in periods_sel:
                val = options_p[p_nom]
                limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                p_hist = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                
                with tab1:
                    st.subheader(f"Période : {p_nom}")
                    horizons = [10, 20, 30]
                    liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                    st.table(pd.DataFrame({
                        "Horizon": [f"Sous {h} jours" for h in horizons],
                        "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons],
                        "Confiance (Taux)": [f"{t[h]:.1%}" for h in horizons]
                    }))

                with tab2:
                    st.subheader(f"Délais de paiement ({p_nom})")
                    if not p_hist.empty:
                        stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std']).reset_index()
                        stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Écart-type (j)"]
                        
                        cols_view = ["Assureur", "Moyenne (j)"]
                        if show_med: cols_view.append("Médiane (j)")
                        if show_std: cols_view.append("Écart-type (j)")
                        
                        st.dataframe(stats[cols_view].sort_values("Moyenne (j)", ascending=False), use_container_width=True)
                    else:
                        st.warning(f"Aucun historique pour la période {p_nom}")

                with tab3:
                    st.subheader(f"Factures en retard > 30j ({p_nom})")
                    df_att_30 = f_att[f_att["delai_actuel"] > 30].copy()
                    
                    if not df_att_30.empty:
                        # Analyse par assureur pour les retards
                        total_assur = df[df["date_facture"] >= limit].groupby("assureur").size().reset_index(name="Total")
                        ret_assur = df_att_30.groupby("assureur").size().reset_index(name="En Retard")
                        merged = pd.merge(ret_assur, total_assur, on="assureur", how="right").fillna(0)
                        merged["% de Retard"] = (merged["En Retard"] / merged["Total"] * 100).round(1)
                        
                        st.write(f"Nombre total de factures en retard : **{len(df_att_30)}**")
                        st.dataframe(merged.sort_values("% de Retard", ascending=False), use_container_width=True)
                        st.write("**Détail des factures critiques :**")
                        st.dataframe(df_att_30[["date_facture", "assureur", "fournisseur", "montant", "delai_actuel"]].sort_values("delai_actuel", ascending=False))
                    else:
                        st.success("Félicitations, aucune facture n'a plus de 30 jours de retard sur cette sélection.")

    except Exception as e:
        st.error(f"Erreur d'analyse : {e}")
else:
    st.info("👋 Veuillez charger votre export Excel pour démarrer l'analyse.")
