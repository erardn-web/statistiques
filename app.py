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

# --- INTERFACE ---
st.title("🏥 Analyseur de Facturation Suisse")
st.markdown("---")

st.sidebar.header("📁 1. Importation")
uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx")

if uploaded_file:
    try:
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES (SIDEBAR) ---
        st.sidebar.header("🔍 2. Filtres")
        
        # Filtre Fournisseurs (Colonne J / Index 9)
        fournisseurs = df_brut.iloc[:, 9].dropna().unique().tolist()
        sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", options=sorted(fournisseurs), default=fournisseurs)
        
        # Filtre Lois (Colonne E / Index 4)
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
            st.session_state.calcul_medecin_lance = False
        btn_simuler = col_b2.button("🔮 Simuler", use_container_width=True)

        st.sidebar.markdown("---")
        if st.sidebar.button("🩺 Calcul Médecins", use_container_width=True):
            st.session_state.calcul_medecin_lance = True
            st.session_state.analyse_lancee = False

        # --- BLOC ANALYSE INITIALE (CONSERVÉ À 100%) ---
        if not st.session_state.calcul_medecin_lance:
            df = df_brut[
                (df_brut.iloc[:, 9].isin(sel_fournisseurs)) & 
                (df_brut.iloc[:, 4].isin(sel_lois))
            ].copy()

            df = df.rename(columns={
                df.columns[2]: "date_facture", 
                df.columns[4]: "loi",
                df.columns[8]: "assureur",
                df.columns[9]: "fournisseur", 
                df.columns[12]: "statut", 
                df.columns[13]: "montant", 
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
            st.markdown("---")

            if btn_simuler:
                jours_delta = (pd.Timestamp(date_cible) - ajd).days
                if jours_delta < 0:
                    st.error("La date doit être dans le futur.")
                else:
                    st.subheader(f"🔮 Simulation au {date_cible.strftime('%d.%m.%Y')} (+{jours_delta}j)")
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
                        st.table(pd.DataFrame({
                            "Horizon": [f"Sous {h}j" for h in horizons],
                            "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons],
                            "Probabilité": [f"{round(t[h]*100)}%" for h in horizons]
                        }))

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
                        merged["Nb Retards"] = merged["Nb Retards"].astype(int)
                        merged["% Retard"] = (merged["Nb Retards"] / merged["Volume Total"] * 100).round(1)
                        
                        st.metric(f"Total Retards ({p_name})", f"{int(merged['Nb Retards'].sum())} factures")
                        st.dataframe(merged[["assureur", "Nb Retards", "Volume Total", "% Retard"]].sort_values("% Retard", ascending=False), use_container_width=True)

                with tab4:
                    st.subheader("📈 Évolution du délai de remboursement")
                    ordre_chrono = ["Global", "6 mois", "4 mois", "3 mois", "2 mois"]
                    periodes_graph = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2}
                    evol_data = []
                    
                    p_hist_global = df[df["date_paiement"].notna()].copy()
                    top_assurances = p_hist_global.groupby("assureur").size().sort_values(ascending=False).head(5).index.tolist()

                    for n, v in periodes_graph.items():
                        lim = ajd - pd.DateOffset(months=v) if v else df["date_facture"].min()
                        h_tmp = df[(df["date_paiement"].notna()) & (df["date_facture"] >= lim)].copy()
                        h_tmp["delai"] = (h_tmp["date_paiement"] - h_tmp["date_facture"]).dt.days
                        if not h_tmp.empty:
                            m = h_tmp.groupby("assureur")["delai"].mean().reset_index()
                            m["Période"] = n
                            evol_data.append(m)

                    if evol_data:
                        df_ev = pd.concat(evol_data)
                        df_pv = df_ev.pivot(index="assureur", columns="Période", values="delai")
                        cols_presentes = [c for c in ordre_chrono if c in df_pv.columns]
                        df_pv = df_pv[cols_presentes]
                        
                        assur_sel = st.multiselect("Sélectionner les assureurs (Top 5 volume pré-sélectionnés) :", 
                                                   options=df_pv.index.tolist(), 
                                                   default=[a for a in top_assurances if a in df_pv.index])
                        
                        if assur_sel:
                            df_plot = df_pv.loc[assur_sel].T
                            df_plot.index = pd.CategoricalIndex(df_plot.index, categories=ordre_chrono, ordered=True)
                            df_plot = df_plot.sort_index()
                            
                            st.line_chart(df_plot)
                            st.write("**Détails par période (en jours) :**")
                            st.caption("🔴 Rouge : Délai max (lent) | 🟢 Vert : Délai min (rapide) pour l'assureur.")
                            st.dataframe(df_pv.loc[assur_sel].style.highlight_max(axis=1, color='#ff9999').highlight_min(axis=1, color='#99ff99'))

        # --- NOUVELLE FONCTIONNALITÉ MÉDECINS (INDÉPENDANTE) ---
        if st.session_state.calcul_medecin_lance:
            st.header("👨‍⚕️ Analyse des 10 plus gros Médecins Prescripteurs")
            if st.button("⬅️ Retour"):
                st.session_state.calcul_medecin_lance = False
                st.rerun()

            df_med = df_brut.copy()
            # H = index 7 (médecin), O = index 14 (CA), C = index 2 (date facture)
            df_med["nom_m"] = df_med.iloc[:, 7].fillna("Inconnu")
            df_med["ca_m"] = pd.to_numeric(df_med.iloc[:, 14], errors="coerce").fillna(0)
            df_med["dt_m"] = df_med.iloc[:, 2].apply(convertir_date)
            
            # Filtre : CA (Col O) > 0 uniquement
            df_med = df_med[(df_med["ca_m"] > 0) & (df_med["dt_m"].notna())]
            
            if not df_med.empty:
                df_med["Mois"] = df_med["dt_m"].dt.to_period("M").astype(str)
                top_10_names = df_med.groupby("nom_m")["ca_m"].sum().nlargest(10).index
                df_top = df_med[df_med["nom_m"].isin(top_10_names)]
                
                # Graphique en courbe indépendant
                pivot_m = df_top.groupby(["Mois", "nom_m"])["ca_m"].sum().unstack().fillna(0)
                st.line_chart(pivot_m)
                
                st.subheader("Classement CA cumulé (CHF)")
                st.table(df_med.groupby("nom_m")["ca_m"].sum().sort_values(ascending=False).head(10).apply(lambda x: f"{x:,.2f} CHF"))
            else:
                st.warning("Aucune donnée avec paiement trouvé en colonne O.")

    except Exception as e:
        st.error(f"Erreur : {e}")
else:
    st.info("👋 Veuillez charger votre fichier Excel (.xlsx).")
