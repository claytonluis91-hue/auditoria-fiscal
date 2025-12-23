import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor 
import importlib
import relatorio
import requests

# Recarrega módulos
importlib.reload(motor)
importlib.reload(relatorio)

# --- CONFIGURAÇÃO ---
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

cols_padrao = ['Chave NFe', 'Valor', 'Produto', 'NCM']
init_df('xml_vendas_df', cols_padrao)
init_df('xml_compras_df', cols_padrao)
init_df('sped_vendas_df', cols_padrao)
init_df('sped_compras_df', cols_padrao)
init_df('sped1_vendas', cols_padrao)
init_df('sped1_compras', cols_padrao)
init_df('sped2_vendas', cols_padrao)
init_df('sped2_compras', cols_padrao)

# NBS Cache (para não baixar toda hora)
if 'df_nbs' not in st.session_state: st.session_state.df_nbs = None

if 'empresa_nome' not in st.session_state: st.session_state.empresa_nome = "Nenhuma Empresa"
if 'uploader_key' not in st.session_state: st.session_state.uploader_key = 0

def reset_all():
    for key in list(st.session_state.keys()):
        if 'df' in key or 'sped' in key:
            if key != 'df_nbs': 
                st.session_state[key] = pd.DataFrame(columns=cols_padrao)
    st.session_state.empresa_nome = "Nenhuma Empresa"
    st.session_state.uploader_key += 1

# --- CSS ---
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

# Função Inteligente para Baixar NBS do Governo
@st.cache_data(ttl=3600) # Cache por 1 hora
def baixar_nbs_gov():
    url = "https://www.gov.br/mdic/pt-br/images/REPOSITORIO/scs/decos/NBS/NBSa_2-0.csv"
    try:
        # Tenta baixar direto (com verify=False para evitar erro de certificado do gov)
        response = requests.get(url, verify=False, timeout=10)
        if response.status_code == 200:
            # Lê o CSV direto da memória
            content = response.content.decode('latin1') # Governo usa latin1 geralmente
            df = pd.read_csv(io.StringIO(content), sep=';', dtype=str)
            return df
        return None
    except:
        return None

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2910/2910768.png", width=70)
    
    st.markdown("### Selecione o Modo:")
    modo_app = st.radio(
        "Modo de Operação", 
        ["📊 Auditoria & Reforma", "⚔️ Comparador SPED vs SPED", "🔍 Consulta NBS Online"], 
        label_visibility="collapsed"
    )
    st.divider()
    
    uploaded_tipi = None 
    
    if modo_app == "📊 Auditoria & Reforma":
        if st.session_state.empresa_nome != "Nenhuma Empresa":
            st.success(f"🏢 {st.session_state.empresa_nome}")
        c1, c2 = st.columns(2)
        with c1: aliq_ibs = st.number_input("IBS (%)", 0.0, 50.0, 17.7, 0.1)
        with c2: aliq_cbs = st.number_input("CBS (%)", 0.0, 50.0, 8.8, 0.1)
        with st.expander("📂 Atualizar TIPI"):
            uploaded_tipi = st.file_uploader("TIPI", type=['xlsx', 'csv'])
            if st.button("🔄 Recarregar"):
                carregar_bases.clear()
                st.rerun()
    
    elif modo_app == "🔍 Consulta NBS Online":
        st.info("ℹ️ Conectado à base do MDIC/Gov.br")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR TUDO", type="secondary"):
        reset_all()
        st.rerun()

    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- FUNÇÕES ---
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
                k1.metric("Omissão SPED", len(so_xml), delta_color="inverse")
                k2.metric("Divergência Valor", len(div), delta_color="inverse")
                
                if not so_xml.empty: st.error("🚨 Notas fora do SPED:"); st.dataframe(so_xml)
                if not div.empty: st.warning("⚠️ Valores Divergentes:"); st.dataframe(div)

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
        st.markdown("### 📥 Exportar Relatórios Completos")
        c1, c2 = st.columns(2)
        with c1:
            try:
                if not df_final_v.empty or not df_final_c.empty:
                    pdf = relatorio.gerar_pdf_bytes(st.session_state.empresa_nome, df_final_v, df_final_c)
                    st.download_button("📄 BAIXAR LAUDO PDF", pdf, "Laudo_Auditoria.pdf", "application/pdf", use_container_width=True)
            except: st.error("Erro ao gerar PDF.")
        with c2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                if not df_final_v.empty: preparing_df = preparar_exibicao(df_final_v); preparing_df.to_excel(writer, sheet_name="Saidas", index=False)
                if not df_final_c.empty: preparing_df = preparar_exibicao(df_final_c); preparing_df.to_excel(writer, sheet_name="Entradas", index=False)
                if tem_cruzamento:
                    if 'so_xml' in locals() and not so_xml.empty: so_xml.to_excel(writer, sheet_name="Omissao_SPED", index=False)
                    if 'div' in locals() and not div.empty: div.to_excel(writer, sheet_name="Divergencia_Valor", index=False)
            st.download_button("📊 BAIXAR EXCEL COMPLETO", buf, "Auditoria_Dados.xlsx", "primary", use_container_width=True)


