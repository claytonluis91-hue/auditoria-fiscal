import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - LCP 214",
    page_icon="⚖️",
    layout="wide"
)

# Estilos CSS
st.markdown("""
    <style>
    .main {background-color: #f8f9fa;}
    h1 {color: #0e1117;}
    .stMetric {background-color: #fff; padding: 15px; border-radius: 10px; border-left: 5px solid #2E86C1;}
    </style>
    """, unsafe_allow_html=True)

st.title("Sistema de Auditoria Fiscal Inteligente")
st.caption("Versão com Trava de Segurança (Anti-Erro em Bebidas e Cigarros)")
st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS ---
CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica (Aliq. Zero)", "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)"},
    "ANEXO II": {"Descricao": "Medicamentos (Red. 60%)", "cClassTrib": "200009", "CST": "20", "Status": "REDUZIDA 60% (Anexo II)"},
    "ANEXO III": {"Descricao": "Disp. Médicos (Red. 60%)", "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo III)"},
    "ANEXO IV": {"Descricao": "Higiene Pessoal (Red. 60%)", "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)"}
}

# --- 3. TRAVA DE SEGURANÇA (NOVIDADE) ---
def validar_coerencia_ncm(ncm, anexo_sugerido):
    """
    Impede que NCMs de Imposto Seletivo caiam em regras de benefício por erro de leitura.
    Retorna True se for seguro, False se for incoerente.
    """
    ncm = str(ncm).replace('.', '')
    
    # Capítulos proibidos em Cesta Básica ou Higiene
    capitulos_proibidos = [
        '22', # Bebidas Alcoólicas
        '24', # Tabaco / Cigarro
        '93', # Armas e Munições
        '87'  # Veículos (Geralmente não são higiene/cesta básica)
    ]
    
    # Se o NCM começa com algum proibido, bloqueia o benefício
    if any(ncm.startswith(cap) for cap in capitulos_proibidos):
        return False
        
    return True

# --- 4. CARREGAMENTO DE DADOS ---

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
    headers = {"User-Agent": "Mozilla/5.0"}
    mapa_ncm_anexo = {}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        texto = soup.get_text(separator=' ').replace('\n', ' ')
        texto = re.sub(r'\s+', ' ', texto)
        
        # Procura os Anexos
        anexos_pos = []
        for anexo in CONFIG_ANEXOS.keys():
            pos = texto.upper().find(anexo)
            if pos != -1: anexos_pos.append((pos, anexo))
        anexos_pos.sort()
        
        # Adiciona um "Fim de Curso" para parar de ler se achar palavras perigosas
        # Isso ajuda o robô a saber que o Anexo IV acabou
        pos_imposto_seletivo = texto.upper().find("IMPOSTO SELETIVO")
        if pos_imposto_seletivo != -1:
            anexos_pos.append((pos_imposto_seletivo, "FIM_ANEXOS"))
        anexos_pos.sort()

        for i in range(len(anexos_pos)):
            nome = anexos_pos[i][1]
            if nome == "FIM_ANEXOS": continue # Não mapeia o resto
            
            inicio = anexos_pos[i][0]
            fim = anexos_pos[i+1][0] if i+1 < len(anexos_pos) else len(texto)
            
            bloco = texto[inicio:fim].replace('.', '')
            ncms = re.findall(r'\b\d{8}\b', bloco)
            caps = re.findall(r'\b\d{4}\b', bloco)
            
            for n in ncms: mapa_ncm_anexo[n] = nome
            for c in caps: 
                if c not in mapa_ncm_anexo: mapa_ncm_anexo[c] = nome
                    
        return mapa_ncm_anexo
    except: return {}

# --- 5. CLASSIFICAÇÃO COM TRAVA ---

