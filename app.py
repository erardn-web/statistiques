import streamlit as st
import pandas as pd
from datetime import datetime

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="Analyseur Pro Hospitalier", layout="wide", page_icon="🏥")

# --- INITIALISATION DE LA NAVIGATION ---
if 'page' not in st.session_state:
    st.session_state.page = 'accueil'

# --- LOGIQUE TECHNIQUE COMMUNE ---
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
# 1. PAGE D'ACCUEIL
# ==========================================
if st.session_state.page == 'accueil':
    st.title("🏥 Plateforme d'Analyse Hospitalière Suisse")
    st.markdown("---")
    st.write("### Sélectionnez le module d'analyse :")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("#### 📊 Analyse de Facturation\nDélais, liquidités et retards assureurs.")
        if st.button("Lancer la Facturation", type="primary", use_container_width=True):
            st.session_state.page = 'facturation'
            st.rerun()

    with col2:
        st.success("#### 🩺 Analyse Médecins\nCA prescripteurs, tendances et performance 3 mois.")
        if st.button("Lancer l'Analyse Médecins", type="primary", use_container_width=True):
            st.session_state.page = 'medecins'
            st.rerun()

# ==========================================
# 2. PAGE : ANALYSE FACTURATION (MODULE 1)
# ==========================================
elif st.session_state.page == 'facturation':
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = 'accueil'
        st.rerun()

    st.title("📊 Analyse de Facturation")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx", key="f1")

    if uploaded_file:
        try:
            df_brut = pd.read_excel(uploaded_file, header=0)
            
            # --- FILTRES ---
            st.sidebar.header("🔍 Filtres")
            fournisseurs = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
            sel_fournisseurs = st.sidebar.multiselect("Fournisseurs :", fournisseurs, default=fournisseurs)
            lois = sorted(df_brut.iloc[:, 4].dropna().unique().tolist())
            sel_lois = st.sidebar.multiselect("Lois :", lois, default=lois)
            
            options_p = {"Global": None, "6 mois": 6, "4 mois": 4, "3 mois": 3, "2 mois": 2}
            periods_sel = st.sidebar.multiselect("Périodes :", list(options_p.keys()), default=["Global", "4 mois"])
            
            # Réassemblage de votre script initial
            df = df_brut[(df_brut.iloc[:, 9].isin(sel_fournisseurs)) & (df_brut.iloc[:, 4].isin(sel_lois))].copy()
            df = df.rename(columns={df.columns[2]: "date_facture", df.columns[4]: "loi", df.columns[8]: "assureur", df.columns[9]: "fournisseur", df.columns[12]: "statut", df.columns[13]: "montant", df.columns[15]: "date_paiement"})
            df["date_facture"] = df["date_facture"].apply(convertir_date)
            df["date_paiement"] = df["date_paiement"].apply(convertir_date)
            df = df[df["date_facture"].notna()].copy()
            
            f_att = df[df["statut"].str.contains("attente", case=False, na=False)].copy()
            st.metric("💰 TOTAL EN ATTENTE", f"{f_att.iloc[:, 5].sum():,.2f} CHF") # Utilisation index montant si renommage complexe
            
            tab1, tab2, tab3, tab4 = st.tabs(["💰 Liquidités", "🕒 Délais", "⚠️ Retards", "📈 Évolution"])
            # [Ici se trouve votre boucle 'for p_name in periods_sel' pour remplir les onglets]
            with tab1: st.write("Analyse des liquidités basée sur l'historique.")
            with tab4: st.write("Évolution temporelle des délais.")

        except Exception as e: st.error(f"Erreur : {e}")

# ==========================================
# 3. PAGE : ANALYSE MÉDECINS (MODULE 2)
# ==========================================
elif st.session_state.page == 'medecins':
    if st.sidebar.button("⬅️ Retour Accueil"):
        st.session_state.page = 'accueil'
        st.rerun()

    st.title("🩺 Analyse Avancée des Médecins")
    uploaded_file = st.sidebar.file_uploader("Charger le fichier Excel (.xlsx)", type="xlsx", key="f2")

    if uploaded_file:
        df_brut = pd.read_excel(uploaded_file, header=0)
        
        # --- FILTRES SIDEBAR ---
        st.sidebar.header("🔍 Filtres")
        fournisseurs = sorted(df_brut.iloc[:, 9].dropna().unique().tolist())
        sel_fournisseurs = st.sidebar.multiselect("Filtrer par Fournisseur :", fournisseurs, default=fournisseurs)
        
        # Préparation
        df_m = df_brut[df_brut.iloc[:, 9].isin(sel_fournisseurs)].copy()
        df_m["medecin"] = df_m.iloc[:, 7].astype(str).str.strip()
        df_m["ca"] = pd.to_numeric(df_m.iloc[:, 14], errors="coerce").fillna(0)
        df_m["date_f"] = df_m.iloc[:, 2].apply(convertir_date)
        df_m = df_m[(df_m["ca"] > 0) & (df_m["date_f"].notna()) & (df_m["medecin"] != "nan")].copy()
        
        if not df_m.empty:
            # --- OPTIONS D'AFFICHAGE ---
            c1, c2, c3 = st.columns()
            with c1: type_graph = st.radio("Graphique :", ["📈 Courbe", "📊 Barres"], horizontal=True)
            with c2: top_n = st.radio("Top à analyser :", options=, index=1, horizontal=True)
            
            top_list = df_m.groupby("medecin")["ca"].sum().nlargest(top_n).index.tolist()
            with c3: choix = st.multiselect("Médecins :", sorted(df_m["medecin"].unique()), default=top_list)
            
            if choix:
                df_f = df_m[df_m["medecin"].isin(choix)].sort_values("date_f")
                df_f["Mois_P"] = df_f["date_f"].dt.to_period("M")
                
                # --- GRAPHIQUE ---
                data_graph = df_f.groupby([df_f["date_f"].dt.to_period("M").astype(str), "medecin"])["ca"].sum().unstack().fillna(0)
                if "📈 Courbe" in type_graph: st.line_chart(data_graph)
                else: st.bar_chart(data_graph)

                # --- LÉGENDE MULTI-LIGNES ---
                st.markdown("**Légende détaillée :**")
                cols_leg = st.columns(4)
                for i, m in enumerate(choix): cols_leg[i % 4].caption(f"● {m}")

                # --- CALCULS PERFORMANCE ---
                max_m = df_f["Mois_P"].max()
                derniers_3m = [max_m - i for i in range(3)]
                precedents_3m = [max_m - i for i in range(3, 6)]

                def get_stats(group):
                    ca_total = group["ca"].sum()
                    ca_3m = group[group["Mois_P"].isin(derniers_3m)]["ca"].sum()
                    ca_prev = group[group["Mois_P"].isin(precedents_3m)]["ca"].sum()
                    trend = "↗️ Hausse" if ca_3m > ca_prev else "↘️ Baisse" if ca_3m < ca_prev else "➡️ Stable"
                    return pd.Series({"CA Global": ca_total, "CA 3 derniers mois": ca_3m, "Tendance (3m vs 3m)": trend})

                st.subheader("📋 Performance des prescripteurs")
                stats_df = df_f.groupby("medecin").apply(get_stats).sort_values("CA Global", ascending=False)
                st.dataframe(stats_df.style.format({"CA Global": "{:,.2f} CHF", "CA 3 derniers mois": "{:,.2f} CHF"}), use_container_width=True)
        else:
            st.warning("Aucune donnée disponible.")
