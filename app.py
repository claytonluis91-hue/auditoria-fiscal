import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor 
import importlib
import relatorio

# Recarrega módulos auxiliares
importlib.reload(motor)
importlib.reload(relatorio)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="cClass Auditor AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTADO (SESSION STATE BLINDADO) ---
def init_df(key, columns=None):
    if key not in st.session_state:
        if columns:
            st.session_state[key] = pd.DataFrame(columns=columns)
        else:
            st.session_state[key] = pd.DataFrame()

# Inicializa DataFrames com colunas essenciais
cols_padrao = ['Chave NFe', 'Num NFe', 'Valor', 'Produto', 'NCM']
init_df('xml_vendas_df', cols_padrao)
init_df('xml_compras_df', cols_padrao)
init_df('sped_vendas_df', cols_padrao)
init_df('sped_compras_df', cols_padrao)
init_df('sped1_vendas', cols_padrao)
init_df('sped1_compras', cols_padrao)
init_df('sped2_vendas', cols_padrao)
init_df('sped2_compras', cols_padrao)

if 'empresa_nome' not in st.session_state: st.session_state.empresa_nome = "Nenhuma Empresa"
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

def reset_all():
    for key in list(st.session_state.keys()):
        if 'df' in key or 'sped' in key:
            st.session_state[key] = pd.DataFrame(columns=cols_padrao)
    st.session_state.empresa_nome = "Nenhuma Empresa"
    st.session_state.uploader_key += 1

