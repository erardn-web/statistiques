import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import altair as alt

# --- CONFIGURATION PAGE WEB ---
st.set_page_config(page_title="Analyseur de Facturation Pro", layout="wide", page_icon="🏥")

# --- LOGIQUE MÉTIER ET FONCTIONS ---
MOTS_EXCLUSION = {"BERNOIS", "NEUCHATELOIS", "VALAISANS", "GENEVOIS", "VAUDOIS", "FRIBOURGEOIS"}
COULEURS_PROF = {"Physiothérapie": "#00CCFF", "Ergothérapie": "#FF9900", "Massage": "#00CC96", "Autre": "#AB63FA"}

def assigner_profession(code):
    """Logique métier pour le module Tarifs"""
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

# ==========================================
# 🏠 PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == "accueil":
    st.title("🏥 Assistant d'Analyse de Santé")
    st.markdown("---")
    st.write("### Choisissez le module d'analyse souhaité :")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("📊 **MODULE FACTURATION**")
        st.write("Liquidités, délais par assureur et retards.")
        if st.button("Accéder à la Facturation", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
            
    with col2:
        st.success("🩺 **MODULE MÉDECINS**")
        st.write("CA par médecin, tendances et fusion des noms.")
        if st.button("Accéder aux Médecins", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()

    with col3:
        st.warning("🏷️ **MODULE TARIFS**")
        st.write("Revenus mensuels par métier (Physio, Ergo...).")
        if st.button("Accéder aux Tarifs", use_container_width=True):
            st.session_state.page = "tarifs"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("📊 Analyse de la Facturation")
    uploaded_file = st.sidebar.file_uploader("Fichier Excel (.xlsx)", type="xlsx", key="fact_file")

    if uploaded_file:
        try:
            df_brut = pd.read_excel(uploaded_file, header=0)
            st.sidebar.header("🔍 Filtres")
            fournisseurs = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_fourn = st.sidebar.multiselect("Fournisseurs :", fournisseurs, default=fournisseurs)
            
            df = df_brut[df_brut.iloc[:, 9].isin(sel_fourn)].copy()
            df = df.rename(columns={
                df.columns[2]: "date_facture", df.columns[8]: "assureur", 
                df.columns[9]: "fournisseur", df.columns[12]: "statut", 
                df.columns[13]: "montant", df.columns[15]: "date_paiement"
            })
            
            df["date_facture"] = df["date_facture"].apply(convertir_date)
            df["date_paiement"] = df["date_paiement"].apply(convertir_date)
            df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
            ajd = pd.Timestamp(datetime.today().date())
            
            f_att = df[df["statut"].astype(str).str.lower().str.contains("en attente")].copy()
            f_att["delai_actuel"] = (ajd - f_att["date_facture"]).dt.days
            
            st.metric("💰 TOTAL BRUT EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")

            t1, t2 = st.tabs(["💰 Liquidités", "🕒 Délais"])
            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days

            with t1:
                horizons = [10, 20, 30]
                liq, probas = calculer_liquidites_fournisseur(f_att, p_hist, horizons)
                st.table(pd.DataFrame({
                    "Horizon": [f"Sous {h}j" for h in horizons],
                    "Estimation (CHF)": [f"{round(liq[h]):,}" for h in horizons],
                    "Probabilité": [f"{round(probas[h]*100)}%" for h in horizons]
                }))
            with t2:
                stats = p_hist.groupby("assureur")["delai"].agg(['mean', 'median']).reset_index()
                st.dataframe(stats.sort_values("mean", ascending=False), use_container_width=True)
        except Exception as e: st.error(f"Erreur Facturation : {e}")

# ==========================================
# 🩺 MODULE MÉDECINS
# ==========================================
elif st.session_state.page == "medecins":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.header("👨‍⚕️ Performance Médecins")
    uploaded_file = st.sidebar.file_uploader("Fichier Excel (.xlsx)", type="xlsx", key="med_up")

    if uploaded_file:
        try:
            df_m = pd.read_excel(uploaded_file, header=0)
            
            # Moteur de fusion simplifié
            noms_originaux = df_m.iloc[:, 7].dropna().unique()
            mapping = {}
            for n in noms_originaux:
                # Logique simplifiée : on pourrait remettre ton moteur complet ici
                mapping[n] = n 

            df_m.iloc[:, 7] = df_m.iloc[:, 7].replace(mapping)
            df_m["medecin"] = df_m.iloc[:, 7]
            df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
            
            ca_total = df_m.groupby("medecin")["ca"].sum().sort_values(ascending=False).reset_index()
            
            chart = alt.Chart(ca_total.head(15)).mark_bar().encode(
                x=alt.X('ca:Q', title="CA (CHF)"),
                y=alt.Y('medecin:N', sort='-x'),
                color='ca:Q'
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
            st.dataframe(ca_total, use_container_width=True)
        except Exception as e: st.error(f"Erreur Médecins : {e}")

# ==========================================
# 🏷️ MODULE TARIFS
# ==========================================
elif st.session_state.page == "tarifs":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()

    st.title("🏷️ Analyse par Métier et Prestations")
    uploaded_file = st.sidebar.file_uploader("Fichier Excel (Onglet 'Prestation')", type="xlsx", key="tarif_up")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, sheet_name='Prestation')
            nom_col_code = df.columns[2]   # C
            nom_col_somme = df.columns[11] # L
            date_cols = [c for c in df.columns if 'Date' in str(c)]
            nom_col_date = date_cols[0] if date_cols else df.columns[0]

            df[nom_col_somme] = pd.to_numeric(df[nom_col_somme], errors='coerce')
            df[nom_col_date] = pd.to_datetime(df[nom_col_date], errors='coerce')
            df = df[df[nom_col_somme] > 0].dropna(subset=[nom_col_date, nom_col_somme])
            df['Profession'] = df[nom_col_code].apply(assigner_profession)

            # Filtres
            st.sidebar.header("⚙️ Paramètres")
            inclure_mois = st.sidebar.toggle("Inclure le mois en cours", value=True)
            if not inclure_mois:
                df = df[df[nom_col_date] < datetime.now().replace(day=1, hour=0, minute=0)]

            profs = sorted(df['Profession'].unique())
            sel_profs = [p for p in profs if st.sidebar.checkbox(p, value=True, key=f"check_{p}")]
            
            df_filtered = df[df['Profession'].isin(sel_profs)].copy()
            df_filtered['Mois'] = df_filtered[nom_col_date].dt.to_period('M').dt.to_timestamp()
            
            df_plot = df_filtered.groupby(['Mois', 'Profession'])[nom_col_somme].sum().reset_index()

            fig = px.bar(df_plot, x='Mois', y=nom_col_somme, color='Profession', 
                         color_discrete_map=COULEURS_PROF, barmode='group', text_auto='.2f')
            
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_plot.sort_values('Mois', ascending=False), use_container_width=True)
            
        except Exception as e: st.error(f"Erreur Tarifs : {e}")
