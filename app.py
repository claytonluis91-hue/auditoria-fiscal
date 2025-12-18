import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - Reforma Tributária",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Auditoria Fiscal & Análise Legal")
st.markdown("Auditoria de XMLs cruzando NCM, CFOP e Texto da LCP 214/2025.")
st.divider()

# --- 2. CARREGAMENTO DE DADOS ---

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
def carregar_texto_lei_online():
    # URL Oficial
    url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    
    # Headers para fingir ser um navegador (evita bloqueio)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Timeout de 10s para não ficar travado para sempre
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
            # Limpeza pesada do texto
            texto = soup.get_text(separator=' ')
            texto = re.sub(r'\s+', ' ', texto).lower()
            return texto
        else:
            return None
    except:
        return None

# --- 3. LÓGICA DE INTELIGÊNCIA ---

def limpar_descricao(descricao):
    # Pega apenas a primeira palavra significativa (ex: "Absorvente" de "Absorvente Intimus")
    # Isso aumenta a chance de achar na lei
    desc = descricao.lower()
    desc = re.sub(r'[0-9]', '', desc) 
    desc = desc.replace('.', '').replace('-', '')
    
    palavras_ignoradas = ['kg', 'un', 'pct', 'cx', 'lt', 'ml', 'g', 'pote', 'vidro', 'saco']
    palavras = [p for p in desc.split() if p not in palavras_ignoradas and len(p) > 3]
    
    if palavras:
        return palavras[0] # Retorna a primeira palavra forte (Ex: "arroz", "feijao", "absorvente")
    return ""

def verificar_na_lei(produto, texto_lei):
    if not texto_lei:
        return "-"
    
    termo_busca = limpar_descricao(produto)
    
    if len(termo_busca) < 4: 
        return "-"

    # Busca a palavra no texto da lei
    if termo_busca in texto_lei:
        index = texto_lei.find(termo_busca)
        inicio = max(0, index - 60)
        fim = min(len(texto_lei), index + 60)
        trecho = texto_lei[inicio:fim]
        return f"...{trecho}..."
    
    return "-"

def classificar_item(ncm, cfop, df_regras):
    ncm = str(ncm)
    cfop = str(cfop).replace('.', '')
    
    termo_busca = ""
    status = "PADRAO" 

    # --- REGRAS DE NCM E CFOP (AQUI ESTÁ A CORREÇÃO DO ABSORVENTE) ---
    
    # 1. Exportação / Zona Franca / Remessas
    if cfop.startswith('7'): 
        termo_busca = "exportação"
        status = "IMUNE"
    elif cfop in ['6109', '6110', '5109', '5110']:
        termo_busca = "zona franca"
        status = "BENEFICIO"
    elif cfop in ['5901', '5902', '5949', '6901']:
        return '-', 'Remessa/Devolução', 'OUTROS', '999'
    
    # 2. Produtos Específicos (Pelo começo do NCM)
    elif ncm.startswith('30'):
        termo_busca = "medicamentos"
        status = "REDUZIDA"
    elif ncm.startswith('9619'): # <--- ADICIONADO: Absorventes e Fraldas
        termo_busca = "higiene pessoal" # Ou "absorventes" se tiver no JSON
        status = "REDUZIDA"
    elif ncm.startswith('1006') or ncm.startswith('02') or ncm.startswith('1101'):
        termo_busca = "cesta básica"
        status = "ZERO"
    elif ncm.startswith('3304') or ncm.startswith('3401'):
        termo_busca = "higiene"
        status = "REDUZIDA"
    elif ncm.startswith('2710'):
        termo_busca = "combustíveis"
        status = "MONOFASICA"
    else:
        termo_busca = "tributação integral"
        status = "PADRAO"

    if not df_regras.empty:
        # Busca parcial no JSON
        resultado = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
        if not resultado.empty:
            codigo = resultado.iloc[0]['Código da Classificação Tributária']
            desc = resultado.iloc[0]['Descrição do Código da Classificação Tributária']
            cst = resultado.iloc[0].get('Código da Situação Tributária', '?')
            return codigo, desc, status, cst
    
    return 'VERIFICAR', f'Regra não achada: {termo_busca}', 'ATENCAO', '?'

