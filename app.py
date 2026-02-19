import pandas as pd
from datetime import datetime
import altair as alt

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- INITIALISATION DE L'ÉTAT ---
if 'page' not in st.session_state:
    st.session_state.page = "accueil"
if 'analyse_lancee' not in st.session_state:
    st.session_state.analyse_lancee = False

# --- LOGIQUE DE CALCUL (FONCTIONS ORIGINALES) ---
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
    st.markdown("---")
    st.write("### Choisissez le module d'analyse souhaité :")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("📊 **MODULE FACTURATION**")
        st.write("Analyse des liquidités, des délais de paiement par assureur et des retards.")
        if st.button("Accéder à l'Analyse Facturation", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
            
    with col2:
        st.success("🩺 **MODULE MÉDECINS**")
        st.write("Analyse du CA par médecin, tendances Vitalité (90j/365j) et top prescripteurs.")
        if st.button("Accéder à l'Analyse Médecins", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("📊 Analyse de la Facturation")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx", key="fact_file")

    if uploaded_file:
        try:
            df_brut = pd.read_excel(uploaded_file, header=0)
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

            # Sélection des colonnes par index pour éviter les erreurs d'objets Index
            df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
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

            if btn_simuler:
                jours_delta = (pd.Timestamp(date_cible) - ajd).days
                if jours_delta >= 0:
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
                        st.subheader(f"Liquidités : {p_name}")
                        horizons = [10, 20, 30]
                        liq, t = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                        st.table(pd.DataFrame({"Horizon": [f"Sous {h}j" for h in horizons], "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons], "Probabilité": [f"{round(t[h]*100)}%" for h in horizons]}))
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
                        
                        assur_sel = st.multiselect("Sélectionner les assureurs (Top 5 volume par défaut) :", 
                                                   options=df_pv.index.tolist(), 
                                                   default=[a for a in top_assurances if a in df_pv.index])
                        
                        if assur_sel:
                            df_plot = df_pv.loc[assur_sel].T
                            df_plot.index = pd.CategoricalIndex(df_plot.index, categories=ordre_chrono, ordered=True)
                            st.line_chart(df_plot.sort_index())
                            st.write("**Détails par période (en jours) :**")
                            st.caption("🔴 Rouge : Délai max (lent) | 🟢 Vert : Délai min (rapide) pour l'assureur.")
                            st.dataframe(df_pv.loc[assur_sel].style.highlight_max(axis=1, color='#ff9999').highlight_min(axis=1, color='#99ff99'))
                        else:
                            st.info("Veuillez sélectionner au moins un assureur.")

        except Exception as e:
            st.error(f"Erreur d'analyse : {e}")
# ==========================================
# 👨‍⚕️ MODULE MÉDECINS (FILTRE FOURNISSEUR INCLUS)
# ==========================================
elif st.session_state.page == "medecins":
    st.markdown("<style>.block-container { padding-left: 1rem; padding-right: 1rem; max-width: 100%; }</style>", unsafe_allow_html=True)
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.header("👨‍⚕️ Performance Médecins")
    MOTS_EXCLUSION = {"BERNOIS", "NEUCHATELOIS", "VALAISANS", "GENEVOIS", "VAUDOIS", "FRIBOURGEOIS"}
    uploaded_file = st.sidebar.file_uploader("Fichier Excel (.xlsx)", type="xlsx", key="med_up")
    
    if uploaded_file:
        try:
            df_brut = pd.read_excel(uploaded_file, header=0)
            
            # --- 1. FILTRES SIDEBAR (FOURNISSEUR RÉTABLI) ---
            st.sidebar.header("🔍 Filtres")
            fourn_med = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_fourn_med = st.sidebar.multiselect("Fournisseurs :", fourn_med, default=fourn_med)
            
            # Exclusion TG (Colonne F / Index 5)
            df_m_init = df_brut[df_brut.iloc[:, 5].astype(str).str.upper() != "TG"].copy()
            # Filtre Fournisseur
            df_m_init = df_m_init[df_m_init.iloc[:, 9].isin(sel_fourn_med)]

            # --- 2. FUSION AUTOMATIQUE ---
            def moteur_fusion_securise(df):
                noms_originaux = df.iloc[:, 7].dropna().unique()
                mapping = {}
                def extraire_mots(texte):
                    mots = "".join(c if c.isalnum() else " " for c in str(texte)).upper().split()
                    return {m for m in mots if len(m) > 2}
                noms_tries = sorted(noms_originaux, key=len, reverse=True)
                for i, nom_long in enumerate(noms_tries):
                    mots_long = extraire_mots(nom_long)
                    for nom_court in noms_tries[i+1:]:
                        mots_court = extraire_mots(nom_court)
                        conflit = any(m in mots_long.symmetric_difference(mots_court) for m in MOTS_EXCLUSION)
                        if len(mots_long.intersection(mots_court)) >= 2 and not conflit:
                            mapping[nom_court] = nom_long
                return mapping

            regroupements = moteur_fusion_securise(df_m_init)
            df_m_init.iloc[:, 7] = df_m_init.iloc[:, 7].replace(regroupements)
            
            # --- 3. PRÉPARATION & SÉCURITÉ ---
            ajd = pd.Timestamp(datetime.today().date())
            df_m_init["medecin"] = df_m_init.iloc[:, 7]
            df_m_init["ca"] = pd.to_numeric(df_m_init.iloc[:, 14], errors="coerce").fillna(0)
            df_m_init["date_f"] = df_m_init.iloc[:, 2].apply(convertir_date)
            df_m = df_m_init[(df_m_init["ca"] > 0) & (df_m_init["date_f"].notna()) & (df_m_init["date_f"] <= ajd) & (df_m_init["medecin"].notna())].copy()
            
            if not df_m.empty:
                t_90j, t_365j = ajd - pd.DateOffset(days=90), ajd - pd.DateOffset(days=365)
                stats_ca = df_m.groupby("medecin")["ca"].sum().reset_index(name="CA Global")
                ca_90 = df_m[df_m["date_f"] >= t_90j].groupby("medecin")["ca"].sum().reset_index(name="CA 90j")
                ca_365 = df_m[df_m["date_f"] >= t_365j].groupby("medecin")["ca"].sum().reset_index(name="CA 365j")
                tab_final = stats_ca.merge(ca_90, on="medecin", how="left").merge(ca_365, on="medecin", how="left").fillna(0)
                
                tab_final["Tendance"] = tab_final.apply(lambda r: f"↘️ Baisse ({(r['CA 90j']/r['CA 365j']*100):.1f}%)" if (r['CA 365j']>0 and r['CA 90j']/r['CA 365j']*100 <= 23) else f"↗️ Hausse ({(r['CA 90j']/r['CA 365j']*100):.1f}%)" if (r['CA 365j']>0 and r['CA 90j']/r['CA 365j']*100 >= 27) else "➡️ Stable", axis=1)

                st.markdown("### 🏆 Sélection et Visualisation")
                c1, c2, c3 = st.columns([1, 1, 1.5]) 
                with c1: m_top = st.selectbox("Top :", [5, 10, 25, 50, "Tout"], index=1)
                with c2: t_graph = st.radio("Style :", ["📊 Barres", "📈 Courbes"], horizontal=True)
                with c3: visibility = st.radio("Option Tendance :", ["Données", "Ligne", "Les deux"], index=0, horizontal=True)

                tab_s = tab_final.sort_values("CA Global", ascending=False)
                def_sel = tab_s["medecin"].tolist() if m_top == "Tout" else tab_s.head(int(m_top))["medecin"].tolist()
                choix = st.multiselect("Sélection :", options=sorted(tab_final["medecin"].unique()), default=def_sel)

                if choix:
                    df_p = df_m[df_m["medecin"].isin(choix)].copy()
                    df_p["M_Date"] = df_p["date_f"].dt.to_period("M").dt.to_timestamp()
                    df_p = df_p.groupby(["M_Date", "medecin"])["ca"].sum().reset_index()

                    base = alt.Chart(df_p).encode(
                        x=alt.X('M_Date:T', title="Mois", axis=alt.Axis(format='%m.%Y')),
                        y=alt.Y('ca:Q', title="CA (CHF)"),
                        color=alt.Color('medecin:N', legend=alt.Legend(orient='bottom', columns=2, labelLimit=0))
                    ).properties(height=600)

                    data_layer = base.mark_bar(opacity=0.6) if "Barres" in t_graph else base.mark_line(point=True)
                    trend_layer = base.transform_regression('M_Date', 'ca', groupby=['medecin']).mark_line(size=4, strokeDash=[6, 4])

                    if visibility == "Données": chart = data_layer
                    elif visibility == "Ligne": chart = trend_layer
                    else: chart = data_layer + trend_layer

                    st.altair_chart(chart, use_container_width=True)
                    st.dataframe(tab_final[tab_final["medecin"].isin(choix)].sort_values("CA Global", ascending=False)[["medecin", "CA Global", "CA 365j", "CA 90j", "Tendance"]], use_container_width=True, hide_index=True)
        except Exception as e: st.error(f"Erreur technique : {e}")
