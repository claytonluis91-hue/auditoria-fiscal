import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import motor 
import importlib
import relatorio

# Recarrega módulos
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
# Inicializa variáveis com segurança
def init_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

init_state('xml_vendas_df', pd.DataFrame())
init_state('xml_compras_df', pd.DataFrame())
init_state('sped_vendas_df', pd.DataFrame())
init_state('sped_compras_df', pd.DataFrame())
init_state('sped1_vendas', pd.DataFrame())
init_state('sped1_compras', pd.DataFrame())
init_state('sped2_vendas', pd.DataFrame())
init_state('sped2_compras', pd.DataFrame())
init_state('empresa_nome', "Nenhuma Empresa")
init_state('uploader_key', 0)

def reset_all():
    # Reseta forçado
    st.session_state.xml_vendas_df = pd.DataFrame()
    st.session_state.xml_compras_df = pd.DataFrame()
    st.session_state.sped_vendas_df = pd.DataFrame()
    st.session_state.sped_compras_df = pd.DataFrame()
    st.session_state.sped1_vendas = pd.DataFrame()
    st.session_state.sped2_vendas = pd.DataFrame()
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
    
    .stProgress > div > div > div > div { background-color: #E67E22; }

    div[data-testid="stMetric"] { 
        background-color: #FFFFFF !important; border: 1px solid #E0E0E0; 
        border-radius: 10px; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border-top: 4px solid #E67E22; 
    }
    
    .file-success {
        background-color: #D5F5E3; color: #196F3D; padding: 10px; border-radius: 5px;
        border: 1px solid #ABEBC6; margin-top: 5px; margin-bottom: 10px; font-weight: 600; text-align: center;
    }
    
    .correction-box {
        background-color: #FEF9E7; border: 1px solid #F39C12; padding: 20px; border-radius: 10px; margin-top: 20px;
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
    
    st.markdown("### Selecione o Modo:")
    modo_app = st.radio("Modo de Operação", ["📊 Auditoria & Reforma", "⚔️ Comparador SPED vs SPED"], label_visibility="collapsed")
    
    st.divider()
    
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
                
    elif modo_app == "⚔️ Comparador SPED vs SPED":
        st.info("ℹ️ Validação de Arquivos.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ LIMPAR TUDO", type="secondary"):
        reset_all()
        st.rerun()

    mapa_lei, df_regras_json = carregar_bases()
    df_tipi = carregar_tipi_cache(uploaded_tipi)

# --- FUNÇÕES ---
ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

def convert_df_to_csv(df):
    return df.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig').encode('utf-8-sig')

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
        <div class="sub-header">Auditoria de Conformidade e Reforma Tributária | Powered by Nascel</div>
    </div>
    """, unsafe_allow_html=True)

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

    df_xml_v = auditar_df(st.session_state.xml_vendas_df.copy())
    df_xml_c = auditar_df(st.session_state.xml_compras_df.copy())
    df_sped_v = auditar_df(st.session_state.sped_vendas_df.copy())
    df_sped_c = auditar_df(st.session_state.sped_compras_df.copy())

    df_final_v = df_xml_v if not df_xml_v.empty else df_sped_v
    df_final_c = df_xml_c if not df_xml_c.empty else df_sped_c
    tem_dados = not df_final_v.empty or not df_final_c.empty

    if tem_dados:
        st.markdown("---")
        abas = ["💎 Oportunidades & Riscos", "📊 Dashboard", "⚖️ Simulação", "📤 Saídas", "📥 Entradas"]
        tem_cruzamento = (not df_xml_v.empty or not df_xml_c.empty) and (not df_sped_v.empty or not df_sped_c.empty)
        if tem_cruzamento: abas.insert(0, "⚔️ Cruzamento XML x SPED")
            
        tabs = st.tabs(abas)
        
        if tem_cruzamento:
            with tabs[0]:
                st.markdown("### ⚔️ Auditoria Cruzada")
                xml_val = df_xml_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor':'V_XML'}) if not df_xml_v.empty else pd.DataFrame()
                sped_val = df_sped_v.groupby('Chave NFe')['Valor'].sum().reset_index().rename(columns={'Valor':'V_SPED'}) if not df_sped_v.empty else pd.DataFrame()
                
                cross = pd.merge(xml_val, sped_val, on='Chave NFe', how='outer', indicator=True)
                so_xml = cross[cross['_merge']=='left_only']
                div = cross[(cross['_merge']=='both') & (abs(cross['V_XML'] - cross['V_SPED']) > 0.01)]
                
                k1, k2 = st.columns(2)
                k1.metric("Omissão SPED", len(so_xml), delta_color="inverse")
                k2.metric("Divergência Valor", len(div), delta_color="inverse")
                
                if not so_xml.empty: st.error("🚨 Notas fora do SPED:"); st.dataframe(so_xml)
                if not div.empty: st.warning("⚠️ Valores Divergentes:"); st.dataframe(div)

        idx = 1 if tem_cruzamento else 0
        with tabs[idx]:
            st.markdown("### 💎 Análise de Inteligência Fiscal")
            if not df_final_v.empty:
                op = df_final_v[(df_final_v['Carga Atual']>0) & (df_final_v['Status'].str.contains("ZERO") | df_final_v['Status'].str.contains("REDUZIDA"))].copy()
                ri = df_final_v[(df_final_v['Carga Atual']==0) & (df_final_v['Status']=="PADRAO")]
                
                c1, c2 = st.columns(2)
                c1.metric("💰 Recuperável", f"R$ {op['Carga Atual'].sum():,.2f}")
                c2.metric("⚠️ Risco", f"R$ {ri['Carga Projetada'].sum():,.2f}")
                
                if not op.empty:
                    st.success("Itens pagando a mais:")
                    st.dataframe(op[['Produto', 'NCM', 'Carga Atual', 'DescRegra']])
                    st.markdown('<div class="correction-box">', unsafe_allow_html=True)
                    st.markdown("#### 🛠️ Kit de Correção")
                    df_cor = op[['Cód. Produto', 'Produto', 'NCM', 'DescRegra']].copy()
                    df_cor.columns = ['COD', 'DESCRICAO', 'NCM_ATUAL', 'REGRA_SUGERIDA']
                    st.download_button("📥 BAIXAR CSV", convert_df_to_csv(df_cor), "Correcao.csv", "text/csv")
                    st.markdown('</div>', unsafe_allow_html=True)

                if not ri.empty: st.error("Itens pagando a menos:"); st.dataframe(ri[['Produto', 'NCM', 'DescRegra']])

        idx += 1
        with tabs[idx]:
            st.markdown("### Visão Geral")
            d = df_final_v['Carga Projetada'].sum(); c = df_final_c['Carga Projetada'].sum()
            k1, k2, k3 = st.columns(3)
            k1.metric("Débitos", f"R$ {d:,.2f}"); k2.metric("Créditos", f"R$ {c:,.2f}"); k3.metric("Saldo", f"R$ {d-c:,.2f}")
            try:
                top = df_final_v.groupby('Produto')['Carga Projetada'].sum().nlargest(5).reset_index()
                st.bar_chart(top.set_index('Produto')['Carga Projetada'])
            except: pass

        idx += 1
        with tabs[idx]:
            st.markdown("### Comparativo")
            atu = df_final_v['Carga Atual'].sum(); nov = df_final_v['Carga Projetada'].sum()
            try:
                st.bar_chart(pd.DataFrame({'Cenário':['Atual','Novo'], 'Valor':[float(atu),float(nov)]}).set_index('Cenário')['Valor'])
            except: pass

        with tabs[idx+1]: st.dataframe(preparar_exibicao(df_final_v))
        with tabs[idx+2]: st.dataframe(preparar_exibicao(df_final_c))


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
    
    # --- LIMPEZA AUTOMÁTICA DE MEMÓRIA SUJA ---
    # Se o uploader estiver vazio, garante que o dataframe esteja vazio
    
    with col1:
        st.markdown("### 📁 1. SPED Original")
        file1 = st.file_uploader("Upload SPED Cliente", type=['txt'], key="sped1")
        if not file1: 
            st.session_state.sped1_vendas = pd.DataFrame()
        elif file1 and st.session_state.sped1_vendas.empty:
            with st.spinner("Lendo Arquivo A..."):
                n1, v1, c1 = motor.processar_sped_fiscal(file1)
                st.session_state.sped1_vendas = pd.DataFrame(v1)
                st.session_state.sped1_compras = pd.DataFrame(c1)
                st.rerun()
                
    with col2:
        st.markdown("### 💻 2. SPED Gerado")
        file2 = st.file_uploader("Upload SPED ERP", type=['txt'], key="sped2")
        if not file2:
            st.session_state.sped2_vendas = pd.DataFrame()
        elif file2 and st.session_state.sped2_vendas.empty:
            with st.spinner("Lendo Arquivo B..."):
                n2, v2, c2 = motor.processar_sped_fiscal(file2)
                st.session_state.sped2_vendas = pd.DataFrame(v2)
                st.session_state.sped2_compras = pd.DataFrame(c2)
                st.rerun()

    df1 = st.session_state.sped1_vendas
    df2 = st.session_state.sped2_vendas
    
    # --- BLINDAGEM CONTRA ARQUIVO VAZIO ---
    if not df1.empty and not df2.empty:
        required = ['Chave NFe', 'Valor']
        # Verifica se as colunas existem antes de tentar calcular
        if all(col in df1.columns for col in required) and all(col in df2.columns for col in required):
            st.divider()
            st.markdown("### 📊 Resultado da Comparação (Vendas/Saídas)")
            
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
            st.warning("⚠️ Um dos arquivos não possui registros de venda válidos (C100/C190).")