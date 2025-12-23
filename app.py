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
    
    .stProgress > div > div > div > div { background-color: #E67E22; }

    div[data-testid="stMetric"] { 
        background-color: #FFFFFF !important; 
        border: 1px solid #E0E0E0; 
        border-radius: 10px; 
        padding: 15px; 
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border-top: 4px solid #E67E22; 
    }
    
    div.stButton > button[kind="primary"] { background-color: #E67E22 !important; color: white !important; border: none; font-weight: 600; transition: all 0.3s ease; }
    div.stButton > button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(230, 126, 34, 0.3); }
    
    .streamlit-expanderHeader { font-weight: 600; color: #34495E; background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 5px; }
    
    /* Box de Sucesso Customizado (para os arquivos) */
    .file-success {
        background-color: #D5F5E3;
        color: #196F3D;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #ABEBC6;
        margin-top: 5px;
        margin-bottom: 10px;
        font-size: 0.9rem;
        text-align: center;
        font-weight: 600;
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
        
        if qtd_xml > 0 and qtd_sped > 0:
            st.success(f"⚔️ Modo Cruzamento\n\nXML: {qtd_xml} itens\nSPED: {qtd_sped} itens")
        elif qtd_xml > 0:
            st.info(f"📄 XML Carregado\n({qtd_xml} itens)")
        elif qtd_sped > 0:
            st.warning(f"📝 SPED Carregado\n({qtd_sped} itens)")

    else:
        st.markdown("### 🔍 Auditoria Fiscal")
        st.caption("Aguardando Arquivos...")
    
    st.divider()
    st.markdown("#### ⚙️ Parâmetros Fiscais")
    c1, c2 = st.columns(2)
    with c1: aliq_ibs = st.number_input("IBS (%)", 0.0, 50.0, 17.7, 0.1)
    with c2: aliq_cbs = st.number_input("CBS (%)", 0.0, 50.0, 8.8, 0.1)
    with st.expander("📂 Atualizar Tabela TIPI"):
        uploaded_tipi = st.file_uploader("TIPI (.xlsx)", type=['xlsx', 'csv'])
        if st.button("🔄 Recarregar Motor"):
            carregar_bases.clear()
            st.rerun()
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR AUDITORIA", type="secondary"):
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
    barra = st.progress(0, text=f"⏳ Iniciando leitura de {total} arquivos...")
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

# === ÁREA DE UPLOAD UNIFICADA (COM O CONTADOR DE VOLTA!) ===
st.markdown("### 📂 Central de Arquivos (Carregue XML e/ou SPED)")
c_xml, c_sped = st.columns(2)

with c_xml:
    with st.expander("📄 Carregar XMLs (Notas Fiscais)", expanded=True):
        st.markdown("**Saídas (Vendas):**")
        vendas_files = st.file_uploader("Upload Vendas", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}", label_visibility="collapsed")
        
        # --- AQUI ESTÁ ELE DE VOLTA ---
        if vendas_files:
            st.markdown(f'<div class="file-success">✅ {len(vendas_files)} XMLs de Saída Selecionados</div>', unsafe_allow_html=True)
        # ------------------------------

        st.markdown("**Entradas (Compras):**")
        compras_files = st.file_uploader("Upload Compras", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}", label_visibility="collapsed")
        
        # --- AQUI TAMBÉM ---
        if compras_files:
            st.markdown(f'<div class="file-success">✅ {len(compras_files)} XMLs de Entrada Selecionados</div>', unsafe_allow_html=True)
        # -------------------
        
        if vendas_files and st.session_state.xml_vendas_df.empty:
            st.session_state.xml_vendas_df = pd.DataFrame(processar_arquivos_com_barra(vendas_files, 'SAIDA'))
            st.rerun()
        if compras_files and st.session_state.xml_compras_df.empty:
            st.session_state.xml_compras_df = pd.DataFrame(processar_arquivos_com_barra(compras_files, 'ENTRADA'))
            st.rerun()

with c_sped:
    with st.expander("📝 Carregar SPED Fiscal (TXT)", expanded=True):
        sped_file = st.file_uploader("Arquivo SPED", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}", label_visibility="collapsed")
        
        # --- FEEDBACK DO SPED TAMBÉM ---
        if sped_file:
            st.markdown(f'<div class="file-success">✅ Arquivo SPED Pronto</div>', unsafe_allow_html=True)
        # -------------------------------
        
        if sped_file and st.session_state.sped_vendas_df.empty:
            with st.spinner("Lendo SPED..."):
                nome, vendas, compras = motor.processar_sped_fiscal(sped_file)
                st.session_state.empresa_nome = nome
                st.session_state.sped_vendas_df = pd.DataFrame(vendas)
                st.session_state.sped_compras_df = pd.DataFrame(compras)
                st.rerun()

# === LÓGICA DE AUDITORIA ===
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
    
    # SELECIONA ABAS
    abas = ["📊 Dashboard Financeiro", "⚖️ Simulação Reforma", "📤 Saídas", "📥 Entradas"]
    tem_cruzamento = (not df_xml_v.empty or not df_xml_c.empty) and (not df_sped_v.empty or not df_sped_c.empty)
    if tem_cruzamento: abas.insert(0, "⚔️ Cruzamento XML x SPED")
        
    tabs = st.tabs(abas)

    # --- ABA CRUZAMENTO ---
    if tem_cruzamento:
        with tabs[0]:
            st.markdown("### ⚔️ Auditoria Cruzada: XML vs SPED Fiscal")
            
            # Cruzamento
            xml_v_group = df_xml_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor': 'Valor_XML'}) if not df_xml_v.empty else pd.DataFrame(columns=['Chave NFe', 'Valor_XML'])
            sped_v_group = df_sped_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor': 'Valor_SPED'}) if not df_sped_v.empty else pd.DataFrame(columns=['Chave NFe', 'Valor_SPED'])
            
            cruzamento = pd.merge(xml_v_group, sped_v_group, on='Chave NFe', how='outer', indicator=True)
            
            so_xml = cruzamento[cruzamento['_merge'] == 'left_only']
            so_sped = cruzamento[cruzamento['_merge'] == 'right_only']
            ambos = cruzamento[cruzamento['_merge'] == 'both'].copy()
            
            ambos['Diferenca'] = ambos['Valor_XML'] - ambos['Valor_SPED']
            divergentes = ambos[abs(ambos['Diferenca']) > 0.01]
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Omissão no SPED (Só XML)", len(so_xml), delta="Risco Alto", delta_color="inverse")
            k2.metric("Sem XML (Só SPED)", len(so_sped), delta="Atenção", delta_color="inverse")
            k3.metric("Divergência de Valor", len(divergentes), delta="Erro Valor", delta_color="inverse")
            
            st.divider()
            
            if not so_xml.empty:
                st.error(f"🚨 **{len(so_xml)} Notas Omitidas no SPED**")
                st.dataframe(so_xml[['Chave NFe', 'Valor_XML']], use_container_width=True, column_config={"Valor_XML": st.column_config.NumberColumn(format="R$ %.2f")})
            
            if not divergentes.empty:
                st.warning(f"⚠️ **{len(divergentes)} Notas com Valores Divergentes**")
                st.dataframe(divergentes[['Chave NFe', 'Valor_XML', 'Valor_SPED', 'Diferenca']], use_container_width=True, column_config={"Valor_XML": st.column_config.NumberColumn(format="R$ %.2f"), "Valor_SPED": st.column_config.NumberColumn(format="R$ %.2f"), "Diferenca": st.column_config.NumberColumn(format="R$ %.2f")})
                
            if so_xml.empty and divergentes.empty:
                st.success("✅ Cruzamento Perfeito! Nenhuma divergência encontrada nas saídas.")

    idx_dash = 1 if tem_cruzamento else 0
    idx_sim = 2 if tem_cruzamento else 1
    idx_sai = 3 if tem_cruzamento else 2
    idx_ent = 4 if tem_cruzamento else 3

    # --- DASHBOARD ---
    with tabs[idx_dash]:
        st.markdown("### Visão Geral da Apuração")
        debito = df_final_v['Carga Projetada'].sum() if not df_final_v.empty else 0
        credito = df_final_c['Carga Projetada'].sum() if not df_final_c.empty else 0
        saldo = debito - credito
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Débitos (Saídas)", f"R$ {debito:,.2f}", delta="Passivo", delta_color="off")
        k2.metric("Créditos (Entradas)", f"R$ {credito:,.2f}", delta="Ativo", delta_color="normal")
        cor_saldo = "#C0392B" if saldo > 0 else "#27AE60"
        st.markdown(f"""<style>div[data-testid="metric-container"]:nth-child(3) {{border-left: 5px solid {cor_saldo} !important;}}</style>""", unsafe_allow_html=True)
        k3.metric("Saldo Estimado", f"R$ {abs(saldo):,.2f}", delta="A Pagar" if saldo > 0 else "Credor", delta_color="inverse")
        
        erros = 0
        if not df_final_v.empty: erros += len(df_final_v[df_final_v['Validação TIPI'].str.contains("Ausente")])
        k4.metric("Alertas NCM", erros, delta_color="inverse")

        if not df_final_v.empty:
            st.markdown("#### 🏆 Top 5 Produtos - Maior Carga")
            top = df_final_v.groupby('Produto')['Carga Projetada'].sum().nlargest(5).reset_index().sort_values('Carga Projetada')
            st.bar_chart(top, x="Carga Projetada", y="Produto", color="#E67E22", horizontal=True)

    # --- SIMULAÇÃO ---
    with tabs[idx_sim]:
        st.markdown("### Comparativo: Regime Atual vs. Reforma")
        total_atual = df_final_v['Carga Atual'].sum() if not df_final_v.empty else 0
        total_novo = df_final_v['Carga Projetada'].sum() if not df_final_v.empty else 0
        delta = total_novo - total_atual
        pct_delta = ((total_novo - total_atual) / total_atual * 100) if total_atual > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Carga Atual", f"R$ {total_atual:,.2f}")
        c2.metric("Nova Carga", f"R$ {total_novo:,.2f}")
        lbl_delta = "Aumento" if delta > 0 else "Economia"
        c3.metric(lbl_delta, f"R$ {abs(delta):,.2f}", delta=f"{pct_delta:+.2f}%", delta_color="inverse")
        
        df_chart = pd.DataFrame({'Cenário': ['1. Atual', '2. Reforma'], 'Valor': [total_atual, total_novo]})
        st.bar_chart(df_chart, x='Cenário', y='Valor', color='Cenário')

    # --- TABELAS ---
    col_config = {
        "Valor": st.column_config.ProgressColumn("Valor Base", format="R$ %.2f", min_value=0, max_value=float(df_final_v['Valor'].max()) if not df_final_v.empty else 1000),
        "vICMS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vPIS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vCOFINS": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Atual": st.column_config.NumberColumn(format="R$ %.2f"),
        "Carga Projetada": st.column_config.NumberColumn(format="R$ %.2f"),
        "vIBS": st.column_config.NumberColumn(format="R$ %.2f"),
        "vCBS": st.column_config.NumberColumn(format="R$ %.2f"),
        "Novo CST": st.column_config.TextColumn("Novo CST", width="small"),
        "Validação TIPI": st.column_config.TextColumn("TIPI", width="medium"),
    }

    with tabs[idx_sai]:
        if not df_final_v.empty: st.dataframe(preparar_exibicao(df_final_v), use_container_width=True, hide_index=True, column_config=col_config)
        else: st.info("Sem dados de Venda.")
    
    with tabs[idx_ent]:
        if not df_final_c.empty: st.dataframe(preparar_exibicao(df_final_c), use_container_width=True, hide_index=True, column_config=col_config)
        else: st.info("Sem dados de Compra.")

    # EXPORTAÇÃO
    st.markdown("---")
    st.markdown("### 📥 Exportar Resultados")
    c_pdf, c_xls = st.columns(2)
    with c_pdf:
        if not df_final_v.empty or not df_final_c.empty:
            try:
                pdf_bytes = relatorio.gerar_pdf_bytes(st.session_state.empresa_nome, df_final_v, df_final_c)
                st.download_button("📄 BAIXAR LAUDO (PDF)", pdf_bytes, "Laudo_Auditoria.pdf", "application/pdf", use_container_width=True)
            except: st.error("Erro PDF")
    with c_xls:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            if not df_final_v.empty: preparar_exibicao(df_final_v).to_excel(writer, index=False, sheet_name="Auditoria_Vendas")
            if not df_final_c.empty: preparar_exibicao(df_final_c).to_excel(writer, index=False, sheet_name="Auditoria_Compras")
            if tem_cruzamento and 'so_xml' in locals() and not so_xml.empty: so_xml.to_excel(writer, index=False, sheet_name="Omissao_SPED")
            if tem_cruzamento and 'divergentes' in locals() and not divergentes.empty: divergentes.to_excel(writer, index=False, sheet_name="Divergencia_Valor")
        st.download_button("📊 BAIXAR EXCEL", buffer, "Dados_Auditoria.xlsx", "primary", use_container_width=True)
else:
    st.info("👈 Utilize as caixas acima para carregar os arquivos.")