# ==============================================================================
# MODO 2: COMPARADOR SPED VS SPED
# ==============================================================================
elif modo_app == "⚔️ Comparador SPED vs SPED":
    st.markdown("""
    <div class="header-container">
        <div class="main-header">Comparador de Arquivos SPED</div>
        <div class="sub-header">Validação Cruzada: Original (Cliente) vs Gerado (ERP)</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 📁 1. SPED Original")
        file1 = st.file_uploader("Selecione o SPED do Cliente", type=['txt'], key="sped1")
        if not file1:
            st.session_state.sped1_vendas = pd.DataFrame(columns=cols_padrao)
        elif file1 and st.session_state.sped1_vendas.empty:
            with st.spinner("Lendo Arquivo A..."):
                n1, v1, c1 = motor.processar_sped_fiscal(file1)
                st.session_state.sped1_vendas = pd.DataFrame(v1) if v1 else pd.DataFrame(columns=cols_padrao)
                st.success(f"Arquivo A: {len(v1)} Vendas")
                st.rerun()
                
    with col2:
        st.markdown("### 💻 2. SPED Gerado")
        file2 = st.file_uploader("Selecione o SPED do ERP", type=['txt'], key="sped2")
        if not file2:
            st.session_state.sped2_vendas = pd.DataFrame(columns=cols_padrao)
        elif file2 and st.session_state.sped2_vendas.empty:
            with st.spinner("Lendo Arquivo B..."):
                n2, v2, c2 = motor.processar_sped_fiscal(file2)
                st.session_state.sped2_vendas = pd.DataFrame(v2) if v2 else pd.DataFrame(columns=cols_padrao)
                st.success(f"Arquivo B: {len(v2)} Vendas")
                st.rerun()

    df1 = st.session_state.sped1_vendas
    df2 = st.session_state.sped2_vendas
    
    try:
        if not df1.empty and not df2.empty:
            required = ['Chave NFe', 'Valor']
            if all(col in df1.columns for col in required) and all(col in df2.columns for col in required):
                st.divider()
                st.markdown("### 📊 Resultado da Comparação")
                g1 = df1.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor': 'Valor_A'})
                g2 = df2.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor': 'Valor_B'})
                comp = pd.merge(g1, g2, on='Chave NFe', how='outer', indicator=True)
                comp['Diferença'] = comp['Valor_A'].fillna(0) - comp['Valor_B'].fillna(0)
                so_no_cliente = comp[comp['_merge'] == 'left_only']
                so_no_erp = comp[comp['_merge'] == 'right_only']
                divergentes = comp[(comp['_merge'] == 'both') & (abs(comp['Diferença']) > 0.01)]
                iguais = comp[(comp['_merge'] == 'both') & (abs(comp['Diferença']) <= 0.01)]
                
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total Cliente", len(g1))
                k2.metric("Total ERP", len(g2))
                k3.metric("Faltantes", len(so_no_cliente), delta_color="inverse")
                k4.metric("Div. Valor", len(divergentes), delta_color="inverse")
                
                t1, t2 = st.tabs(["⚠️ Divergências", "✅ Iguais"])
                with t1:
                    if not so_no_cliente.empty: st.error("🚨 Notas SUMIRAM no ERP:"); st.dataframe(so_no_cliente)
                    if not so_no_erp.empty: st.warning("⚠️ Notas EXTRAS no ERP:"); st.dataframe(so_no_erp)
                    if not divergentes.empty: st.warning("💰 Valores Alterados:"); st.dataframe(divergentes)
                    if so_no_cliente.empty and so_no_erp.empty and divergentes.empty: st.success("Perfeito!")
                with t2:
                    st.success(f"{len(iguais)} Notas conferem."); st.dataframe(iguais)
            else:
                st.warning("⚠️ Arquivos carregados, mas não contêm dados de venda válidos.")
    except Exception as e:
        st.info("Aguardando arquivos válidos para comparação...")

# ==============================================================================
# MODO 3: CONSULTA NBS ONLINE (AUTOMÁTICA)
# ==============================================================================
elif modo_app == "🔍 Consulta NBS Online":
    st.markdown("""
    <div class="header-container">
        <div class="main-header">Consultor de Serviços (NBS Online)</div>
        <div class="sub-header">Base Atualizada Automaticamente via Gov.br</div>
    </div>
    """, unsafe_allow_html=True)
    
    # 1. TENTA CARREGAR DO GOVERNO
    if st.session_state.df_nbs is None:
        with st.spinner("🔄 Conectando ao servidor do MDIC/Governo..."):
            df = baixar_nbs_gov()
            if df is not None:
                st.session_state.df_nbs = df
                st.success("✅ Tabela NBS Oficial Carregada!")
            else:
                st.warning("⚠️ Não foi possível baixar automaticamente do Gov.br (Site instável ou sem internet).")
                st.info("👇 Por favor, carregue o arquivo manualmente se tiver.")
    
    # 2. SE FALHAR, MOSTRA O UPLOAD
    if st.session_state.df_nbs is None:
        uploaded_nbs = st.file_uploader("Upload Manual da NBS (CSV ou Excel)", type=['csv', 'xlsx'])
        if uploaded_nbs:
            try:
                if uploaded_nbs.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_nbs, sep=';', encoding='latin1', dtype=str)
                else:
                    df = pd.read_excel(uploaded_nbs, dtype=str)
                st.session_state.df_nbs = df
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    # 3. MOSTRA A BUSCA (SE TIVER DADOS)
    if st.session_state.df_nbs is not None and not st.session_state.df_nbs.empty:
        st.markdown("---")
        termo = st.text_input("🔍 **Pesquisar Serviço (Nome ou Código):**", placeholder="Ex: Limpeza, 1.05, Vigilância...")
        
        if termo:
            mask = st.session_state.df_nbs.apply(lambda x: x.astype(str).str.contains(termo, case=False, na=False)).any(axis=1)
            resultado = st.session_state.df_nbs[mask]
            
            st.markdown(f"**Resultados: {len(resultado)}**")
            st.dataframe(resultado, use_container_width=True)
        else:
            with st.expander("Ver Tabela Completa (Amostra)"):
                st.dataframe(st.session_state.df_nbs.head(100), use_container_width=True)
