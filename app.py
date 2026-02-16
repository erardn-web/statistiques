import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- INITIALISATION DE L'ÉTAT DE NAVIGATION ---
if 'page' not in st.session_state:
    st.session_state.page = "accueil"
if 'analyse_lancee' not in st.session_state:
    st.session_state.analyse_lancee = False

# --- LOGIQUE DE CALCUL (TES FONCTIONS) ---
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
# 🏠 PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse de Facturation")
    st.write("Bienvenue. Sélectionnez le module de travail :")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 ANALYSE FACTURATION (Liquidités/Délais)", use_container_width=True, height=150):
            st.session_state.page = "factures"
            st.rerun()
    with col2:
        if st.button("🩺 ANALYSE MÉDECINS (CA/Prescriptions)", use_container_width=True, height=150):
            st.session_state.page = "medecins"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES (TON CODE INITIAL)
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("🏥 Analyseur de Facturation Suisse")
    st.sidebar.header("📁 1. Importation")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

    if uploaded_file:
        try:
            df_brut = pd.read_excel(uploaded_file, header=0)
            
            # --- FILTRES (SIDEBAR) ---
            st.sidebar.header("🔍 2. Filtres")
            fournisseurs = df_brut.iloc[:, 9].dropna().unique().tolist()
            sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", options=sorted(fournisseurs), default=fournisseurs)
            
            lois = df_brut.iloc[:, 4].dropna().unique().tolist()
            sel_lois = st.sidebar.multiselect("Types de Loi :", options=sorted(lois), default=lois)
            
            st.sidebar.header("📊 3. Options Délais")
            show_med = st.sidebar.checkbox("Afficher la Médiane", value=True)
            show_std = st.sidebar.checkbox("Afficher l'Écart-type", value=True)
            
            st.sidebar.header("📅 4. Périodes & Simulation")
            options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2, "1 mois": 1}
            periods_sel = st.sidebar.multiselect("Analyser les périodes :", list(options_p.keys()), default=["Global", "4 mois"])
            date_cible = st.sidebar.date_input("Date cible (simulation) :", value=datetime.today())
            
            col_b1, col_b2 = st.sidebar.columns(2)
            if col_b1.button("🚀 Analyser", type="primary", use_container_width=True):
                st.session_state.analyse_lancee = True
            btn_simuler = col_b2.button("🔮 Simuler", use_container_width=True)

            # --- LOGIQUE ANALYSE (TON CODE) ---
            df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df = df.rename(columns={
                df.columns[2]: "date_facture", df.columns[4]: "loi", df.columns[8]: "assureur",
                df.columns[9]: "fournisseur", df.columns[12]: "statut", df.columns[13]: "montant", 
                df.columns[15]: "date_paiement"
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

            if btn_simuler:
                jours_delta = (pd.Timestamp(date_cible) - ajd).days
                if jours_delta < 0: st.error("La date doit être dans le futur.")
                else:
                    st.subheader(f"🔮 Simulation au {date_cible.strftime('%d.%m.%Y')}")
                    res_sim = []
                    for p_nom in periods_sel:
                        val = options_p[p_nom]
                        limit = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                        p_hist_sim = df[(df["date_paiement"].notna()) & (df["date_facture"] >= limit)].copy()
                        p_hist_sim["delai"] = (p_hist_sim["date_paiement"] - p_hist_sim["date_facture"]).dt.days
                        liq, t = calculer_liquidites_fournisseur(f_att, p_hist_sim, [jours_delta])
                        res_sim.append({"Période": p_nom, "Estimation (CHF)": f"{round(liq[jours_delta]):,}", "Probabilité": f"{t[jours_delta]:.1%}"})
                    st.table(pd.DataFrame(res_sim))

            if st.session_state.analyse_lancee:
                tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
                for p_name in periods_sel:
                    val = options_p[p_name]
                    limit_p = ajd - pd.DateOffset(months=val) if val else df["date_facture"].min()
                    df_p = df[df["date_facture"] >= limit_p]
                    p_hist = df_p[df_p["date_paiement"].notna()].copy()
                    p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
                    
                    with tab1:
                        st.subheader(f"Période : {p_name}")
                        horizons = [10, 20, 30]
                        liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                        st.table(pd.DataFrame({"Horizon": [f"Sous {h}j" for h in horizons], "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons], "Probabilité": [f"{round(t[h]*100)}%" for h in horizons]}))

                    with tab2:
                        st.subheader(f"Délais par assureur ({p_name})")
                        if not p_hist.empty:
                            stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median', 'std']).reset_index()
                            stats.columns = ["Assureur", "Moyenne (j)", "Médiane (j)", "Écart-type (j)"]
                            cols = ["Assureur", "Moyenne (j)"]
                            if show_med: cols.append("Médiane (j)")
                            if show_std: cols.append("Écart-type (j)")
                            st.dataframe(stats[cols].sort_values("Moyenne (j)", ascending=False), use_container_width=True)

                    with tab3:
                        st.subheader(f"Analyse des retards > 30j ({p_name})")
                        df_att_30 = f_att[f_att["delai_actuel"] > 30].copy()
                        df_pay_30 = p_hist[p_hist["delai"] > 30].copy()
                        plus_30 = pd.concat([df_pay_30, df_att_30])
                        total_vol = df_p.groupby("assureur").size().reset_index(name="Volume Total")
                        ret_assur = plus_30.groupby("assureur").size().reset_index(name="Nb Retards")
                        merged = pd.merge(ret_assur, total_vol, on="assureur", how="right").fillna(0)
                        merged["% Retard"] = (merged["Nb Retards"] / merged["Volume Total"] * 100).round(1)
                        st.dataframe(merged.sort_values("% Retard", ascending=False), use_container_width=True)

                with tab4:
                    # (Ton code graphique ici)
                    st.write("Module Graphique actif.")

        except Exception as e:
            st.error(f"Erreur : {e}")

# ==========================================
# 👨‍⚕️ MODULE MÉDECINS (TON CODE INITIAL)
# ==========================================
elif st.session_state.page == "medecins":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.header("👨‍⚕️ Top Médecins Prescripteurs")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel", type="xlsx", key="med_file")
    
    if uploaded_file:
        df_brut = pd.read_excel(uploaded_file, header=0)
        df_m = df_brut.copy()
        df_m["medecin"] = df_m.iloc[:, 7] 
        df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0) 
        df_m["date_f"] = df_m.iloc[:, 2].apply(convertir_date) 
        
        df_m = df_m[(df_m["ca"] > 0) & (df_m["date_f"].notna()) & (df_m["medecin"].notna())].copy()
        
        if not df_m.empty:
            top_global = df_m.groupby("medecin")["ca"].sum().nlargest(10).index.tolist()
            choix_meds = st.multiselect("Sélectionner les médecins :", options=sorted(df_m["medecin"].unique().tolist()), default=top_global)
            
            if choix_meds:
                df_final = df_m[df_m["medecin"].isin(choix_meds)].copy()
                df_final["Mois"] = df_final["date_f"].dt.to_period("M").astype(str)
                pivot_m = df_final.groupby(["Mois", "medecin"])["ca"].sum().unstack().fillna(0)
                st.line_chart(pivot_m)
                st.subheader("Classement CA Cumulé (CHF)")
                st.table(df_final.groupby("medecin")["ca"].sum().sort_values(ascending=False).apply(lambda x: f"{x:,.2f} CHF"))
