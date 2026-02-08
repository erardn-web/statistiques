import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide")

# --- LOGIQUE DE CALCUL ---

def convertir_date(val):
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    if isinstance(val, pd.Timestamp): return val
    try:
        return pd.to_datetime(str(val).strip(), format="%d.%m.%Y", errors="coerce")
    except:
        return pd.NaT

def calculer_liquidites_precision(f_attente, p_hist):
    """Estimation précise assureur par assureur"""
    liq = {10: 0.0, 20: 0.0, 30: 0.0}
    taux_glob = {10: 0.0, 20: 0.0, 30: 0.0}
    if p_hist.empty: return liq, taux_glob
    
    for h in [10, 20, 30]:
        taux_glob[h] = (p_hist["delai"] <= h).mean()
        for _, f in f_attente.iterrows():
            hist_assur = p_hist[p_hist["assureur"] == f["assureur"]]
            if not hist_assur.empty:
                liq[h] += f["montant"] * (hist_assur["delai"] <= h).mean()
    return liq, taux_glob

# --- INTERFACE STREAMLIT ---

st.title("🏥 Analyseur de Facturation Suisse")
st.markdown("---")

st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        # Lecture initiale
        df_brut = pd.read_excel(uploaded_file, sheet_name="Factures", header=0)
        
        # --- FILTRES MÉTIERS ---
        st.sidebar.header("🔍 2. Filtres Métiers")
        fournisseurs = df_brut.iloc[:, 9].dropna().unique().tolist()
        
        # Définition des groupes pour faciliter la sélection
        groupes_codes = {
            "Physiothérapie": ["V 8254.26", "L 8393.24"],
            "Ergothérapie": ["N 6311.24"],
            "Massage": ["A 9709.63"]
        }
        
        selection = st.sidebar.multiselect(
            "Sélectionner les fournisseurs :", 
            options=sorted(fournisseurs), 
            default=fournisseurs
        )
        
        # --- OPTIONS STATISTIQUES ---
        st.sidebar.header("📊 3. Options")
        show_med = st.sidebar.checkbox("Afficher la Médiane")
        show_std = st.sidebar.checkbox("Afficher l'Écart-type")
        
        # --- PÉRIODES ---
        st.sidebar.header("📅 4. Périodes")
        options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2, "1 mois": 1}
        periods_sel = st.sidebar.multiselect(
            "Analyser les périodes :", 
            list(options_p.keys()), 
            default=["Global", "4 mois", "2 mois"]
        )

        if st.sidebar.button("🚀 Lancer l'analyse", type="primary"):
            # Filtrage des données
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
            
            # Constante : Factures actuellement en attente (Global)
            f_att = df[df["statut"].str.startswith("en attente") & (df["statut"] != "en attente (annulé)")].copy()
            f_att["delai"] = (ajd - f_att["date_facture"]).dt.days
            total_en_attente_fixe = f_att["montant"].sum()

            # Création des onglets Web
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
                    st.metric("Total Global en attente", f"{round(total_en_attente_global_fixe if 'total_en_attente_global_fixe' in locals() else total_en_attente_fixe)} CHF")
                    
                    data_liq = {
                        "Horizon": ["10 jours", "20 jours", "30 jours"],
                        "Estimation (CHF)": [round(liq[10]), round(liq[20]), round(liq[30])],
                        "Probabilité": [f"{round(t[10]*100)}%", f"{round(t[20]*100)}%", f"{round(t[30]*100)}%"]
                    }
                    st.table(pd.DataFrame(data_liq))
                    st.markdown("---")

                with tab2:
                    st.subheader(f"Délais par assureur ({p_name})")
                    if not p_hist.empty:
                        stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std']).reset_index()
                        stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Écart-type (j)"]
                        stats["Moyenne (j)"] = stats["Moyenne (j)"].round(0).astype(int)
                        
                        cols = ["Assureur", "Moyenne (j)"]
                        if show_med: 
                            stats["Médiane (j)"] = stats["Médiane (j)"].round(0).astype(int)
                            cols.append("Médiane (j)")
                        if show_std: 
                            stats["Écart-type (j)"] = stats["Écart-type (j)"].round(1)
                            cols.append("Écart-type (j)")
                        
                        st.dataframe(stats[cols].sort_values("Moyenne (j)", ascending=False), use_container_width=True)
                    else:
                        st.warning("Aucun paiement historique sur cette période.")

                with tab3:
                    st.subheader(f"Analyse des retards > 30j ({p_name})")
                    df_att_30 = f_att[f_att["delai"] > 30].copy()
                    df_pay_30 = p_hist[p_hist["delai"] > 30].copy()
                    plus_30 = pd.concat([df_pay_30, df_att_30])
                    
                    total_assureur = df_p.groupby("assureur").size().reset_index(name="total")
                    ret_assur = plus_30.groupby("assureur").size().reset_index(name="nb_retard")
                    
                    merged = pd.merge(ret_assur, total_assureur, on="assureur", how="right").fillna(0)
                    merged["% retard"] = (merged["nb_retard"] / merged["total"] * 100).round(0).astype(int)
                    
                    st.write(f"Total des factures en retard : **{len(plus_30)}**")
                    st.dataframe(merged[["assureur", "nb_retard", "% retard"]].sort_values("% retard", ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"Erreur lors de l'analyse : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel dans la barre latérale pour commencer.")
