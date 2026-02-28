import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import altair as alt

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- CONSTANTES ET LOGIQUE MÉTIER ---
MOTS_EXCLUSION = {"BERNOIS", "NEUCHATELOIS", "VALAISANS", "GENEVOIS", "VAUDOIS", "FRIBOURGEOIS"}
COULEURS_PROF = {"Physiothérapie": "#00CCFF", "Ergothérapie": "#FF9900", "Massage": "#00CC96", "Autre": "#AB63FA"}

def assigner_profession(code):
    """Logique métier spécifique au module Tarifs"""
    c = str(code).strip().lower()
    if 'rem' in c: return "Autre"
    if any(x in c for x in ['privé', 'abo', 'thais']) or c.startswith(('73', '25', '15.30')): 
        return "Physiothérapie"
    if any(x in c for x in ['foyer']) or c.startswith(('76', '31', '32')): 
        return "Ergothérapie"
    if c.startswith('1062'): 
        return "Massage"
    return "Autre"

def convertir_date(val):
    """Conversion robuste des dates pour tous les modules"""
    if pd.isna(val) or str(val).strip() == "": return pd.NaT
    if isinstance(val, pd.Timestamp): return val
    try:
        return pd.to_datetime(str(val).strip(), format="%d.%m.%Y", errors="coerce")
    except:
        return pd.to_datetime(val, errors="coerce")

def calculer_liquidites_fournisseur(f_attente, p_hist, jours_horizons):
    """Calcul de probabilité de paiement pour le module Facturation"""
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

# --- INITIALISATION DE L'ÉTAT ---
if 'page' not in st.session_state:
    st.session_state.page = "accueil"
if 'analyse_lancee' not in st.session_state:
    st.session_state.analyse_lancee = False

