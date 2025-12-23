import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor 
import importlib
import relatorio

importlib.reload(motor)
importlib.reload(relatorio)

# --- CONFIGURAÇÃO ---
st.set_page_config(
    page_title="cClass Auditor AI",
    page_icon="🟧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTADO (SESSION STATE) ---
if 'xml_vendas_df' not in st.session_state: st.session_state.xml_vendas_df = pd.DataFrame()
if 'xml_compras_df' not in st.session_state: st.session_state.xml_compras_df = pd.DataFrame()
if 'sped_vendas_df' not in st.session_state: st.session_state.sped_vendas_df = pd.DataFrame()
if 'sped_compras_df' not in st.session_state: st.session_state.sped_compras_df = pd.DataFrame()
if 'empresa_nome' not in st.session_state: st.session_state.empresa_nome = "Nenhuma Empresa"
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

def reset_all():
    st.session_state.xml_vendas_df = pd.DataFrame()
    st.session_state.xml_compras_df = pd.DataFrame()
    st.session_state.sped_vendas_df = pd.DataFrame()
    st.session_state.sped_compras_df = pd.DataFrame()
    st.session_state.empresa_nome = "Nenhuma Empresa"
    st.session_state.uploader_key += 1

# --- CSS (VISUAL NASCEL PREMIUM) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .stApp { background-color: #F8F9FA; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E0E0E0; }
    
    .header-container {
        background: linear-gradient(135deg, #E67E22 0%, #D35400 100%);
        padding: 25px;
        border-radius: 12px;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(230, 126, 34, 0.2);
        color: white;
    }
    .main-header { font-size: 2.2rem; font-weight: 800; color: #FFFFFF; margin: 0; letter-spacing: -1px; }
    .sub-header { font-size: 1rem; color: #FDEBD0; margin-top: 5px; opacity: 0.9; }
    
    /* Barra de Progresso Laranja */
    .stProgress > div > div > div > div { background-color: #E67E22; }

    /* Métricas */
    div[data-testid="stMetric"] { 
        background-color: #FFFFFF !important; 
        border: 1px solid #E0E0E0; 
        border-radius: 10px; 
        padding: 15px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border-top: 4px solid #E67E22; 
    }
    
    /* Botões */
    div.stButton > button[kind="primary"] { background-color: #E67E22 !important; color: white !important; border: none; font-weight: 600; transition: all 0.3s ease; }
    div.stButton > button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(230, 126, 34, 0.3); }
    
    .streamlit-expanderHeader { font-weight: 600; color: #34495E; background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 5px; }
    
    /* Box Sucesso */
    .file-success {
        background-color: #D5F5E3; color: #196F3D; padding: 10px; border-radius: 5px;
        border: 1px solid #ABEBC6; margin-top: 5px; margin-bottom: 10px; font-weight: 600; text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CACHE ---
@st.cache_data
def carregar_bases(): return motor.carregar_base_legal(), motor.carregar_json_regras()
@st.cache_data
def carregar_tipi_cache(file): return motor.carregar_tipi(file)

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3029/3029337.png", width=50)
    if st.session_state.empresa_nome != "Nenhuma Empresa":
        st.markdown(f"### 🏢 {st.session_state.empresa_nome}")
        qtd_xml = len(st.session_state.xml_vendas_df) + len(st.session_state.xml_compras_df)
        qtd_sped = len(st.session_state.sped_vendas_df) + len(st.session_state.sped_compras_df)
        
        if qtd_xml > 0 and qtd_sped > 0: st.success(f"⚔️ Modo Cruzamento\nXML: {qtd_xml} | SPED: {qtd_sped}")
        elif qtd_xml > 0: st.info(f"📄 XML Carregado\n({qtd_xml} itens)")
        elif qtd_sped > 0: st.warning(f"📝 SPED Carregado\n({qtd_sped} itens)")
    else:
        st.markdown("### 🔍 Auditoria Fiscal")
        st.caption("Aguardando Arquivos...")
    
    st.divider()
    c1, c2 = st.columns(2)
    with c1: aliq_ibs = st.number_input("IBS (%)", 0.0, 50.0, 17.7, 0.1)
    with c2: aliq_cbs = st.number_input("CBS (%)", 0.0, 50.0, 8.8, 0.1)
    
    with st.expander("📂 Atualizar TIPI"):
        uploaded_tipi = st.file_uploader("TIPI", type=['xlsx', 'csv'])
        if st.button("🔄 Recarregar"):
            carregar_bases.clear()
            st.rerun()
            
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR TUDO", type="secondary"):
        reset_all()
        st.rerun()

    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- HEADER ---
st.markdown("""
<div class="header-container">
    <div class="main-header">cClass Auditor AI </div>
    <div class="sub-header">Auditoria de Conformidade e Cruzamento XML vs SPED | Powered by Nascel</div>
</div>
""", unsafe_allow_html=True)

ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

def processar_arquivos_com_barra(arquivos, tipo):
    lista = []
    total = len(arquivos)
    barra = st.progress(0, text=f"⏳ Lendo {total} arquivos...")
    for i, arquivo in enumerate(arquivos):
        progresso = (i + 1) / total
        barra.progress(progresso, text=f"Lendo {i+1}/{total}: {arquivo.name}")
        try:
            tree = ET.parse(arquivo)
            if tipo == 'SAIDA' and st.session_state.empresa_nome == "Nenhuma Empresa":
                st.session_state.empresa_nome = motor.extrair_nome_empresa_xml(tree, ns)
            lista.extend(motor.processar_xml_detalhado(tree, ns, tipo))
        except: continue
    barra.empty()
    return lista

# --- UPLOAD ---
st.markdown("### 📂 Central de Arquivos")
c_xml, c_sped = st.columns(2)

with c_xml:
    with st.expander("📄 Carregar XMLs (Notas Fiscais)", expanded=True):
        vendas_files = st.file_uploader("XML Vendas", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}", label_visibility="collapsed")
        if vendas_files: st.markdown(f'<div class="file-success">✅ {len(vendas_files)} XMLs Venda</div>', unsafe_allow_html=True)
        
        compras_files = st.file_uploader("XML Compras", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}", label_visibility="collapsed")
        if compras_files: st.markdown(f'<div class="file-success">✅ {len(compras_files)} XMLs Compra</div>', unsafe_allow_html=True)

        if vendas_files and st.session_state.xml_vendas_df.empty:
            st.session_state.xml_vendas_df = pd.DataFrame(processar_arquivos_com_barra(vendas_files, 'SAIDA'))
            st.rerun()
        if compras_files and st.session_state.xml_compras_df.empty:
            st.session_state.xml_compras_df = pd.DataFrame(processar_arquivos_com_barra(compras_files, 'ENTRADA'))
            st.rerun()

with c_sped:
    with st.expander("📝 Carregar SPED Fiscal", expanded=True):
        sped_file = st.file_uploader("SPED TXT", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}", label_visibility="collapsed")
        if sped_file: st.markdown(f'<div class="file-success">✅ SPED Pronto</div>', unsafe_allow_html=True)
        
        if sped_file and st.session_state.sped_vendas_df.empty:
            with st.spinner("Processando SPED..."):
                nome, vendas, compras = motor.processar_sped_fiscal(sped_file)
                st.session_state.empresa_nome = nome
                st.session_state.sped_vendas_df = pd.DataFrame(vendas)
                st.session_state.sped_compras_df = pd.DataFrame(compras)
                st.rerun()

# --- AUDITORIA ---
def auditar_df(df):
    if df.empty: return df
    res = df.apply(lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliq_ibs/100, aliq_cbs/100), axis=1, result_type='expand')
    df[['cClassTrib', 'DescRegra', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada', 'vIBS', 'vCBS']] = res
    return df

df_xml_v = auditar_df(st.session_state.xml_vendas_df.copy())
df_xml_c = auditar_df(st.session_state.xml_compras_df.copy())
df_sped_v = auditar_df(st.session_state.sped_vendas_df.copy())
df_sped_c = auditar_df(st.session_state.sped_compras_df.copy())

df_final_v = df_xml_v if not df_xml_v.empty else df_sped_v
df_final_c = df_xml_c if not df_xml_c.empty else df_sped_c

tem_dados = not df_final_v.empty or not df_final_c.empty

if tem_dados:
    cols_ordenadas = ['Cód. Produto', 'Descrição Produto', 'NCM', 'CFOP', 'Novo CST', 'cClassTrib', 'DescRegra', 'Valor', 'vICMS', 'vPIS', 'vCOFINS', 'Carga Atual', 'vIBS', 'vCBS', 'Carga Projetada', 'Validação TIPI']
    def preparar_exibicao(df):
        if df.empty: return df
        return df.rename(columns={'Produto': 'Descrição Produto'})[cols_ordenadas]

    st.markdown("---")
    
    abas = ["💎 Oportunidades & Riscos", "📊 Dashboard", "⚖️ Simulação", "📤 Saídas", "📥 Entradas"]
    tem_cruzamento = (not df_xml_v.empty or not df_xml_c.empty) and (not df_sped_v.empty or not df_sped_c.empty)
    if tem_cruzamento: abas.insert(0, "⚔️ Cruzamento XML x SPED")
        
    tabs = st.tabs(abas)
    
    # --- ABA 0: CRUZAMENTO ---
    if tem_cruzamento:
        with tabs[0]:
            st.markdown("### ⚔️ Auditoria Cruzada")
            xml_v_group = df_xml_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor': 'Valor_XML'}) if not df_xml_v.empty else pd.DataFrame()
            sped_v_group = df_sped_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor': 'Valor_SPED'}) if not df_sped_v.empty else pd.DataFrame()
            
            cruzamento = pd.merge(xml_v_group, sped_v_group, on='Chave NFe', how='outer', indicator=True)
            so_xml = cruzamento[cruzamento['_merge'] == 'left_only']
            divergentes = cruzamento[(cruzamento['_merge'] == 'both') & (abs(cruzamento['Valor_XML'] - cruzamento['Valor_SPED']) > 0.01)]
            
            k1, k2 = st.columns(2)
            k1.metric("Omissão no SPED", len(so_xml), delta="Risco Alto", delta_color="inverse")
            k2.metric("Divergência de Valor", len(divergentes), delta="Erro Valor", delta_color="inverse")
            
            if not so_xml.empty: st.error("🚨 Notas não escrituradas no SPED:"); st.dataframe(so_xml)
            if not divergentes.empty: st.warning("⚠️ Notas com valor diferente:"); st.dataframe(divergentes)
            if so_xml.empty and divergentes.empty: st.success("✅ Cruzamento XML x SPED 100% Ok!")

    # --- ABA 1: OPORTUNIDADES ---
    idx_oport = 1 if tem_cruzamento else 0
    idx_dash = 2 if tem_cruzamento else 1
    idx_sim = 3 if tem_cruzamento else 2
    idx_sai = 4 if tem_cruzamento else 3
    idx_ent = 5 if tem_cruzamento else 4

    with tabs[idx_oport]:
        st.markdown("### 💎 Análise de Inteligência Fiscal")
        st.caption("Identificação automática de pagamentos indevidos (oportunidades) e passivos ocultos (riscos).")
        
        if not df_final_v.empty:
            oportunidades = df_final_v[
                (df_final_v['Carga Atual'] > 0) & 
                (df_final_v['Status'].str.contains("ZERO") | df_final_v['Status'].str.contains("REDUZIDA"))
            ].copy()
            
            oportunidades['Potencial Recuperação'] = oportunidades['Carga Atual'] - oportunidades['Carga Projetada']
            total_recup = oportunidades['Potencial Recuperação'].sum()
            
            riscos = df_final_v[
                (df_final_v['Carga Atual'] == 0) & 
                (df_final_v['Status'] == "PADRAO")
            ].copy()
            total_risco = riscos['Carga Projetada'].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("💰 Potencial de Recuperação", f"R$ {total_recup:,.2f}", delta="Crédito Possível", delta_color="normal")
            c2.metric("⚠️ Risco Fiscal Detectado", f"R$ {total_risco:,.2f}", delta="Passivo Oculto", delta_color="inverse")
            
            st.divider()
            
            if not oportunidades.empty:
                st.success(f"**Encontramos {len(oportunidades)} itens com tributação maior que a necessária:**")
                st.dataframe(oportunidades[['Cód. Produto', 'Descrição Produto', 'NCM', 'Carga Atual', 'DescRegra', 'Potencial Recuperação']], use_container_width=True)
            else: st.info("Nenhuma oportunidade óbvia de recuperação encontrada.")
                
            if not riscos.empty:
                st.error(f"**Atenção: {len(riscos)} itens saíram zerados mas não encontramos base legal para isso:**")
                st.dataframe(riscos[['Cód. Produto', 'Descrição Produto', 'NCM', 'Carga Atual', 'DescRegra']], use_container_width=True)

    # --- ABA DASHBOARD ---
    with tabs[idx_dash]:
        st.markdown("### Visão Geral")
        deb = df_final_v['Carga Projetada'].sum() if not df_final_v.empty else 0
        cred = df_final_c['Carga Projetada'].sum() if not df_final_c.empty else 0
        saldo = deb - cred
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Débitos (Saídas)", f"R$ {deb:,.2f}")
        k2.metric("Créditos (Entradas)", f"R$ {cred:,.2f}")
        k3.metric("Saldo Estimado", f"R$ {abs(saldo):,.2f}", delta="A Pagar" if saldo>0 else "Credor", delta_color="inverse")
        
        if not df_final_v.empty:
            st.markdown("#### Top 5 Produtos (Carga Tributária)")
            top = df_final_v.groupby('Produto')['Carga Projetada'].sum().nlargest(5).reset_index().sort_values('Carga Projetada')
            # CORREÇÃO: Removido 'color=' para evitar erro
            st.bar_chart(top, x="Carga Projetada", y="Produto", horizontal=True)

    # --- ABA SIMULAÇÃO ---
    with tabs[idx_sim]:
        st.markdown("### Comparativo: Atual vs Reforma")
        t_atual = df_final_v['Carga Atual'].sum() if not df_final_v.empty else 0
        t_novo = df_final_v['Carga Projetada'].sum() if not df_final_v.empty else 0
        delta = t_novo - t_atual
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Carga Atual", f"R$ {t_atual:,.2f}")
        c2.metric("Nova Carga", f"R$ {t_novo:,.2f}")
        c3.metric("Variação", f"R$ {abs(delta):,.2f}", delta="Aumento" if delta>0 else "Economia", delta_color="inverse")
        
        # CORREÇÃO: Removido 'color=' para evitar erro
        st.bar_chart(pd.DataFrame({'Cenário': ['Atual', 'Reforma'], 'Valor': [t_atual, t_novo]}), x='Cenário', y='Valor')

    # --- TABELAS ---
    col_cfg = {
        "Valor": st.column_config.ProgressColumn("Valor Base", format="R$ %.2f", min_value=0, max_value=1000),
        "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
        "Novo CST": st.column_config.TextColumn(width="small"),
        "Validação TIPI": st.column_config.TextColumn(width="medium"),
    }

    with tabs[idx_sai]:
        if not df_final_v.empty: st.dataframe(preparar_exibicao(df_final_v), use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.info("Sem dados.")
    with tabs[idx_ent]:
        if not df_final_c.empty: st.dataframe(preparar_exibicao(df_final_c), use_container_width=True, hide_index=True, column_config=col_cfg)
        else: st.info("Sem dados.")

    # --- EXPORTAR ---
    st.markdown("---")
    st.markdown("### 📥 Exportar Relatórios")
    c1, c2 = st.columns(2)
    with c1:
        if not df_final_v.empty:
            try:
                pdf = relatorio.gerar_pdf_bytes(st.session_state.empresa_nome, df_final_v, df_final_c)
                st.download_button("📄 BAIXAR LAUDO PDF", pdf, "Laudo.pdf", "application/pdf", use_container_width=True)
            except: st.error("Erro PDF")
    with c2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            if not df_final_v.empty: preparar_exibicao(df_final_v).to_excel(writer, sheet_name="Vendas", index=False)
            if not df_final_c.empty: preparar_exibicao(df_final_c).to_excel(writer, sheet_name="Compras", index=False)
            if tem_cruzamento:
                if not so_xml.empty: so_xml.to_excel(writer, sheet_name="Omissao_SPED", index=False)
                if not divergentes.empty: divergentes.to_excel(writer, sheet_name="Divergencia_Valor", index=False)
            if 'oportunidades' in locals() and not oportunidades.empty: oportunidades.to_excel(writer, sheet_name="Recuperacao_Credito", index=False)
        st.download_button("📊 BAIXAR EXCEL COMPLETO", buf, "Auditoria.xlsx", "primary", use_container_width=True)

else:
    st.info("👈 Utilize o menu lateral para carregar os arquivos.")