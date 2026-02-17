import streamlit as st
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
        if st.button("Accéder à l'Analyse Facturation", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
            
    with col2:
        st.success("🩺 **MODULE MÉDECINS**")
        if st.button("Accéder à l'Analyse Médecins", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES (INTOUCHÉ)
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

            if st.session_state.analyse_lancee:
                tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
                # (Tes onglets originaux s'exécutent ici)
        except Exception as e: st.error(f"Erreur : {e}")

# ==========================================
# 👨‍⚕️ MODULE MÉDECINS (TENDANCE LINÉAIRE XXL)
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
            fourn_med = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_fourn_med = st.sidebar.multiselect("Filtrer par Fournisseur :", fourn_med, default=fourn_med)
            
            df_m = df_brut[df_brut.iloc[:, 9].isin(sel_fourn_med)].copy()
            df_m["medecin"] = df_m.iloc[:, 7] 
            df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0) 
            df_m["date_f"] = df_m.iloc[:, 2].apply(convertir_date) 
            df_m = df_m[(df_m["ca"] > 0) & (df_m["date_f"].notna()) & (df_m["medecin"].notna())].copy()
            
            if not df_m.empty:
                ajd = pd.Timestamp(datetime.today())
                t_90j, t_365j = ajd - pd.DateOffset(days=90), ajd - pd.DateOffset(days=365)
                stats_ca = df_m.groupby("medecin")["ca"].sum().reset_index(name="CA Global")
                ca_90 = df_m[df_m["date_f"] >= t_90j].groupby("medecin")["ca"].sum().reset_index(name="CA 90j")
                ca_365 = df_m[df_m["date_f"] >= t_365j].groupby("medecin")["ca"].sum().reset_index(name="CA 365j")
                tab_final = stats_ca.merge(ca_90, on="medecin", how="left").merge(ca_365, on="medecin", how="left").fillna(0)

                def calc_t(row):
                    if row["CA 365j"] <= 0: return "⚪ Inconnu"
                    ratio = (row["CA 90j"] / row["CA 365j"]) * 100
                    return f"↘️ Baisse ({ratio:.1f}%)" if ratio <= 23 else (f"↗️ Hausse ({ratio:.1f}%)" if ratio >= 27 else f"➡️ Stable ({ratio:.1f}%)")
                tab_final["Tendance"] = tab_final.apply(calc_t, axis=1)

                st.markdown("### 🏆 Sélection et Visualisation")
                c1, c2, c3 = st.columns([1, 1, 1.5])
                with c1: m_top = st.selectbox("Top :", [5, 10, 25, 50, "Tout"], index=1)
                with c2: t_graph = st.radio("Style :", ["📊 Barres", "📈 Lignes"], horizontal=True)
                with c3: visibility = st.radio("Affichage :", ["Données", "Tendance Linéaire", "Les deux"], index=0, horizontal=True)

                tab_s = tab_final.sort_values("CA Global", ascending=False)
                def_sel = tab_s["medecin"].tolist() if m_top == "Tout" else tab_s.head(int(m_top))["medecin"].tolist()
                choix = st.multiselect("Affiner la sélection :", options=sorted(tab_final["medecin"].unique()), default=def_sel)

                if choix:
                    df_p = df_m[df_m["medecin"].isin(choix)].copy()
                    df_p = df_p.sort_values("date_f")
                    df_p["Mois"] = df_p["date_f"].dt.to_period("M").astype(str)
                    df_p = df_p.groupby(["Mois", "medecin"])["ca"].sum().reset_index()

                    # --- CORRECTION TENDANCE LINÉAIRE ---
                    mois_uniques = sorted(df_p["Mois"].unique())
                    mapping_mois = {m: i for i, m in enumerate(mois_uniques)}
                    df_p["x_index"] = df_p["Mois"].map(mapping_mois)

                    base = alt.Chart(df_p).encode(
                        x=alt.X('Mois:O', title="Mois", sort=mois_uniques),
                        y=alt.Y('ca:Q', title="CA (CHF)"),
                        color=alt.Color('medecin:N', legend=alt.Legend(orient='bottom', columns=5))
                    ).properties(height=600)

                    data_layer = base.mark_bar(opacity=0.6) if "Barres" in t_graph else base.mark_line(point=True)
                    # strokeDash=[6, 4] définit les pointillés
                    trend_layer = base.transform_regression('x_index', 'ca', groupby=['medecin']).mark_line(size=4, strokeDash=[6, 4])

                    if visibility == "Données": chart = data_layer
                    elif visibility == "Tendance Linéaire": chart = trend_layer
                    else: chart = data_layer + trend_layer

                    st.altair_chart(chart, use_container_width=True)
                    st.dataframe(tab_final[tab_final["medecin"].isin(choix)].sort_values("CA Global", ascending=False)[["medecin", "CA Global", "CA 365j", "CA 90j", "Tendance"]], use_container_width=True, hide_index=True)
        except Exception as e: st.error(f"Erreur technique : {e}")
