import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import io # <--- Importante para criar o arquivo Excel na memória

# --- 1. CONFIGURAÇÃO DA PÁGINA E ESTILO (DESIGN) ---
st.set_page_config(
    page_title="Auditoria Fiscal - LCP 214",
    page_icon="⚖️",
    layout="wide"
)

# CSS Customizado para dar uma cara profissional
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    h1 {
        color: #0e1117;
        font-family: 'Helvetica Neue', sans-serif;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
        border-left: 5px solid #4CAF50;
    }
    .css-16idsys p {
        font-size: 1.1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Título com design melhorado
col_header1, col_header2 = st.columns([1, 5])
with col_header1:
    st.image("https://cdn-icons-png.flaticon.com/512/7325/7325265.png", width=80) # Ícone de balança/auditoria
with col_header2:
    st.title("Sistema de Auditoria Fiscal Inteligente")
    st.caption("Cruzamento de XMLs, Regras de Negócio e Base Legal do Planalto (LCP 214/2025)")

st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS ---
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica Nacional (Alíquota Zero)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)"},
    "ANEXO II": {"Descricao": "Medicamentos (Redução 60%)", "cClassTrib": "200009", "CST": "20", "Status": "REDUZIDA 60% (Anexo II)"},
    "ANEXO III": {"Descricao": "Dispositivos Médicos (Redução 60%)", "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo III)"},
    "ANEXO IV": {"Descricao": "Produtos de Higiene (Redução 60%)", "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)"}
}

# --- 3. CARREGAMENTO DE DADOS ---

@st.cache_data
def carregar_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            return df
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def mapear_anexos_online():
    url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    mapa_ncm_anexo = {}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        texto_limpo = soup.get_text(separator=' ')
        texto_limpo = re.sub(r'\s+', ' ', texto_limpo)
        
        anexos_encontrados = []
        for anexo in CONFIG_ANEXOS.keys():
            posicao = texto_limpo.upper().find(anexo)
            if posicao != -1:
                anexos_encontrados.append((posicao, anexo))
        anexos_encontrados.sort()
        
        for i in range(len(anexos_encontrados)):
            nome_anexo = anexos_encontrados[i][1]
            inicio = anexos_encontrados[i][0]
            if i + 1 < len(anexos_encontrados):
                fim = anexos_encontrados[i+1][0]
            else:
                fim = len(texto_limpo)
            
            bloco_texto = texto_limpo[inicio:fim]
            texto_sem_pontos = bloco_texto.replace('.', '')
            
            ncms = re.findall(r'\b\d{8}\b', texto_sem_pontos)
            capitulos = re.findall(r'\b\d{4}\b', texto_sem_pontos)
            
            for n in ncms: mapa_ncm_anexo[n] = nome_anexo
            for c in capitulos: 
                if c not in mapa_ncm_anexo: mapa_ncm_anexo[c] = nome_anexo
                    
        return mapa_ncm_anexo
    except Exception as e:
        return {}

# --- 4. LÓGICA DE CLASSIFICAÇÃO ---

def classificar_item_master(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm_limpo = str(ncm).replace('.', '')
    cfop_limpo = str(cfop).replace('.', '')
    
    # Valores Padrão
    cClassTrib, desc_legal, cst, status, origem = '000001', 'Padrão - Tributação Integral', '01', 'PADRAO', 'Regra Geral'
    
    anexo_encontrado = None
    if ncm_limpo in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo]
    elif ncm_limpo[:4] in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
    elif ncm_limpo[:2] in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo[:2]]

    if cfop_limpo.startswith('7'):
        return '410004', 'Exportação', 'IMUNE', '50', 'Não'
    elif anexo_encontrado:
        regra = CONFIG_ANEXOS[anexo_encontrado]
        return regra['cClassTrib'], f"{regra['Descricao']} (Via {anexo_encontrado})", regra['Status'], regra['CST'], anexo_encontrado
    else:
        termo_busca = ""
        if ncm_limpo.startswith('30'): termo_busca = "medicamentos"
        elif ncm_limpo.startswith('1006'): termo_busca = "cesta básica"
        else: termo_busca = "tributação integral"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return cClassTrib, desc_legal, status, cst, origem