# ==========================================
# 🏠 PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse de Ephysio")
    st.markdown("---")
    st.write("### Choisissez le module d'analyse souhaité :")
    
    # Injection de CSS pour transformer les boutons en "tuiles" d'application
    st.markdown("""
    <style>
    div.stButton > button {
        height: 120px;
        border-radius: 12px;
        border: 2px solid #f0f2f6;
        background-color: #ffffff;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.2s ease-in-out;
    }
    div.stButton > button:hover {
        border-color: #00CCFF; /* Couleur de survol (Bleu médical) */
        transform: translateY(-4px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.1);
    }
    div.stButton > button p {
        font-size: 22px;
        font-weight: 600;
        color: #31333F;
    }
    </style>
    """, unsafe_allow_html=True)

    # Ligne 1 : 3 modules
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Facturation", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
        st.caption("📌 Export et analyse des factures")
            
    with col2:
        if st.button("👨‍⚕️ Médecins", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()
        st.caption("📌 Performance et CA par médecin")

    with col3:
        if st.button("🏷️ Tarifs", use_container_width=True):
            st.session_state.page = "tarifs"
            st.rerun()
        st.caption("📌 Tendances des prestations")

    st.write("") # Petit espace entre les deux lignes
    st.write("")

    # Ligne 2 : 2 modules (dans une grille de 3 pour garder la même largeur de bouton)
    col4, col5, col6 = st.columns(3)
    
    with col4:
        if st.button("🏦 Bilan Comptable", use_container_width=True):
            st.session_state.page = "bilan"
            st.rerun()
        st.caption("📌 Synthèse annuelle par fournisseur")

    with col5:
        if st.button("👥 Stats Patients", use_container_width=True):
            st.session_state.page = "stats_patients"
            st.rerun()
        st.caption("📌 Pilotage du flux et occupation")

# ==========================================
# 📊 MODULE FACTURES (ORIGINAL RÉPARÉ)
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

            df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df = df.rename(columns={
                df.columns[2]: "date_facture", df.columns[4]: "loi", 
                df.columns[8]: "assureur", df.columns[9]: "fournisseur", 
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
                        assur_sel = st.multiselect("Sélectionner les assureurs :", options=df_pv.index.tolist(), default=[a for a in top_assurances if a in df_pv.index])
                        if assur_sel:
                            df_plot = df_pv.loc[assur_sel].T
                            df_plot.index = pd.CategoricalIndex(df_plot.index, categories=ordre_chrono, ordered=True)
                            st.line_chart(df_plot.sort_index())
                            st.dataframe(df_pv.loc[assur_sel].style.highlight_max(axis=1, color='#ff9999').highlight_min(axis=1, color='#99ff99'))
        except Exception as e: st.error(f"Erreur d'analyse : {e}")

# ==========================================
# 🩺 MODULE MÉDECINS (ORIGINAL)
# ==========================================
elif st.session_state.page == "medecins":
    st.markdown("<style>.block-container { padding-left: 1rem; padding-right: 1rem; max-width: 100%; }</style>", unsafe_allow_html=True)
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.header("👨‍⚕️ Performance Médecins")
    uploaded_file = st.sidebar.file_uploader("Fichier Excel (.xlsx)", type="xlsx", key="med_up")
    
    if uploaded_file:
        try:
            df_brut = pd.read_excel(uploaded_file, header=0)
            st.sidebar.header("🔍 Filtres")
            fourn_med = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_fourn_med = st.sidebar.multiselect("Fournisseurs :", fourn_med, default=fourn_med)
            df_m_init = df_brut[df_brut.iloc[:, 5].astype(str).str.upper() != "TG"].copy()
            df_m_init = df_m_init[df_m_init.iloc[:, 9].isin(sel_fourn_med)]

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
                    chart = data_layer if visibility == "Données" else trend_layer if visibility == "Ligne" else data_layer + trend_layer
                    st.altair_chart(chart, use_container_width=True)
                    st.dataframe(tab_final[tab_final["medecin"].isin(choix)].sort_values("CA Global", ascending=False)[["medecin", "CA Global", "CA 365j", "CA 90j", "Tendance"]], use_container_width=True, hide_index=True)
        except Exception as e: st.error(f"Erreur technique : {e}")

# ==========================================
# 🏷️ MODULE TARIFS (PERFORMANCE & TENDANCES)
# ==========================================
elif st.session_state.page == "tarifs":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("📊 Analyse des revenus mensuels et Tendances")
    uploaded_file = st.sidebar.file_uploader("📂 Déposer l'export Excel (onglet 'Prestation')", type="xlsx", key="tarif_up")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, sheet_name='Prestation')
            nom_col_code = df.columns[2]   # C (Tarif)
            nom_col_somme = df.columns[11] # L (Montant)
            date_cols = [c for c in df.columns if 'Date' in str(c)]
            nom_col_date = date_cols[0] if date_cols else df.columns[0]

            df[nom_col_somme] = pd.to_numeric(df[nom_col_somme], errors='coerce')
            df[nom_col_date] = pd.to_datetime(df[nom_col_date], errors='coerce')
            df = df[df[nom_col_somme] > 0].dropna(subset=[nom_col_date, nom_col_somme])
            
            # --- GESTION DE LA PÉRIODE ET AFFICHAGE ---
            st.sidebar.header("📅 Période & Graphique")
            exclure_actuel = st.sidebar.toggle("Exclure le mois en cours", value=True)
            y_axis_zero = st.sidebar.toggle("Forcer l'axe Y à zéro", value=False)
            
            maintenant = pd.Timestamp(datetime.today().date())
            
            if exclure_actuel:
                reference_date = maintenant.replace(day=1) - pd.Timedelta(days=1)
                df = df[df[nom_col_date] <= reference_date]
            else:
                reference_date = maintenant

            df['Profession'] = df[nom_col_code].apply(assigner_profession)

            # --- FILTRAGE ---
            st.sidebar.header("⚙️ Filtres")
            professions_dispo = sorted(df['Profession'].unique())
            metiers_actifs = [p for p in professions_dispo if st.sidebar.checkbox(p, value=True, key=f"t_check_{p}")]

            codes_possibles = df[df['Profession'].isin(metiers_actifs)]
            liste_codes = sorted(codes_possibles[nom_col_code].unique().astype(str))
            selection_codes = st.sidebar.multiselect("Codes à afficher :", options=liste_codes, default=liste_codes)

            view_mode = st.radio("Affichage :", ["Profession", "Code tarifaire"], horizontal=True)
            chart_type = st.radio("Style :", ["Barres", "Courbes"], horizontal=True)

            df_filtered = df[df[nom_col_code].astype(str).isin(selection_codes)].copy()

            if not df_filtered.empty:
                # 1. GRAPHIQUE D'ÉVOLUTION
                df_filtered['Mois'] = df_filtered[nom_col_date].dt.to_period('M').dt.to_timestamp()
                target_col = "Profession" if view_mode == "Profession" else nom_col_code
                df_plot = df_filtered.groupby(['Mois', target_col])[nom_col_somme].sum().reset_index()
                
                color_map = COULEURS_PROF if view_mode == "Profession" else None
                if chart_type == "Barres":
                    fig = px.bar(df_plot, x='Mois', y=nom_col_somme, color=target_col, 
                                 barmode='group', color_discrete_map=color_map, text_auto='.2f')
                else:
                    fig = px.line(df_plot, x='Mois', y=nom_col_somme, color=target_col, 
                                  markers=True, color_discrete_map=color_map)
                
                # Application de la logique d'axe Y
                if y_axis_zero:
                    fig.update_yaxes(rangemode="tozero")
                else:
                    fig.update_yaxes(rangemode="normal")

                fig.update_xaxes(dtick="M1", tickformat="%b %Y")
                st.plotly_chart(fig, use_container_width=True)

                # 2. TABLEAU DES TENDANCES
                st.markdown(f"### 📈 Performance par Tarif (Base : {reference_date.strftime('%d.%m.%Y')})")
                
                t_90j = reference_date - pd.DateOffset(days=90)
                t_365j = reference_date - pd.DateOffset(days=365)
                
                stats_global = df_filtered.groupby(nom_col_code)[nom_col_somme].sum().reset_index(name="CA Global")
                ca_90 = df_filtered[df_filtered[nom_col_date] >= t_90j].groupby(nom_col_code)[nom_col_somme].sum().reset_index(name="CA 90j")
                ca_365 = df_filtered[df_filtered[nom_col_date] >= t_365j].groupby(nom_col_code)[nom_col_somme].sum().reset_index(name="CA 365j")
                
                tab_perf = stats_global.merge(ca_365, on=nom_col_code, how="left").merge(ca_90, on=nom_col_code, how="left").fillna(0)
                
                def calculer_tendance_tarif(r):
                    if r['CA 365j'] > 0:
                        ratio = (r['CA 90j'] / r['CA 365j']) * 100
                        if ratio <= 23: return f"↘️ Baisse ({ratio:.1f}%)"
                        if ratio >= 27: return f"↗️ Hausse ({ratio:.1f}%)"
                        return "➡️ Stable"
                    return "N/A"

                tab_perf["Tendance"] = tab_perf.apply(calculer_tendance_tarif, axis=1)
                
                st.dataframe(
                    tab_perf.sort_values("CA Global", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        nom_col_code: "Code Tarifaire",
                        "CA Global": st.column_config.NumberColumn("CA Global", format="%.2f CHF"),
                        "CA 365j": st.column_config.NumberColumn("CA 365j", format="%.2f CHF"),
                        "CA 90j": st.column_config.NumberColumn("CA 90j", format="%.2f CHF")
                    }
                )
            else:
                st.warning("Aucune donnée disponible pour cette sélection.")
                
        except Exception as e: st.error(f"Erreur Tarifs : {e}")
# ==========================================
# 🏦 MODULE BILAN COMPTABLE (V10 - AVEC LIGNE TOTAL)
# ==========================================
elif st.session_state.page == "bilan":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("🏦 Bilan des Revenus par Fournisseur")
    up = st.sidebar.file_uploader("Fichier Excel (Export avec onglet Facture)", type="xlsx", key="bilan_up")
    
    if up:
        try:
            xl = pd.ExcelFile(up)
            ong_f = next((s for s in xl.sheet_names if 'Facture' in s), None)
            
            if not ong_f:
                st.error("L'onglet 'Facture' est introuvable.")
                st.stop()
            
            df_f = pd.read_excel(up, sheet_name=ong_f)
            
           # --- CONFIGURATION DES COLONNES ---
            col_date_f = df_f.columns[2]   # C: Date de la facture
            col_fourn_f = df_f.columns[9]  # J: Fournisseur
            col_ca_f = df_f.columns[14]    # O: Montant (CA)
            col_paye_f = df_f.columns[15]  # P: Date de paiement
            
            df_f[col_date_f] = pd.to_datetime(df_f[col_date_f], errors='coerce')
            df_f[col_ca_f] = pd.to_numeric(df_f[col_ca_f], errors='coerce').fillna(0)
            df_f = df_f.dropna(subset=[col_date_f])

            # Extraction des années uniques
            annees = sorted(df_f[col_date_f].dt.year.unique().astype(int), reverse=True)
            
            # --- NOUVEAU : ALERTE MULTI-ANNÉES ---
            if len(annees) > 1:
                st.warning(
                    f"⚠️ **Attention :** L'export chargé contient des données sur {len(annees)} années différentes "
                    f"({min(annees)} à {max(annees)}). Le bilan est conçu pour analyser un exercice comptable unique. "
                    "Veuillez faire un export des prestations du 1er janvier au 31 décembre d'une seule année."
                )

            annee = st.sidebar.selectbox("Année d'analyse :", annees)
            df_sel = df_f[df_f[col_date_f].dt.year == annee].copy()

            # --- SECTION CHIFFRE D'AFFAIRES ---
            st.subheader(f"📊 Analyse du Chiffre d'Affaires ({annee})")
            vue_ca = st.radio("Affichage CA par Fournisseur :", ["Annuel (Cumulé)", "Mensuel (Détail)"], horizontal=True)

            if vue_ca == "Annuel (Cumulé)":
                ca_fourn = df_sel.groupby(col_fourn_f)[col_ca_f].sum().sort_values(ascending=False).reset_index()
                
                # Ajout de la ligne Total pour le cumul annuel
                total_val = ca_fourn[col_ca_f].sum()
                ligne_total = pd.DataFrame({col_fourn_f: ['TOTAL GÉNÉRAL'], col_ca_f: [total_val]})
                ca_fourn = pd.concat([ca_fourn, ligne_total], ignore_index=True)
                
                st.dataframe(
                    ca_fourn, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        col_fourn_f: "Fournisseur", 
                        col_ca_f: st.column_config.NumberColumn("Total CA", format="%.2f CHF")
                    }
                )
            else:
                df_sel['Mois_Num'] = df_sel[col_date_f].dt.month
                nom_mois = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Août", "Sep", "Oct", "Nov", "Déc"]
                
                pivot_fourn = df_sel.pivot_table(index=col_fourn_f, columns='Mois_Num', values=col_ca_f, aggfunc='sum', fill_value=0)
                pivot_fourn = pivot_fourn.reindex(columns=range(1, 13), fill_value=0)
                pivot_fourn.columns = nom_mois
                pivot_fourn['TOTAL'] = pivot_fourn.sum(axis=1)
                
                # Ajout de la ligne de Totalisation en bas du tableau mensuel
                pivot_total = pivot_fourn.sum(axis=0).to_frame().T
                pivot_total.index = ["TOTAL GÉNÉRAL"]
                pivot_final = pd.concat([pivot_fourn, pivot_total])
                
                st.dataframe(pivot_final.style.format("{:.2f}").highlight_max(axis=0, color="#d4f1f9"), use_container_width=True)

            # --- SECTION IMPAYÉS AU 31.12 ---
            st.markdown("---")
            st.subheader(f"⏳ Factures Impayées au 31.12.{annee}")
            
            df_impayes = df_sel[df_sel[col_paye_f].isna()].copy()
            total_impayes = df_impayes[col_ca_f].sum()

            if total_impayes > 0:
                st.warning(f"Montant total restant à percevoir pour {annee} : **{total_impayes:,.2f} CHF**")
                imp_par_fourn = df_impayes.groupby(col_fourn_f)[col_ca_f].sum().sort_values(ascending=False).reset_index()
                
                # Ajout de la ligne Total aussi pour les impayés
                ligne_total_imp = pd.DataFrame({col_fourn_f: ['TOTAL DES IMPAYÉS'], col_ca_f: [total_impayes]})
                imp_par_fourn = pd.concat([imp_par_fourn, ligne_total_imp], ignore_index=True)
                
                with st.expander("Voir le détail des impayés par fournisseur"):
                    st.dataframe(
                        imp_par_fourn, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={col_fourn_f: "Fournisseur", col_ca_f: st.column_config.NumberColumn("Montant dû", format="%.2f CHF")}
                    )
            else:
                st.success(f"Toutes les factures de l'année {annee} sont marquées comme payées.")

        except Exception as e:
            st.error(f"Erreur d'analyse : {e}")

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# 👥 MODULE : PILOTAGE FLUX (V11.1 - Final Fix)
# ==========================================
def render_stats_patients():
    if st.sidebar.button("⬅️ Retour Accueil", key="btn_back_final"):
        st.session_state.page = "accueil"
        st.rerun()

    st.sidebar.markdown("---")
    uploaded_file = st.sidebar.file_uploader("📂 Déposer l'export Excel", type="xlsx", key="uploader_v11_1")

    st.title("👥 Pilotage du Flux Patients")

    if not uploaded_file:
        st.info("👋 Chargez un fichier Excel pour activer l'analyse comparative.")
        return

    try:
        @st.cache_data
        def get_full_analysis(file):
            df = pd.read_excel(file, sheet_name='Prestation')
            df.columns = [str(c).strip() for c in df.columns]
            
            c_date, c_tarif, c_pat, c_mont = df.columns[0], df.columns[2], df.columns[8], df.columns[11]
            df[c_date] = pd.to_datetime(df[c_date], errors='coerce')
            df[c_tarif] = df[c_tarif].astype(str).str.strip()
            
            codes = ["7301", "7311", "25.110"]
            df_f = df[(df[c_mont] > 0) & (df[c_tarif].isin(codes))].dropna(subset=[c_date, c_pat]).copy()
            
            # --- 1. CALCULS HISTORIQUES ---
            p_stats = df_f.groupby(c_pat).agg(
                nb_seances=(c_pat, 'size'),
                date_min=(c_date, 'min'),
                date_max=(c_date, 'max')
            )
            
            p_stats['jours_vie'] = (p_stats['date_max'] - p_stats['date_min']).dt.days
            p_suivis = p_stats[p_stats['jours_vie'] >= 7]
            rythme = p_suivis['nb_seances'].sum() / (p_suivis['jours_vie'].sum() / 7) if not p_suivis.empty else 1.1

            # --- 2. CALCUL DU FLUX RÉEL ---
            derniere_date = df_f[c_date].max()
            
            def stats_periode(jours):
                seuil = derniere_date - timedelta(days=jours)
                # Un patient est "nouveau" si sa toute première séance est dans la zone
                nouveaux = p_stats[p_stats['date_min'] >= seuil]
                count = len(nouveaux)
                jours_ouvres = (jours / 7) * 5
                return count, count / jours_ouvres if jours_ouvres > 0 else 0

            return {
                "moy_seances": p_stats['nb_seances'].mean(),
                "rythme_reel": rythme,
                "flux_30": stats_periode(30),
                "flux_60": stats_periode(60),
                "flux_120": stats_periode(120),
                "derniere_date": derniere_date
            }

        data = get_full_analysis(uploaded_file)

        # --- AFFICHAGE ANALYSE RÉELLE ---
        st.subheader(f"📈 Recrutement Réel (Calculé au {data['derniere_date'].strftime('%d/%m/%Y')})")
        c_r1, c_r2, c_r3 = st.columns(3)
        c_r1.metric("Derniers 30j", f"{data['flux_30'][0]} pat.", f"{data['flux_30'][1]:.1f} / jour")
        c_r2.metric("Derniers 60j", f"{data['flux_60'][0]} pat.", f"{data['flux_60'][1]:.1f} / jour")
        c_r3.metric("Derniers 120j", f"{data['flux_120'][0]} pat.", f"{data['flux_120'][1]:.1f} / jour")

        # --- FORMULAIRE CONFIGURATION ---
        with st.form("form_v11_1"):
            st.subheader("⚙️ Simulation des besoins (Cabinets A & B)")
            if 'capa_df' not in st.session_state:
                st.session_state.capa_df = pd.DataFrame([
                    {"Thérapeute": f"Thérapeute {i}", "Cabinet": "A" if i <= 6 else "B", 
                     "Places/Sem": 0, "Semaines/an": 43} for i in range(1, 13)
                ])

            config = {"Cabinet": st.column_config.SelectboxColumn("Cabinet", options=["A", "B"], required=True)}
            edited_df = st.data_editor(st.session_state.capa_df, column_config=config, use_container_width=True)

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                in_seances = st.number_input("Séances / traitement", value=float(round(data['moy_seances'], 1)))
                in_rythme = st.slider("Rythme hebdomadaire", 0.5, 3.0, float(round(data['rythme_reel'], 1)))
            with col_p2:
                in_occup = st.slider("Taux d'occupation visé (%)", 50, 100, 85)
                in_jours = st.slider("Jours d'ouverture / semaine", 1, 6, 5)

            btn_go = st.form_submit_button("🚀 CALCULER ET COMPARER", use_container_width=True, type="primary")

        if btn_go:
            st.session_state.capa_df = edited_df
            
            def calc_needs(df_p):
                annuel = (df_p['Places/Sem'] * df_p['Semaines/an']).sum()
                capa_h = (annuel * (in_occup/100)) / 52.14
                flux_h = (capa_h * in_rythme) / in_seances
                return capa_h, flux_h

            df_act = edited_df[edited_df['Places/Sem'] > 0]
            c_tot, f_tot = calc_needs(df_act)
            c_a, f_a = calc_needs(df_act[df_act['Cabinet'] == "A"])
            c_b, f_b = calc_needs(df_act[df_act['Cabinet'] == "B"])

            st.markdown("---")
            t_all, t_a, t_b = st.tabs(["📊 TOTAL GLOBAL", "🏠 CABINET A", "🏠 CABINET B"])

            with t_all:
                besoin_j = f_tot / in_jours
                st.success(f"### Besoin Total : **{besoin_j:.1f}** nouveaux / jour")
                diff = data['flux_60'][1] - besoin_j
                st.metric("Équilibre (Réel 60j vs Théorique)", f"{data['flux_60'][1]:.1f} / jour", delta=round(diff, 1))

            with t_a:
                st.info(f"### Besoin A : **{(f_a/in_jours):.1f}** nouveaux / jour")
                st.metric("Capacité Cible A", f"{c_a:.1f} RDV/sem")

            with t_b:
                st.warning(f"### Besoin B : **{(f_b/in_jours):.1f}** nouveaux / jour")
                st.metric("Capacité Cible B", f"{c_b:.1f} RDV/sem")

    except Exception as e:
        st.error(f"❌ Erreur : {e}")

# --- APPEL ---
if 'page' not in st.session_state: st.session_state.page = "accueil"
if st.session_state.page == "stats_patients": render_stats_patients()


