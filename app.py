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
        
        st.sidebar.header("📅 3. Actions")
        col_b1, col_b2 = st.sidebar.columns(2)
        if col_b1.button("🚀 Analyser", type="primary", use_container_width=True):
            st.session_state.analyse_lancee = True
            st.session_state.calcul_medecin_lance = False
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

            if st.session_state.analyse_lancee:
                tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
                # Logique simplifiée pour l'exemple (identique à vos onglets)
                with tab4:
                    st.subheader("📈 Évolution temporelle")
                    if not df[df["date_paiement"].notna()].empty:
                        p_hist = df[df["date_paiement"].notna()].copy()
                        p_hist["mois"] = p_hist["date_facture"].dt.to_period("M").astype(str)
                        st.line_chart(p_hist.groupby("mois")["montant"].sum())

        # --- NOUVELLE FONCTIONNALITÉ MÉDECINS (FUSION PAR MOTS UNIFIÉS) ---
        if st.session_state.calcul_medecin_lance:
            st.header("👨‍⚕️ Analyse du Chiffre d'Affaires par Médecin")
            if st.button("⬅️ Retour"): st.session_state.calcul_medecin_lance = False; st.rerun()

            def extraire_mot_cle(nom):
                """Garde le mot le plus long (nom de famille ou institution)."""
                if pd.isna(nom) or str(nom).strip() == "": return ""
                n = re.sub(r'[^A-Z]', ' ', str(nom).upper())
                mots = [m.strip() for m in n.split() if len(m.strip()) >= 4]
                # On exclut les titres communs
                parasites = {'DOCTEUR', 'HOSPITALIER', 'CENTRE', 'MEDECIN', 'SERVICE', 'NEUCHATELOIS'}
                mots_filtres = [m for m in mots if m not in parasites]
                # On retourne le mot le plus long comme 'clé' de fusion
                return max(mots_filtres, key=len) if mots_filtres else (mots[0] if mots else "")

            df_m = df_brut.copy()
            df_m["med_brut"] = df_m.iloc[:, 7].astype(str).str.strip()
            df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
            df_m["dt"] = df_m.iloc[:, 2].apply(convertir_date)
            
            # Fusion : on groupe par le mot-clé principal (ex: LOZANO ou NEUCHATELOIS)
            df_m["cle_fusion"] = df_m["med_brut"].apply(extraire_mot_cle)
            df_m = df_m[(df_m["ca"] > 0) & (df_m["dt"].notna()) & (df_m["cle_fusion"] != "")].copy()
            
            if not df_m.empty:
                # Création du nom d'affichage (le plus court pour être concis, ex: 'LOZANO Juan')
                noms_groupes = df_m.groupby("cle_fusion")["med_brut"].agg(lambda x: min(x, key=len)).to_dict()
                df_m["affichage"] = df_m["cle_fusion"].map(noms_groupes)
                
                choix = st.multiselect("🎯 Sélectionner les prescripteurs :", options=sorted(df_m["affichage"].unique()), default=df_m.groupby("affichage")["ca"].sum().nlargest(10).index.tolist())
                
                if choix:
                    df_f = df_m[df_m["affichage"].isin(choix)].sort_values("dt")
                    df_f["Mois"] = df_f["dt"].dt.to_period("M").astype(str)
                    st.line_chart(df_f.groupby(["Mois", "affichage"])["ca"].sum().unstack().fillna(0))
                    
                    st.subheader("💰 CA Cumulé (CHF)")
                    st.table(df_f.groupby("affichage")["ca"].sum().sort_values(ascending=False).apply(lambda x: f"{x:,.2f} CHF"))

                    with st.expander("🔍 Voir le détail du regroupement"):
                        st.write(df_m.groupby("affichage")["med_brut"].unique().reset_index())
            else:
                st.warning("Aucune donnée avec paiement > 0 trouvée.")

    except Exception as e: st.error(f"Erreur : {e}")
else: st.info("👋 Chargez un fichier Excel.")
