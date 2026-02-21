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
    st.title("🏥 Assistant d'Analyse de Santé")
    st.markdown("---")
    st.write("### Choisissez le module d'analyse souhaité :")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info("📊 **MODULE FACTURATION**")
        if st.button("Accéder à la Facturation", key="btn_fact", use_container_width=True):
            st.session_state.page = "factures"
            st.rerun()
    with col2:
        st.success("🩺 **MODULE MÉDECINS**")
        if st.button("Accéder aux Médecins", key="btn_med", use_container_width=True):
            st.session_state.page = "medecins"
            st.rerun()
    with col3:
        st.warning("🏷️ **MODULE TARIFS**")
        if st.button("Accéder aux Tarifs", key="btn_tarif", use_container_width=True):
            st.session_state.page = "tarifs"
            st.rerun()
    with col4:
        st.info("🏦 **BILAN COMPTABLE**")
        if st.button("Accéder au Bilan", key="btn_bilan", use_container_width=True, type="primary"):
            st.session_state.page = "bilan"
            st.rerun()

# ==========================================
# 📊 MODULE FACTURES
# ==========================================
elif st.session_state.page == "factures":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()
    st.title("📊 Analyse de la Facturation")
    up_f = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="f_up")
    if up_f:
        try:
            df_brut = pd.read_excel(up_f, header=0)
            fourn = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_f = st.sidebar.multiselect("Fournisseurs :", fourn, default=fourn)
            df = df_brut[df_brut.iloc[:, 9].isin(sel_f)].copy()
            df = df.rename(columns={df.columns[2]: "date_facture", df.columns[8]: "assureur", 
                                    df.columns[9]: "fournisseur", df.columns[12]: "statut", 
                                    df.columns[13]: "montant", df.columns[15]: "date_paiement"})
            df["date_facture"] = df["date_facture"].apply(convertir_date)
            df["date_paiement"] = df["date_paiement"].apply(convertir_date)
            df["montant"] = pd.to_numeric(df["montant"], errors="coerce").fillna(0)
            ajd = pd.Timestamp(datetime.today().date())
            f_att = df[df["statut"].astype(str).str.lower().str.contains("attente")].copy()
            st.metric("💰 EN ATTENTE", f"{f_att['montant'].sum():,.2f} CHF")
            
            p_hist = df[df["date_paiement"].notna()].copy()
            p_hist["delai"] = (p_hist["date_paiement"] - p_hist["date_facture"]).dt.days
            if not p_hist.empty:
                st.subheader("🕒 Délais moyens par assureur")
                stats = p_hist.groupby("assureur")["delai"].mean().reset_index()
                st.dataframe(stats.sort_values("delai", ascending=False))
        except Exception as e: st.error(f"Erreur : {e}")

# ==========================================
# 🩺 MODULE MÉDECINS (RÉPARÉ LIGNE 261)
# ==========================================
elif st.session_state.page == "medecins":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()
    st.header("👨‍⚕️ Performance Médecins")
    up_m = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="m_up")
    if up_m:
        try:
            df_brut = pd.read_excel(up_m, header=0)
            df_m_init = df_brut.copy()
            df_m_init["medecin"] = df_m_init.iloc[:, 7]
            df_m_init["ca"] = pd.to_numeric(df_m_init.iloc[:, 14], errors="coerce").fillna(0)
            df_m_init["date_f"] = df_m_init.iloc[:, 2].apply(convertir_date)
            # REPARATION LIGNE 261 : Parenthèse fermée proprement
            df_m = df_m_init[(df_m_init["ca"] > 0) & (df_m_init["date_f"].notna()) & (df_m_init["medecin"].notna())].copy()
            
            if not df_m.empty:
                stats_ca = df_m.groupby("medecin")["ca"].sum().reset_index().sort_values("ca", ascending=False)
                st.subheader("Top Médecins par CA")
                fig_m = px.bar(stats_ca.head(15), x='medecin', y='ca', title="Top 15 Médecins")
                st.plotly_chart(fig_m, use_container_width=True)
                st.dataframe(stats_ca)
        except Exception as e: st.error(f"Erreur Médecins : {e}")

# ==========================================
# 🏷️ MODULE TARIFS (VOTRE NOUVELLE LOGIQUE)
# ==========================================
elif st.session_state.page == "tarifs":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()
    st.title("📊 Analyse des revenus mensuels")
    up_t = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="t_up")
    if up_t:
        try:
            df = pd.read_excel(up_t, sheet_name='Prestation')
            nom_col_code = df.columns[2]
            nom_col_somme = df.columns[11]
            date_cols = [c for c in df.columns if 'Date' in str(c)]
            nom_col_date = date_cols[0] if date_cols else df.columns[0]
            df[nom_col_somme] = pd.to_numeric(df[nom_col_somme], errors='coerce')
            df[nom_col_date] = pd.to_datetime(df[nom_col_date], errors='coerce')
            df = df[df[nom_col_somme] > 0].dropna(subset=[nom_col_date, nom_col_somme])
            df['Profession'] = df[nom_col_code].apply(assigner_profession)
            
            prof_disp = sorted(df['Profession'].unique())
            metiers_actifs = [p for p in prof_disp if st.sidebar.checkbox(p, value=True, key=f"c_{p}")]
            codes_p = df[df['Profession'].isin(metiers_actifs)]
            liste_c = sorted(codes_p[nom_col_code].unique().astype(str))
            sel_c = st.sidebar.multiselect("Codes :", options=liste_c, default=liste_c)
            
            mode = st.radio("Affichage :", ["Profession", "Code tarifaire"], horizontal=True)
            style = st.radio("Style :", ["Barres", "Courbes"], horizontal=True)
            df_f = df[df[nom_col_code].astype(str).isin(sel_c)].copy()
            if not df_f.empty:
                df_f['Mois'] = df_f[nom_col_date].dt.to_period('M').dt.to_timestamp()
                target = "Profession" if mode == "Profession" else nom_col_code
                df_p = df_f.groupby(['Mois', target])[nom_col_somme].sum().reset_index()
                fig = px.bar(df_p, x='Mois', y=nom_col_somme, color=target, barmode='group') if style == "Barres" else px.line(df_p, x='Mois', y=nom_col_somme, color=target, markers=True)
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e: st.error(f"Erreur Tarifs : {e}")

# ==========================================
# 🏦 MODULE BILAN COMPTABLE
# ==========================================
elif st.session_state.page == "bilan":
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = "accueil"
        st.rerun()
    st.title("🏦 Bilan Comptable au 31 Décembre")
    up_b = st.sidebar.file_uploader("Fichier Excel", type="xlsx", key="b_up")
    if up_b:
        try:
            xl = pd.ExcelFile(up_b)
            ong_f = next((s for s in xl.sheet_names if 'Facture' in s), None)
            if 'Prestation' in xl.sheet_names and ong_f:
                df_p = pd.read_excel(up_b, sheet_name='Prestation')
                df_f = pd.read_excel(up_b, sheet_name=ong_f)
                ca = pd.to_numeric(df_p.iloc[:, 11], errors='coerce').sum()
                col_m = df_f.columns[14]
                df_f[col_m] = pd.to_numeric(df_f[col_m], errors='coerce').fillna(0)
                imp = df_f[df_f.iloc[:, 15].isna()][col_m].sum()
                st.metric("📈 CA Total", f"{ca:,.2f} CHF")
                st.metric("⏳ Total Impayés", f"{imp:,.2f} CHF")
        except Exception as e: st.error(f"Erreur Bilan : {e}")