# --- 5. INTERFACE & EXPORTAÇÃO EXCEL ---
df_regras = carregar_regras()

with st.sidebar:
    st.subheader("Painel de Controle")
    uploaded_files = st.file_uploader("Carregar XMLs de Venda", type=['xml'], accept_multiple_files=True)
    
    st.markdown("---")
    st.subheader("Status dos Serviços")
    
    with st.spinner("Conectando ao Planalto..."):
        mapa_anexos = mapear_anexos_online()
    
    if mapa_anexos:
        st.success(f"🟢 **Base Legal (LCP 214):** Conectada\n\n{len(mapa_anexos)} itens mapeados.")
    else:
        st.error("🔴 **Base Legal:** Desconectada")

if uploaded_files:
    if df_regras.empty:
        st.warning("⚠️ JSON de regras não carregado. Operando apenas com base legal.")
    
    lista_produtos = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    
    progress_bar = st.progress(0)
    
    for i, arquivo in enumerate(uploaded_files):
        try:
            tree = ET.parse(arquivo)
            root = tree.getroot()
            # Pega chave da nota
            infNFe = root.find('.//ns:infNFe', ns)
            chave = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else ''
            
            det_itens = root.findall('.//ns:det', ns)
            for item in det_itens:
                prod = item.find('ns:prod', ns)
                lista_produtos.append({
                    'Chave NFe': chave, # Adicionado para ficar bom no Excel
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Valor': float(prod.find('ns:vProd', ns).text) if prod.find('ns:vProd', ns) is not None else 0.0
                })
        except: continue
        progress_bar.progress((i + 1) / len(uploaded_files))
    
    df_base = pd.DataFrame(lista_produtos)
    
    if not df_base.empty:
        df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
        
        resultados = df_analise.apply(
            lambda row: classificar_item_master(row['NCM'], row['CFOP'], row['Produto'], df_regras, mapa_anexos), 
            axis=1, result_type='expand'
        )
        
        df_analise['cClassTrib'] = resultados[0]
        df_analise['Descrição'] = resultados[1]
        df_analise['Status'] = resultados[2]
        df_analise['CST'] = resultados[3]
        df_analise['Origem Legal'] = resultados[4]
        
        # --- DASHBOARD VISUAL ---
        st.markdown("### 📊 Resumo da Auditoria")
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("Volume de Notas", len(uploaded_files))
        col2.metric("Produtos Únicos", len(df_analise))
        
        lei_count = len(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")])
        col3.metric("Encontrados na Lei", lei_count)
        
        valor_total = df_base['Valor'].sum()
        col4.metric("Valor Auditado", f"R$ {valor_total:,.2f}")
        
        # --- TABELA INTERATIVA ---
        st.markdown("---")
        
        tab1, tab2 = st.tabs(["📋 Auditoria Detalhada", "🔍 Itens em Destaque (Lei)"])
        
        with tab1:
            st.dataframe(df_analise, use_container_width=True)
            
        with tab2:
            if lei_count > 0:
                st.success("Estes itens foram identificados nos Anexos oficiais da Lei.")
                st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")], use_container_width=True)
            else:
                st.info("Nenhum item com benefício explícito de Anexo encontrado.")

        # --- EXPORTAÇÃO PARA EXCEL (.XLSX) ---
        st.markdown("---")
        
        # Criação do arquivo Excel em memória (Buffer)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False, sheet_name='Resultado Auditoria')
            # Podemos criar uma aba extra só com os destaques da lei
            if lei_count > 0:
                df_analise[df_analise['Origem Legal'].str.contains("ANEXO")].to_excel(writer, index=False, sheet_name='Destaques Lei')
                
        # Botão de Download estilizado
        st.download_button(
            label="📥 Baixar Relatório Profissional (.xlsx)",
            data=buffer,
            file_name="Relatorio_Auditoria_Fiscal.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary" # Deixa o botão mais destacado
        )

    else:
        st.warning("Nenhum dado encontrado nos arquivos.")    