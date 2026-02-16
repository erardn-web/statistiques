import streamlit as st
import pandas as pd
from datetime import datetime
import re

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
            st.session_state.calcul_medecin_lance = False
        btn_simuler = col_b2.button("🔮 Simuler", use_container_width=True)

        st.sidebar.markdown("---")
        if st.sidebar.button("🩺 Calcul Médecins", use_container_width=True):
            st.session_state.calcul_medecin_lance = True
            st.session_state.analyse_lancee = False

        # --- LOGIQUE ANALYSE INITIALE ---
        if not st.session_state.calcul_medecin_lance:
            df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df = df.rename(columns={
                df.columns[2]: "date_facture", df.columns[4]: "loi",
                df.columns[8]: "assureur", df.columns[9]: "fournisseur", 
                df.columns[12]: "statut", df.columns[13]: "montant", df.columns[15]: "date_paiement"
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
                if jours_delta >= 0:
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
                        liq, t = calculer_liquidites_fournisseur(f_att, p_hist, [10, 20, 30])
                        st.table(pd.DataFrame({"Horizon": ["Sous 10j", "Sous 20j", "Sous 30j"], "Estimation (CHF)": [f"{round(liq[h]):,}" for h in [10, 20, 30]], "Probabilité": [f"{round(t[h]*100)}%" for h in [10, 20, 30]]}))
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
                        merged = pd.merge(pd.concat([p_hist[p_hist["delai"] > 30], f_att[f_att["delai_actuel"] > 30]]).groupby("assureur").size().reset_index(name="Nb Retards"), df_p.groupby("assureur").size().reset_index(name="Volume Total"), on="assureur", how="right").fillna(0)
                        merged["% Retard"] = (merged["Nb Retards"] / merged["Volume Total"] * 100).round(1)
                        st.metric(f"Total Retards ({p_name})", f"{int(merged['Nb Retards'].sum())} factures")
                        st.dataframe(merged.sort_values("% Retard", ascending=False), use_container_width=True)
                with tab4:
                    st.subheader("📈 Évolution du délai de remboursement")
                    # ... [Logique Tab4 du script initial conservée] ...
                    ordre_chrono = ["Global", "6 mois", "4 mois", "3 mois", "2 mois"]
                    periodes_graph = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2}
                    evol_data = []
                    top_assurances = df[df["date_paiement"].notna()].groupby("assureur").size().sort_values(ascending=False).head(5).index.tolist()
                    for n, v in periodes_graph.items():
                        lim = ajd - pd.DateOffset(months=v) if v else df["date_facture"].min()
                        h_tmp = df[(df["date_paiement"].notna()) & (df["date_facture"] >= lim)].copy()
                        h_tmp["delai"] = (h_tmp["date_paiement"] - h_tmp["date_facture"]).dt.days
                        if not h_tmp.empty:
                            m = h_tmp.groupby("assureur")["delai"].mean().reset_index(); m["Période"] = n; evol_data.append(m)
                    if evol_data:
                        df_ev = pd.concat(evol_data).pivot(index="assureur", columns="Période", values="delai")[[c for c in ordre_chrono if c in pd.concat(evol_data).pivot(index="assureur", columns="Période", values="delai").columns]]
                        assur_sel = st.multiselect("Assureurs :", options=df_ev.index.tolist(), default=[a for a in top_assurances if a in df_ev.index])
                        if assur_sel:
                            st.line_chart(df_ev.loc[assur_sel].T.sort_index())

        # --- NOUVELLE FONCTIONNALITÉ MÉDECINS (GROUPEMENT INTELLIGENT) ---
        if st.session_state.calcul_medecin_lance:
            st.header("👨‍⚕️ Analyse des Médecins & Institutions")
            if st.button("⬅️ Retour"): st.session_state.calcul_medecin_lance = False; st.rerun()

            def normaliser_nom(nom):
                if pd.isna(nom) or str(nom).strip() == "": return ""
                # Supprime parenthèses et ponctuation, garde les mots de > 1 lettre, trie alphabétiquement
                n = re.sub(r'[^\w\s]', ' ', str(nom).upper())
                mots = sorted([m.strip() for m in n.split() if len(m.strip()) > 1])
                return " ".join(mots)

            df_m = df_brut.copy()
            df_m["med_brut"] = df_m.iloc[:, 7]
            df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
            df_m["dt"] = df_m.iloc[:, 2].apply(convertir_date)
            df_m["groupe"] = df_m["med_brut"].apply(normaliser_nom)
            df_m = df_m[(df_m["ca"] > 0) & (df_m["dt"].notna()) & (df_m["groupe"] != "")].copy()
            
            if not df_m.empty:
                # Mapping pour afficher le nom le plus long/complet du groupe
                noms_clairs = df_m.groupby("groupe")["med_brut"].apply(lambda x: max(x.astype(str), key=len)).to_dict()
                df_m["affichage"] = df_m["groupe"].map(noms_clairs)
                
                liste_meds = sorted(df_m["affichage"].unique().tolist())
                choix = st.multiselect("🎯 Filtrer les prescripteurs :", options=liste_meds, default=df_m.groupby("affichage")["ca"].sum().nlargest(10).index.tolist())
                
                if choix:
                    df_f = df_m[df_m["affichage"].isin(choix)].sort_values("dt")
                    df_f["Mois"] = df_f["dt"].dt.to_period("M").astype(str)
                    st.line_chart(df_f.groupby(["Mois", "affichage"])["ca"].sum().unstack().fillna(0))
                    st.subheader("CA Cumulé (CHF)")
                    st.table(df_f.groupby("affichage")["ca"].sum().sort_values(ascending=False).apply(lambda x: f"{x:,.2f} CHF"))

    except Exception as e: st.error(f"Erreur : {e}")
else: st.info("👋 Veuillez charger votre fichier Excel.")