def classificar_item_master(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm_limpo = str(ncm).replace('.', '')
    cfop_limpo = str(cfop).replace('.', '')
    
    # Padrão
    cClassTrib, desc, cst, status, origem = '000001', 'Padrão - Tributação Integral', '01', 'PADRAO', 'Regra Geral'
    
    # 1. Busca no Mapa da Lei
    anexo_encontrado = None
    if ncm_limpo in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo]
    elif ncm_limpo[:4] in mapa_anexos: anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
    
    # --- AQUI ENTRA A TRAVA DE SEGURANÇA ---
    # Se achou anexo, mas é cigarro (24) ou bebida (22), ANULA o anexo.
    if anexo_encontrado:
        if not validar_coerencia_ncm(ncm_limpo, anexo_encontrado):
            anexo_encontrado = None # Cancela o benefício
            origem = "Bloqueado por Trava de Segurança (NCM Incompatível)"
            status = "ALERTA - IMPOSTO SELETIVO"
            cst = "02" # Tributação Monofásica/Seletiva

    # 2. Aplica Regras
    if cfop_limpo.startswith('7'):
        return '410004', 'Exportação', 'IMUNE', '50', 'Não'
        
    elif anexo_encontrado:
        regra = CONFIG_ANEXOS[anexo_encontrado]
        return regra['cClassTrib'], f"{regra['Descricao']} (Via {anexo_encontrado})", regra['Status'], regra['CST'], anexo_encontrado
    
    # 3. Fallback JSON (Se não caiu na lei ou foi bloqueado)
    else:
        # Se foi bloqueado antes, mantém o status de alerta
        if status == "ALERTA - IMPOSTO SELETIVO":
            return '000001', 'Produto sujeito a Imposto Seletivo/Majorado', status, cst, origem

        # Busca normal
        termo_busca = ""
        if ncm_limpo.startswith('30'): termo_busca = "medicamentos"
        elif ncm_limpo.startswith('1006'): termo_busca = "cesta básica"
        elif ncm_limpo.startswith('2203') or ncm_limpo.startswith('2402'): # Reforço manual
            termo_busca = "bebidas" # Força padrão ou regra específica
            return '000001', 'Tributação Integral (Bebida/Fumo)', 'PADRAO', '02', 'Regra NCM'
        else: termo_busca = "tributação integral"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem

    return cClassTrib, desc, status, cst, origem

# --- 6. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.subheader("Painel de Controle")
    uploaded_files = st.file_uploader("Carregar XMLs", type=['xml'], accept_multiple_files=True)
    with st.spinner("Lendo Lei..."):
        mapa_anexos = mapear_anexos_online()
    if mapa_anexos: st.success(f"🟢 Lei Mapeada ({len(mapa_anexos)} itens)")

if uploaded_files:
    if df_regras.empty: st.warning("Sem JSON de regras.")
    
    lista_produtos = []
    ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
    
    for arquivo in uploaded_files:
        try:
            tree = ET.parse(arquivo)
            root = tree.getroot()
            infNFe = root.find('.//ns:infNFe', ns)
            chave = infNFe.attrib.get('Id', '')[3:] if infNFe else ''
            for item in root.findall('.//ns:det', ns):
                prod = item.find('ns:prod', ns)
                lista_produtos.append({
                    'Chave NFe': chave,
                    'NCM': prod.find('ns:NCM', ns).text,
                    'Produto': prod.find('ns:xProd', ns).text,
                    'CFOP': prod.find('ns:CFOP', ns).text,
                    'Valor': float(prod.find('ns:vProd', ns).text)
                })
        except: continue
    
    df_base = pd.DataFrame(lista_produtos)
    
    if not df_base.empty:
        df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
        
        resultados = df_analise.apply(
            lambda row: classificar_item_master(row['NCM'], row['CFOP'], row['Produto'], df_regras, mapa_anexos), 
            axis=1, result_type='expand'
        )
        
        df_analise[['cClassTrib', 'Descrição', 'Status', 'CST', 'Origem Legal']] = resultados
        
        st.markdown("### 📊 Auditoria Fiscal")
        col1, col2, col3 = st.columns(3)
        col1.metric("Produtos", len(df_analise))
        col2.metric("Encontrados na Lei", len(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")]))
        # Mostra se houve bloqueios
        bloqueios = len(df_analise[df_analise['Status'].str.contains("ALERTA")])
        col3.metric("Correções de Segurança", bloqueios, delta="Bloqueios de IS" if bloqueios > 0 else None, delta_color="inverse")
        
        tab1, tab2 = st.tabs(["Geral", "Destaques Lei"])
        with tab1: st.dataframe(df_analise, use_container_width=True)
        with tab2: st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")], use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_analise.to_excel(writer, index=False, sheet_name='Resultado')
        
        st.download_button("📥 Baixar Excel (.xlsx)", buffer, "Auditoria.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")