# --- CSS (ESTILO PREMIUM) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    .stApp { background-color: #F8F9FA; }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: #2C3E50; }
    section[data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #E0E0E0; }
    
    .header-container {
        background: linear-gradient(135deg, #E67E22 0%, #D35400 100%);
        padding: 25px; border-radius: 12px; margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(230, 126, 34, 0.2); color: white;
    }
    .main-header { font-size: 2.2rem; font-weight: 800; color: #FFFFFF; margin: 0; letter-spacing: -1px; }
    .sub-header { font-size: 1rem; color: #FDEBD0; margin-top: 5px; opacity: 0.9; }
    
    div[data-testid="stMetric"] { 
        background-color: #FFFFFF !important; border: 1px solid #E0E0E0; 
        border-radius: 10px; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border-top: 4px solid #E67E22; 
    }
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

# --- FUNÇÃO AUXILIAR: BUSCAR DESCRIÇÃO TIPI ---
def buscar_descricao_tipi(ncm, df_tipi):
    if df_tipi.empty: return "TIPI não carregada"
    ncm_limpo = str(ncm).replace('.', '').strip()
    try:
        resultado = None
        if ncm_limpo in df_tipi.index:
            row = df_tipi.loc[ncm_limpo]
            if isinstance(row, pd.DataFrame): resultado = row.iloc[0, 0]
            else: resultado = row.iloc[0]
        elif len(ncm_limpo) >= 4:
            posicao = ncm_limpo[:4]
            if posicao in df_tipi.index:
                row = df_tipi.loc[posicao]
                if isinstance(row, pd.DataFrame): resultado = row.iloc[0, 0]
                else: resultado = row.iloc[0]
                if resultado: resultado = f"[Posição {posicao}] {resultado}"

        if pd.isna(resultado) or str(resultado).lower().strip() == 'nan':
            return "Descrição não encontrada na TIPI"
        return str(resultado)
    except: return "Erro ao ler descrição"

# --- FUNÇÃO FORMATAÇÃO NCM (PARA O LINK FUNCIONAR) ---
def formatar_ncm_pontos(ncm):
    n = str(ncm).replace('.', '').replace(' ', '').strip()
    # Formato padrão 8 dígitos: 1234.56.78
    if len(n) == 8:
        return f"{n[:4]}.{n[4:6]}.{n[6:]}"
    # Formato 4 dígitos (Posição): 12.34
    if len(n) == 4:
        return f"{n[:2]}.{n[2:]}"
    return n # Retorna original se não souber formatar

# --- GERAR MODELO EXCEL ---
def gerar_modelo_excel():
    df_modelo = pd.DataFrame({
        'NCM': ['1006.30.21', '3004.90.69', '2202.10.00'],
        'CFOP': ['5102', '5405', '5102'],
        'Descricao_Interna': ['Arroz (Exemplo)', 'Medicamento (Exemplo)', 'Refrigerante (Exemplo)']
    })
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_modelo.to_excel(writer, index=False, sheet_name='Modelo_Importacao')
    return output.getvalue()

# --- COMPARAÇÃO SPED ---
def comparar_speds_avancado(df_a, df_b, label_a="SPED A", label_b="SPED B"):
    cols_group = ['Chave NFe', 'Num NFe', 'CFOP'] 
    cols_sum = ['Valor', 'vICMS', 'vPIS', 'vCOFINS']
    
    if 'Num NFe' not in df_a.columns: df_a['Num NFe'] = 'N/A'
    if 'Num NFe' not in df_b.columns: df_b['Num NFe'] = 'N/A'
    
    df_a['Num NFe'] = df_a['Num NFe'].astype(str)
    df_b['Num NFe'] = df_b['Num NFe'].astype(str)

    for col in cols_sum:
        if col in df_a.columns: df_a[col] = pd.to_numeric(df_a[col], errors='coerce').fillna(0)
        if col in df_b.columns: df_b[col] = pd.to_numeric(df_b[col], errors='coerce').fillna(0)

    g_a = df_a.groupby(cols_group)[cols_sum].sum().reset_index()
    g_b = df_b.groupby(cols_group)[cols_sum].sum().reset_index()
    
    merged = pd.merge(
        g_a, g_b, 
        on=['Chave NFe', 'Num NFe', 'CFOP'], 
        how='outer', 
        suffixes=('_A', '_B'), 
        indicator=True
    )
    
    merged['Dif_Valor'] = merged['Valor_A'].fillna(0) - merged['Valor_B'].fillna(0)
    merged['Dif_ICMS'] = merged['vICMS_A'].fillna(0) - merged['vICMS_B'].fillna(0)
    
    div_valor = merged[(merged['_merge'] == 'both') & (abs(merged['Dif_Valor']) > 0.05)].copy()
    so_a = merged[merged['_merge'] == 'left_only'].copy()
    so_b = merged[merged['_merge'] == 'right_only'].copy()
    
    return div_valor, so_a, so_b, len(g_a), len(g_b)

def gerar_excel_divergencias(div_v, so_a_v, so_b_v, div_c, so_a_c, so_b_c):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not div_v.empty: div_v.to_excel(writer, sheet_name='Div_Valor_Vendas', index=False)
        if not so_a_v.empty: so_a_v.to_excel(writer, sheet_name='Falta_no_ERP_Vendas', index=False)
        if not so_b_v.empty: so_b_v.to_excel(writer, sheet_name='Falta_no_Cliente_Vendas', index=False)
        if not div_c.empty: div_c.to_excel(writer, sheet_name='Div_Valor_Compras', index=False)
        if not so_a_c.empty: so_a_c.to_excel(writer, sheet_name='Falta_no_ERP_Compras', index=False)
        if not so_b_c.empty: so_b_c.to_excel(writer, sheet_name='Falta_no_Cliente_Compras', index=False)
    return output.getvalue()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2910/2910768.png", width=70)
    
    st.markdown("### Selecione o Modo:")
    modo_app = st.radio(
        "Modo de Operação", 
        ["📊 Auditoria & Reforma", "⚔️ Comparador SPED vs SPED", "🔍 Consultor de Classificação"], 
        label_visibility="collapsed"
    )
    st.divider()
    
    uploaded_tipi = None 
    
    if modo_app in ["📊 Auditoria & Reforma", "🔍 Consultor de Classificação"]:
        if st.session_state.empresa_nome != "Nenhuma Empresa" and modo_app == "📊 Auditoria & Reforma":
            st.success(f"🏢 {st.session_state.empresa_nome}")
            
        c1, c2 = st.columns(2)
        with c1: aliq_ibs = st.number_input("IBS (%)", 0.0, 50.0, 17.7, 0.1)
        with c2: aliq_cbs = st.number_input("CBS (%)", 0.0, 50.0, 8.8, 0.1)
        with st.expander("📂 Atualizar TIPI"):
            uploaded_tipi = st.file_uploader("TIPI", type=['xlsx', 'csv'])
            if st.button("🔄 Recarregar"):
                carregar_bases.clear()
                carregar_tipi_cache.clear()
                st.rerun()
                
    elif modo_app == "⚔️ Comparador SPED vs SPED":
        st.info("ℹ️ Auditoria Cruzada de Escrituração.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR TUDO", type="secondary"):
        reset_all()
        st.rerun()

    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- FUNÇÕES GERAIS ---
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

def auditar_df(df):
    if df.empty: return df
    res = df.apply(lambda row: motor.classificar_item(row, mapa_lei, df_regras_json, df_tipi, aliq_ibs/100, aliq_cbs/100), axis=1, result_type='expand')
    df[['cClassTrib', 'DescRegra', 'Status', 'Novo CST', 'Origem Legal', 'Validação TIPI', 'Carga Atual', 'Carga Projetada', 'vIBS', 'vCBS']] = res
    return df

def preparar_exibicao(df):
    cols_ordenadas = ['Cód. Produto', 'Descrição Produto', 'NCM', 'CFOP', 'Novo CST', 'cClassTrib', 'DescRegra', 'Valor', 'vICMS', 'vPIS', 'vCOFINS', 'Carga Atual', 'vIBS', 'vCBS', 'Carga Projetada', 'Validação TIPI']
    if df.empty: return df
    cols_existentes = [c for c in cols_ordenadas if c in df.columns or c == 'Descrição Produto']
    if 'Produto' in df.columns:
        return df.rename(columns={'Produto': 'Descrição Produto'})[cols_existentes]
    return df[cols_existentes]

def converter_df_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Resultado')
    return output.getvalue()

# ==============================================================================
# MODO 1: AUDITORIA & REFORMA
# ==============================================================================
if modo_app == "📊 Auditoria & Reforma":
    st.markdown("""
    <div class="header-container">
        <div class="main-header">cClass Auditor AI </div>
        <div class="sub-header">Auditoria de Conformidade e Reforma Tributária</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📂 Central de Arquivos")
    c_xml, c_sped = st.columns(2)

    with c_xml:
        with st.expander("📄 Carregar XMLs (Notas Fiscais)", expanded=True):
            st.markdown("#### 📤 1. XMLs de Saída (Vendas)")
            vendas_files = st.file_uploader("Selecione os XMLs de VENDA", type=['xml'], accept_multiple_files=True, key=f"v_{st.session_state.uploader_key}", label_visibility="collapsed")
            if vendas_files: st.markdown(f'<div class="file-success">✅ {len(vendas_files)} XMLs Venda</div>', unsafe_allow_html=True)
            
            st.divider()
            
            st.markdown("#### 📥 2. XMLs de Entrada (Compras)")
            compras_files = st.file_uploader("Selecione os XMLs de COMPRA", type=['xml'], accept_multiple_files=True, key=f"c_{st.session_state.uploader_key}", label_visibility="collapsed")
            if compras_files: st.markdown(f'<div class="file-success">✅ {len(compras_files)} XMLs Compra</div>', unsafe_allow_html=True)

            if vendas_files and st.session_state.xml_vendas_df.empty:
                st.session_state.xml_vendas_df = pd.DataFrame(processar_arquivos_com_barra(vendas_files, 'SAIDA'))
                st.rerun()
            if compras_files and st.session_state.xml_compras_df.empty:
                st.session_state.xml_compras_df = pd.DataFrame(processar_arquivos_com_barra(compras_files, 'ENTRADA'))
                st.rerun()

    with c_sped:
        with st.expander("📝 Carregar SPED Fiscal", expanded=True):
            st.markdown("#### 📋 Arquivo SPED (TXT)")
            sped_file = st.file_uploader("Selecione o arquivo TXT do SPED", type=['txt'], accept_multiple_files=False, key=f"s_{st.session_state.uploader_key}", label_visibility="collapsed")
            if sped_file: st.markdown(f'<div class="file-success">✅ SPED Pronto</div>', unsafe_allow_html=True)
            
            if sped_file and st.session_state.sped_vendas_df.empty:
                with st.spinner("Processando SPED..."):
                    nome, vendas, compras = motor.processar_sped_fiscal(sped_file)
                    st.session_state.empresa_nome = nome
                    st.session_state.sped_vendas_df = pd.DataFrame(vendas) if vendas else pd.DataFrame(columns=cols_padrao)
                    st.session_state.sped_compras_df = pd.DataFrame(compras) if compras else pd.DataFrame(columns=cols_padrao)
                    st.rerun()

    df_xml_v = auditar_df(st.session_state.xml_vendas_df.copy())
    df_xml_c = auditar_df(st.session_state.xml_compras_df.copy())
    df_sped_v = auditar_df(st.session_state.sped_vendas_df.copy())
    df_sped_c = auditar_df(st.session_state.sped_compras_df.copy())

    df_final_v = df_xml_v if not df_xml_v.empty else df_sped_v
    df_final_c = df_xml_c if not df_xml_c.empty else df_sped_c
    tem_dados = not df_final_v.empty or not df_final_c.empty

    if tem_dados:
        st.markdown("---")
        abas = ["📤 Saídas", "📥 Entradas", "⚖️ Simulação", "📊 Dashboard"]
        tem_cruzamento = (not df_xml_v.empty or not df_xml_c.empty) and (not df_sped_v.empty or not df_sped_c.empty)
        if tem_cruzamento: abas.insert(0, "⚔️ Cruzamento XML x SPED")
            
        tabs = st.tabs(abas)
        
        if tem_cruzamento:
            with tabs[abas.index("⚔️ Cruzamento XML x SPED")]:
                st.markdown("### ⚔️ Auditoria Cruzada")
                xml_val = df_xml_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor':'V_XML'}) if not df_xml_v.empty else pd.DataFrame(columns=['Chave NFe', 'V_XML'])
                sped_val = df_sped_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor':'V_SPED'}) if not df_sped_v.empty else pd.DataFrame(columns=['Chave NFe', 'V_SPED'])
                
                cross = pd.merge(xml_val, sped_val, on='Chave NFe', how='outer', indicator=True)
                so_xml = cross[cross['_merge']=='left_only']
                div = cross[(cross['_merge']=='both') & (abs(cross['V_XML'] - cross['V_SPED']) > 0.01)]
                
                k1, k2 = st.columns(2)
                k1.metric("Omissão SPED", len(so_xml), delta="Risco Alto", delta_color="inverse")
                k2.metric("Divergência Valor", len(div), delta="Erro Escrituração", delta_color="inverse")
                
                if not so_xml.empty: st.error("🚨 Notas fora do SPED:"); st.dataframe(so_xml)
                if not div.empty: st.warning("⚠️ Valores divergentes:"); st.dataframe(div)

        with tabs[abas.index("📤 Saídas")]:
            if not df_final_v.empty: st.dataframe(preparar_exibicao(df_final_v), use_container_width=True)
            else: st.info("Sem dados de Saída.")

        with tabs[abas.index("📥 Entradas")]:
            if not df_final_c.empty: st.dataframe(preparar_exibicao(df_final_c), use_container_width=True)
            else: st.info("Sem dados de Entrada.")

        with tabs[abas.index("⚖️ Simulação")]:
            st.markdown("### Comparativo")
            atu = df_final_v['Carga Atual'].sum() if 'Carga Atual' in df_final_v.columns else 0.0
            nov = df_final_v['Carga Projetada'].sum() if 'Carga Projetada' in df_final_v.columns else 0.0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Carga Atual", f"R$ {atu:,.2f}")
            c2.metric("Carga Reforma", f"R$ {nov:,.2f}")
            delta = nov - atu
            c3.metric("Variação", f"R$ {abs(delta):,.2f}", delta="Aumento" if delta > 0 else "Economia", delta_color="inverse")
            
            try:
                st.bar_chart(pd.DataFrame({'Cenário':['Atual','Novo'], 'Valor':[float(atu),float(nov)]}).set_index('Cenário')['Valor'])
            except: st.warning("Gráfico indisponível.")

        with tabs[abas.index("📊 Dashboard")]:
            st.markdown("### Visão Geral")
            d = df_final_v['Carga Projetada'].sum() if 'Carga Projetada' in df_final_v.columns else 0.0
            c = df_final_c['Carga Projetada'].sum() if 'Carga Projetada' in df_final_c.columns else 0.0
            k1, k2, k3 = st.columns(3)
            k1.metric("Débitos", f"R$ {d:,.2f}"); k2.metric("Créditos", f"R$ {c:,.2f}"); k3.metric("Saldo", f"R$ {d-c:,.2f}")
            try:
                if 'Carga Projetada' in df_final_v.columns:
                    top = df_final_v.groupby('Produto')['Carga Projetada'].sum().nlargest(5).reset_index()
                    st.bar_chart(top.set_index('Produto')['Carga Projetada'])
            except: pass

        st.markdown("---")
        st.markdown("### 📥 Exportar Relatórios")
        c1, c2 = st.columns(2)
        with c1:
            try:
                if not df_final_v.empty or not df_final_c.empty:
                    pdf = relatorio.gerar_pdf_bytes(st.session_state.empresa_nome, df_final_v, df_final_c)
                    st.download_button("📄 BAIXAR LAUDO PDF", pdf, "Laudo_Auditoria.pdf", "application/pdf", use_container_width=True)
            except: st.error("Erro PDF")
        with c2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                if not df_final_v.empty: preparing_df = preparar_exibicao(df_final_v); preparing_df.to_excel(writer, sheet_name="Saidas", index=False)
                if not df_final_c.empty: preparing_df = preparar_exibicao(df_final_c); preparing_df.to_excel(writer, sheet_name="Entradas", index=False)
                if tem_cruzamento:
                    if 'so_xml' in locals() and not so_xml.empty: so_xml.to_excel(writer, sheet_name="Omissao_SPED", index=False)
                    if 'div' in locals() and not div.empty: div.to_excel(writer, sheet_name="Divergencia_Valor", index=False)
            st.download_button("📊 BAIXAR EXCEL", buf, "Auditoria_Dados.xlsx", "primary", use_container_width=True)


# ==============================================================================
# MODO 2: COMPARADOR SPED VS SPED
# ==============================================================================
elif modo_app == "⚔️ Comparador SPED vs SPED":
    st.markdown("""
    <div class="header-container">
        <div class="main-header">Comparador de Arquivos SPED</div>
        <div class="sub-header">Validação Cruzada por CFOP e Valor (Entradas e Saídas)</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    # Upload SPED A
    with col1:
        st.markdown("### 📁 1. SPED Original (Cliente)")
        file1 = st.file_uploader("Selecione o SPED do Cliente", type=['txt'], key="sped1")
        if file1 and st.session_state.sped1_vendas.empty:
            with st.spinner("Processando SPED A..."):
                n1, v1, c1 = motor.processar_sped_fiscal(file1)
                st.session_state.sped1_vendas = pd.DataFrame(v1) if v1 else pd.DataFrame(columns=cols_padrao)
                st.session_state.sped1_compras = pd.DataFrame(c1) if c1 else pd.DataFrame(columns=cols_padrao)
                st.success(f"Lido: {len(v1)} Saídas | {len(c1)} Entradas")
                st.rerun()
                
    # Upload SPED B
    with col2:
        st.markdown("### 💻 2. SPED Gerado (ERP/Sistema)")
        file2 = st.file_uploader("Selecione o SPED do ERP", type=['txt'], key="sped2")
        if file2 and st.session_state.sped2_vendas.empty:
            with st.spinner("Processando SPED B..."):
                n2, v2, c2 = motor.processar_sped_fiscal(file2)
                st.session_state.sped2_vendas = pd.DataFrame(v2) if v2 else pd.DataFrame(columns=cols_padrao)
                st.session_state.sped2_compras = pd.DataFrame(c2) if c2 else pd.DataFrame(columns=cols_padrao)
                st.success(f"Lido: {len(v2)} Saídas | {len(c2)} Entradas")
                st.rerun()

    # --- LÓGICA DE COMPARAÇÃO ---
    if not st.session_state.sped1_vendas.empty and not st.session_state.sped2_vendas.empty:
        st.divider()
        st.markdown("### 📊 Resultado da Auditoria Cruzada")
        
        tab_vendas, tab_compras = st.tabs(["📤 Comparar Saídas (Vendas)", "📥 Comparar Entradas (Compras)"])
        
        # 1. COMPARAÇÃO DE VENDAS
        with tab_vendas:
            div_v, so_a_v, so_b_v, tot_a, tot_b = comparar_speds_avancado(
                st.session_state.sped1_vendas, 
                st.session_state.sped2_vendas
            )
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Cliente", tot_a)
            k2.metric("Total ERP", tot_b)
            k3.metric("Divergência Valor", len(div_v), delta_color="inverse")
            k4.metric("Divergência CFOP/Omissão", len(so_a_v) + len(so_b_v), delta_color="inverse")
            
            if not div_v.empty:
                st.error("💰 **Divergência de Valores (Mesma Chave e CFOP):**")
                st.dataframe(div_v[['Num NFe', 'Chave NFe', 'CFOP', 'Valor_A', 'Valor_B', 'Dif_Valor', 'Dif_ICMS']])
            
            if not so_a_v.empty:
                st.warning("⚠️ **Consta no Cliente, mas NÃO no ERP (Ou CFOP Diferente):**")
                st.dataframe(so_a_v[['Num NFe', 'Chave NFe', 'CFOP', 'Valor_A']])
                
            if not so_b_v.empty:
                st.info("ℹ️ **Consta no ERP, mas NÃO no Cliente (Ou CFOP Diferente):**")
                st.dataframe(so_b_v[['Num NFe', 'Chave NFe', 'CFOP', 'Valor_B']])
                
            if div_v.empty and so_a_v.empty and so_b_v.empty:
                st.success("✅ As Saídas estão idênticas nos dois arquivos!")

        # 2. COMPARAÇÃO DE COMPRAS
        with tab_compras:
            div_c, so_a_c, so_b_c, tot_a_c, tot_b_c = comparar_speds_avancado(
                st.session_state.sped1_compras, 
                st.session_state.sped2_compras
            )
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Cliente", tot_a_c)
            k2.metric("Total ERP", tot_b_c)
            k3.metric("Divergência Valor", len(div_c), delta_color="inverse")
            k4.metric("Divergência CFOP/Omissão", len(so_a_c) + len(so_b_c), delta_color="inverse")
            
            if not div_c.empty:
                st.error("💰 **Divergência de Valores (Mesma Chave e CFOP):**")
                st.dataframe(div_c[['Num NFe', 'Chave NFe', 'CFOP', 'Valor_A', 'Valor_B', 'Dif_Valor']])
            
            if not so_a_c.empty:
                st.warning("⚠️ **Consta no Cliente, mas NÃO no ERP:**")
                st.dataframe(so_a_c[['Num NFe', 'Chave NFe', 'CFOP', 'Valor_A']])
                
            if not so_b_c.empty:
                st.info("ℹ️ **Consta no ERP, mas NÃO no Cliente:**")
                st.dataframe(so_b_c[['Num NFe', 'Chave NFe', 'CFOP', 'Valor_B']])

            if div_c.empty and so_a_c.empty and so_b_c.empty:
                st.success("✅ As Entradas estão idênticas nos dois arquivos!")

        # 3. DOWNLOAD
        st.markdown("---")
        excel_divergencias = gerar_excel_divergencias(div_v, so_a_v, so_b_v, div_c, so_a_c, so_b_c)
        st.download_button(
            label="📥 Baixar Relatório de Divergências (Excel Detalhado)",
            data=excel_divergencias,
            file_name="Divergencias_SPED_vs_SPED.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Baixa um arquivo Excel contendo abas separadas para divergências de valor e omissões."
        )

# ==============================================================================
# MODO 3: CONSULTOR DE CLASSIFICAÇÃO
# ==============================================================================
elif modo_app == "🔍 Consultor de Classificação":
    st.markdown("""
    <div class="header-container">
        <div class="main-header">Consultor Inteligente</div>
        <div class="sub-header">Pesquisa de CST e cClassTrib por NCM e Operação</div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔍 Consulta Rápida (Individual)", "📂 Processamento em Lote (Excel)"])

    # --- TAB 1: CONSULTA INDIVIDUAL ---
    with tab1:
        st.markdown("#### Simular Classificação de Item")
        
        c1, c2 = st.columns([1, 1])
        with c1:
            ncm_input = st.text_input("NCM do Produto:", placeholder="Ex: 1006.30.21", max_chars=10)
        with c2:
            cfop_input = st.text_input("CFOP da Operação:", value="5102", placeholder="Ex: 5102, 5910", max_chars=4, help="Se vazio, assume venda padrão.")

        if st.button("🔍 Consultar Regra", type="primary"):
            if ncm_input:
                # Normaliza entrada
                ncm_limpo = ncm_input.replace('.', '').strip()
                ncm_formatado_pontos = formatar_ncm_pontos(ncm_limpo)
                
                # 1. Busca Descrição na TIPI
                desc_tipi = buscar_descricao_tipi(ncm_limpo, df_tipi)
                
                # 2. Monta linha simulada para o motor
                row_simulada = {
                    'NCM': ncm_limpo,
                    'CFOP': cfop_input if cfop_input else '5102',
                    'Valor': 100.00, # Valor fictício para ativar o cálculo
                    'vICMS': 0, 'vPIS': 0, 'vCOFINS': 0
                }
                
                # 3. Chama o Motor de Regras
                resultado = motor.classificar_item(
                    row_simulada, mapa_lei, df_regras_json, df_tipi, 
                    aliq_ibs/100, aliq_cbs/100
                )
                cClass, desc_regra, status, novo_cst, origem_legal = resultado[0], resultado[1], resultado[2], resultado[3], resultado[4]
                
                # 4. Exibe Resultado
                st.markdown("---")
                st.markdown(f"### Resultado para NCM **{ncm_input}**")
                st.caption(f"Operação: CFOP {row_simulada['CFOP']}")
                
                k1, k2 = st.columns(2)
                k1.metric("Novo CST", novo_cst)
                k2.metric("cClassTrib", cClass)
                
                st.markdown("**Status Tributário:**")
                if "ZERO" in status or "REDUZIDA" in status or "IMUNE" in status:
                    st.success(f"✅ {status}")
                elif "ALERTA" in status:
                    st.error(f"🚨 {status}")
                else:
                    st.info(f"ℹ️ {status}")
                
                with st.expander("📋 Detalhes do Produto e Regra Legal", expanded=True):
                    st.markdown(f"**Descrição TIPI:** {desc_tipi}")
                    st.markdown(f"**Regra Aplicada:** {desc_regra}")
                    st.caption(f"Fonte da Regra: {origem_legal}")
                    # Links Úteis (DEEP LINK NA LEI)
                    link_google = f"https://www.google.com/search?q=NCM+{ncm_limpo}+TIPI"
                    # Constrói o link com scroll para texto (Text Fragment)
                    link_lei = f"https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm#:~:text={ncm_formatado_pontos}"
                    
                    st.markdown(f"🌐 [Verificar Produto (Google)]({link_google})")
                    st.markdown(f"📜 [Consultar na Lei (LC 214 - Scroll Automático)]({link_lei})")
                
            else:
                st.warning("Digite um NCM para pesquisar.")

    # --- TAB 2: CONSULTA EM LOTE ---
    with tab2:
        st.markdown("#### Saneamento de Cadastro (Upload Excel)")
        st.info("ℹ️ Baixe o modelo, preencha com seus produtos e faça o upload para classificar em massa.")
        
        c_down, c_up = st.columns([1, 2])
        with c_down:
            st.download_button(
                label="📥 Baixar Planilha Modelo",
                data=gerar_modelo_excel(),
                file_name="Modelo_Classificacao_NCM.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Clique para baixar o arquivo Excel padrão para preenchimento."
            )
        
        uploaded_lote = st.file_uploader("Selecione sua planilha preenchida", type=['xlsx', 'csv'])
        
        if uploaded_lote:
            try:
                if uploaded_lote.name.endswith('.csv'):
                    df_lote = pd.read_csv(uploaded_lote, sep=';', dtype=str)
                else:
                    df_lote = pd.read_excel(uploaded_lote, dtype=str)
                
                col_ncm = None
                col_cfop = None
                
                for col in df_lote.columns:
                    if 'ncm' in col.lower(): col_ncm = col
                    if 'cfop' in col.lower(): col_cfop = col
                
                if col_ncm:
                    st.success(f"Processando {len(df_lote)} linhas...")
                    
                    resultados_lote = []
                    prog_bar = st.progress(0)
                    total = len(df_lote)
                    
                    for idx, row in df_lote.iterrows():
                        ncm_val = str(row[col_ncm])
                        cfop_val = str(row[col_cfop]) if col_cfop and pd.notna(row[col_cfop]) else "5102"
                        
                        # Formata NCM para o link da lei
                        ncm_limpo = ncm_val.replace('.', '').strip()
                        ncm_formatado_pontos = formatar_ncm_pontos(ncm_limpo)
                        
                        row_sim = {'NCM': ncm_val, 'CFOP': cfop_val, 'Valor': 100.0, 'vICMS':0, 'vPIS':0, 'vCOFINS':0}
                        res = motor.classificar_item(row_sim, mapa_lei, df_regras_json, df_tipi, aliq_ibs/100, aliq_cbs/100)
                        desc_tipi = buscar_descricao_tipi(ncm_val, df_tipi)
                        
                        # AQUI: GERAMOS O LINK DA LEI PARA O EXCEL (SEM GOOGLE)
                        link_lei = f"https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm#:~:text={ncm_formatado_pontos}"
                        
                        # Para a tela, podemos mostrar o Google se quiser, mas para o Excel vai o da Lei
                        link_google = f"https://www.google.com/search?q=NCM+{ncm_val}+TIPI"
                        
                        resultados_lote.append({
                            'NCM Original': ncm_val,
                            'CFOP': cfop_val,
                            'Descrição TIPI': desc_tipi,
                            'Novo CST': res[3],
                            'cClassTrib': res[0],
                            'Regra Aplicada': res[1],
                            'Status Tributário': res[2],
                            'Link Conferência (Google)': link_google, # Vai aparecer na tela
                            'Link Legislação (LC 214)': link_lei      # Vai para o Excel
                        })
                        
                        if idx % 10 == 0: prog_bar.progress((idx + 1) / total)
                    
                    prog_bar.empty()
                    df_resultado = pd.DataFrame(resultados_lote)
                    
                    # TELA: Mostra Link do Google (Mais visual para auditoria rápida)
                    st.dataframe(
                        df_resultado.drop(columns=['Link Legislação (LC 214)']), # Esconde o da lei na tela pra não poluir
                        column_config={
                            "Link Conferência (Google)": st.column_config.LinkColumn(
                                "🔍 Validar (Web)", display_text="Ver no Google"
                            )
                        }
                    )
                    
                    # EXCEL: Apenas Link da Lei (Limpo e Direto)
                    df_export = df_resultado.drop(columns=['Link Conferência (Google)'])
                    
                    csv = df_export.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
                    st.download_button("📥 Baixar Resultado (CSV)", csv, "Resultado_Classificacao.csv", "text/csv")
                    
                else:
                    st.error("Não encontrei a coluna 'NCM'. Verifique o cabeçalho.")
                    
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")
