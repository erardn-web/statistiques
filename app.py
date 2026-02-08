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

def calculer_liquidites_precision(f_attente, p_hist, jours_horizons=[10, 20, 30]):
    """Estimation précise basée sur l'historique par assureur"""
    liq = {h: 0.0 for h in jours_horizons}
    taux_glob = {h: 0.0 for h in jours_horizons}
    
    if p_hist.empty: return liq, taux_glob
    
    for h in jours_horizons:
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        # On calcule la probabilité par assureur
        taux_par_assur = p_hist.groupby("assureur")["delai"].apply(lambda x: (x <= h).mean())
        
        # On applique aux factures en attente
        f_attente_copy = f_attente.copy()
        f_attente_copy["prob"] = f_attente_copy["assureur"].map(taux_par_assur).fillna(taux_glob[h])
        liq[h] = (f_attente_copy["montant"] * f_attente_copy["prob"]).sum()
        
    return liq, taux_glob

# --- INTERFACE STREAMLIT ---

st.title("🏥 Analyseur de Facturation Suisse")
st.markdown("---")

st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        # Lecture initiale
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES MÉTIERS ---
        st.sidebar.header("🔍 2. Filtres")
        # On suppose les index de colonnes basés sur votre script initial
        fournisseurs = df_brut.iloc[:, 9].dropna().unique().tolist()
        
        selection = st.sidebar.multiselect(
            "Sélectionner les fournisseurs :", 
            options=sorted(fournisseurs), 
            default=fournisseurs
        )
        
        # --- OPTIONS STATISTIQUES ---
        st.sidebar.header("📊 3. Options Stats")
        show_med = st.sidebar.checkbox("Afficher la Médiane")
        show_std = st.sidebar.checkbox("Afficher l'Écart-type")
        
        # --- PÉRIODES ---
        st.sidebar.header("📅 4. Périodes d'analyse")
        options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect(
            "Comparer les périodes :", 
            list(options_p.keys()), 
            default=["Global", "4 mois"]
        )

        # --- SIMULATION DATE FUTURE ---
        st.sidebar.header("🎯 5. Simulation")
        date_cible = st.sidebar.date_input("Prédire pour le :", value=datetime.today())
        btn_simuler = st.sidebar.button("🔮 Simuler à cette date", use_container_width=True)
        
        # --- BOUTON PRINCIPAL ---
        btn_analyser = st.sidebar.button("🚀 Lancer l'analyse complète", type="primary", use_container_width=True)

        # Pré-traitement des données (commun aux deux boutons)
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
        df["statut"] = df["statut"].astype(str).str.lower().str.strip()
        df["assureur"] = df["assureur"].fillna("Patient")
        
        ajd = pd.Timestamp(datetime.today().date())
        f_att = df[df["statut"].str.contains("en attente") & ~df["statut"].str.contains("annulé")].copy()
        f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days

        # --- LOGIQUE AFFICHAGE : SIMULATION ---
        if btn_simuler:
            jours_delta = (pd.Timestamp(date_cible) - ajd).days
            if jours_delta < 0:
                st.error("Veuillez choisir une date dans le futur.")
            else:
                p_hist_full = df[df["date_paiement"].notna()].copy()
                p_hist_full["delai"] = (p_hist_full["date_paiement"] - p_hist_full["date_facture"]).dt.days
                
                liq_sim, taux_sim = calculer_liquidites_precision(f_att, p_hist_full, [jours_delta])
                
                st.balloons()
                st.subheader(f"🎯 Résultat de la simulation au {date_cible.strftime('%d.%m.%Y')}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Horizon", f"+ {jours_delta} jours")
                c2.metric("Estimation Encaissement", f"{round(liq_sim[jours_delta]):,} CHF")
                c3.metric("Probabilité globale", f"{round(taux_sim[jours_delta]*100)}%")
                st.info(f"Cette simulation projette l'encaissement de vos **{len(f_att)}** factures actuellement en attente.")

        # --- LOGIQUE AFFICHAGE : ANALYSE COMPLETE ---
        if btn_analyser:
            tab1, tab2, tab3 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards"])

            for p_name in periods_sel:
                val = options_p[p_name]
                df_p = df if val is None else df[df["date_facture"] >= ajd - pd.DateOffset(months=val)]
                
                p_hist = df_p[df_p["date_paiement"].notna()].copy()
                p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                p_hist = p_hist[p_hist["delai"] >= 0]
                
                liq, t = calculer_liquidites_precision(f_att, p_hist)
                
                with tab1:
                    st.subheader(f"Période de référence : {p_name}")
                    data_liq = {
                        "Horizon": ["10 jours", "20 jours", "30 jours"],
                        "Estimation (CHF)": [f"{round(liq[10]):,}", f"{round(liq[20]):,}", f"{round(liq[30]):,}"],
                        "Probabilité": [f"{round(t[10]*100)}%", f"{round(t[20]*100)}%", f"{round(t[30]*100)}%"]
                    }
                    st.table(pd.DataFrame(data_liq))

                with tab2:
                    st.subheader(f"Délais par assureur ({p_name})")
                    if not p_hist.empty:
                        stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std']).reset_index()
                        stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Écart-type (j)"]
                        
                        cols_to_show = ["Assureur", "Moyenne (j)"]
                        if show_med: cols_to_show.append("Médiane (j)")
                        if show_std: cols_to_show.append("Écart-type (j)")
                        
                        st.dataframe(stats[cols_to_show].sort_values("Moyenne (j)", ascending=False), use_container_width=True)

                with tab3:
                    st.subheader(f"Analyse des retards > 30j ({p_name})")
                    df_att_30 = f_att[f_att["delai_actuel"] > 30]
                    st.warning(f"Total des factures en attente depuis > 30j : **{len(df_att_30)}**")
                    if not df_att_30.empty:
                        st.dataframe(df_att_30[["date_facture", "assureur", "montant", "delai_actuel"]].sort_values("delai_actuel", ascending=False))

    except Exception as e:
        st.error(f"Erreur lors de l'analyse : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel pour commencer.")