# --- 4. INTERFACE ---
df_regras = carregar_regras()

# Carrega a lei no início
with st.spinner('Conectando ao Planalto...'):
    texto_lei = carregar_texto_lei_online()

# Sidebar Inteligente
with st.sidebar:
    st.header("📂 Arquivos")
    uploaded_files = st.file_uploader("XMLs de Venda", type=['xml'], accept_multiple_files=True)
    
    st.divider()
    st.subheader("Status do Sistema")
    
    if not df_regras.empty:
        st.success("✅ Regras JSON: Carregado")
    else:
        st.error("❌ Regras JSON: Não encontrado")

    # Mostra o status REAL da conexão
    if texto_lei:
        st.success("🟢 Planalto (LCP 214): Conectado")
    else:
        st.error("🔴 Planalto (LCP 214): Falha/Offline")
        st.caption("Verifique sua internet ou o site do governo.")

# Lógica Principal
if uploaded_files:
    if df_regras.empty:
        st.error("Falta o arquivo classificacao_tributaria.json")
    else:
        # Processamento
        lista_produtos = []
        ns = {'ns': 'http://www.portalfiscal.inf.br/nfe'}
        
        for arquivo in uploaded_files:
            try:
                tree = ET.parse(arquivo)
                root = tree.getroot()
                det_itens = root.findall('.//ns:det', ns)
                for item in det_itens:
                    prod = item.find('ns:prod', ns)
                    try: vProd = float(prod.find('ns:vProd', ns).text)
                    except: vProd = 0.0
                    lista_produtos.append({
                        'NCM': prod.find('ns:NCM', ns).text,
                        'Produto': prod.find('ns:xProd', ns).text,
                        'CFOP': prod.find('ns:CFOP', ns).text,
                        'Valor': vProd
                    })
            except: continue
        
        df_base = pd.DataFrame(lista_produtos)
        
        if not df_base.empty:
            df_analise = df_base.drop_duplicates(subset=['NCM', 'Produto', 'CFOP']).copy()
            
            # Classificação
            resultados = df_analise.apply(
                lambda row: classificar_item(row['NCM'], row['CFOP'], df_regras), axis=1, result_type='expand'
            )
            df_analise['Novo cClassTrib'] = resultados[0]
            df_analise['Descrição Legal'] = resultados[1]
            df_analise['Status'] = resultados[2]
            df_analise['Novo CST'] = resultados[3]
            
            # Busca na Lei (Só se estiver conectado)
            if texto_lei:
                df_analise['Citado na Lei?'] = df_analise['Produto'].apply(lambda x: verificar_na_lei(x, texto_lei))
            else:
                df_analise['Citado na Lei?'] = "Offline"
            
            # Métricas
            col1, col2 = st.columns(2)
            col1.metric("Produtos Analisados", len(df_analise))
            achados = len(df_analise[df_analise['Citado na Lei?'].str.len() > 10]) # Filtra quem achou texto
            col2.metric("Termos achados na Lei", achados)
            
            # Exibição
            st.write("### Auditoria Detalhada")
            
            # Filtro para destacar o que foi achado na lei
            if achados > 0:
                with st.expander("🔎 Ver produtos encontrados no texto da Lei (Clique aqui)"):
                    st.dataframe(df_analise[df_analise['Citado na Lei?'].str.len() > 10][['Produto', 'Citado na Lei?']], use_container_width=True)

            st.dataframe(df_analise, use_container_width=True)
            
            csv = df_analise.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button("📥 Baixar Relatório Final", csv, "Auditoria.csv", "text/csv")

        else:
            st.warning("Nenhum dado encontrado.")