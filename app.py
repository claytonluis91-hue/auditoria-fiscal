import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - Reforma Tributária (Online)",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Auditoria Fiscal: Conectada ao Planalto")
st.markdown("O sistema acessa o site da LCP 214, identifica os **Anexos** e aplica o CST/cClassTrib correspondente.")
st.divider()

# --- 2. CONFIGURAÇÃO DOS ANEXOS (O CÉREBRO) ---
# Define o que cada Anexo significa.
CONFIG_ANEXOS = {
    "ANEXO I": {
        "Descricao": "Cesta Básica Nacional (Alíquota Zero)",
        "cClassTrib": "200003", "CST": "40", "Status": "ZERO (Anexo I)"
    },
    "ANEXO II": {
        "Descricao": "Medicamentos (Redução 60%)",
        "cClassTrib": "200009", "CST": "20", "Status": "REDUZIDA 60% (Anexo II)"
    },
    "ANEXO III": {
        "Descricao": "Dispositivos Médicos (Redução 60%)",
        "cClassTrib": "200005", "CST": "20", "Status": "REDUZIDA 60% (Anexo III)"
    },
    "ANEXO IV": {
        "Descricao": "Produtos de Higiene (Redução 60%)",
        "cClassTrib": "200035", "CST": "20", "Status": "REDUZIDA 60% (Anexo IV)"
    }
    # Adicione mais se necessário
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
    """
    Acessa o site do Planalto, baixa o HTML e separa os NCMs por Anexo.
    """
    url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    # Cabeçalho para não ser bloqueado
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    mapa_ncm_anexo = {}
    
    try:
        # 1. Baixa o site
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # 2. Limpa o HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        texto_limpo = soup.get_text(separator=' ')
        texto_limpo = re.sub(r'\s+', ' ', texto_limpo) # Remove espaços extras
        
        # 3. Mapeamento Inteligente
        # Encontra onde começa cada Anexo no texto gigante
        anexos_encontrados = []
        for anexo in CONFIG_ANEXOS.keys():
            posicao = texto_limpo.upper().find(anexo)
            if posicao != -1:
                anexos_encontrados.append((posicao, anexo))
        
        anexos_encontrados.sort() # Ordena pela posição no texto
        
        # 4. Extrai NCMs de cada bloco
        for i in range(len(anexos_encontrados)):
            nome_anexo = anexos_encontrados[i][1]
            inicio = anexos_encontrados[i][0]
            
            # Define o fim (começo do próximo anexo ou fim do texto)
            if i + 1 < len(anexos_encontrados):
                fim = anexos_encontrados[i+1][0]
            else:
                fim = len(texto_limpo)
            
            bloco_texto = texto_limpo[inicio:fim]
            texto_sem_pontos = bloco_texto.replace('.', '')
            
            # Regex para achar NCMs (8 dígitos) e Capítulos (4 dígitos)
            ncms = re.findall(r'\b\d{8}\b', texto_sem_pontos)
            capitulos = re.findall(r'\b\d{4}\b', texto_sem_pontos)
            
            for n in ncms:
                mapa_ncm_anexo[n] = nome_anexo
            for c in capitulos:
                if c not in mapa_ncm_anexo:
                    mapa_ncm_anexo[c] = nome_anexo
                    
        return mapa_ncm_anexo

    except Exception as e:
        st.error(f"Erro ao conectar no Planalto: {e}")
        return {}

# --- 4. LÓGICA DE CLASSIFICAÇÃO ---

def classificar_item_master(ncm, cfop, produto, df_regras, mapa_anexos):
    ncm_limpo = str(ncm).replace('.', '')
    cfop_limpo = str(cfop).replace('.', '')
    
    # Valores Padrão
    cClassTrib = '000001'
    desc_legal = 'Padrão - Tributação Integral'
    cst = '01'
    status = 'PADRAO'
    origem = 'Regra Geral'
    
    # --- PASSO 1: VERIFICA MAPA DA LEI ONLINE ---
    anexo_encontrado = None
    
    if ncm_limpo in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo]
    elif ncm_limpo[:4] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
    elif ncm_limpo[:2] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:2]]

    # --- PASSO 2: APLICA REGRA ---
    
    if cfop_limpo.startswith('7'):
        return '410004', 'Exportação', 'IMUNE', '50', 'Não'
        
    elif anexo_encontrado:
        # Aplica a regra do dicionário CONFIG_ANEXOS
        regra = CONFIG_ANEXOS[anexo_encontrado]
        cClassTrib = regra['cClassTrib']
        cst = regra['CST']
        status = regra['Status']
        desc_legal = f"{regra['Descricao']} (Fonte: {anexo_encontrado} - Planalto)"
        origem = anexo_encontrado
        
    else:
        # Fallback para o JSON ou regras manuais
        termo_busca = ""
        if ncm_limpo.startswith('30'): termo_busca = "medicamentos"
        elif ncm_limpo.startswith('1006'): termo_busca = "cesta básica"
        else: termo_busca = "tributação integral"
        
        if not df_regras.empty:
            res = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not res.empty:
                cClassTrib = res.iloc[0]['Código da Classificação Tributária']
                desc_legal = res.iloc[0]['Descrição do Código da Classificação Tributária']
                cst = res.iloc[0].get('Código da Situação Tributária', '01')
                status = "SUGESTAO JSON"

    return cClassTrib, desc_legal, status, cst, origem

# --- 5. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.header("📂 Importação")
    uploaded_files = st.file_uploader("XMLs", type=['xml'], accept_multiple_files=True)
    
    st.divider()
    with st.spinner("Conectando ao Planalto e lendo Anexos..."):
        mapa_anexos = mapear_anexos_online()
    
    if mapa_anexos:
        st.success(f"🟢 Planalto Online! {len(mapa_anexos)} NCMs mapeados nos Anexos.")
    else:
        st.warning("⚠️ Não foi possível ler os Anexos do site. Verifique sua conexão.")

if uploaded_files:
    if df_regras.empty:
        st.error("JSON de regras ausente.")
    else:
        lista_produtos = []
        ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
        
        for arquivo in uploaded_files:
            try:
                tree = ET.parse(arquivo)
                root = tree.getroot()
                det_itens = root.findall('.//ns:det', ns)
                for item in det_itens:
                    prod = item.find('ns:prod', ns)
                    lista_produtos.append({
                        'NCM': prod.find('ns:NCM', ns).text,
                        'Produto': prod.find('ns:xProd', ns).text,
                        'CFOP': prod.find('ns:CFOP', ns).text,
                    })
            except: continue
        
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
            
            col1, col2 = st.columns(2)
            col1.metric("Produtos", len(df_analise))
            lei_count = len(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")])
            col2.metric("Enquadrados via Site", lei_count, delta="Online")
            
            st.write("### Resultado da Auditoria")
            
            if lei_count > 0:
                st.info("💡 Produtos identificados nos Anexos do Site do Planalto:")
                st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")], use_container_width=True)
                st.divider()

            st.dataframe(df_analise, use_container_width=True)
            csv = df_analise.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button("Baixar Auditoria.csv", csv, "Auditoria_Online.csv", "text/csv")