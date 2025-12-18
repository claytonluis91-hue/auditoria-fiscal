import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - Reforma Tributária (Live)",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Auditoria Fiscal & Análise Legal (Online)")
st.markdown("""
**Versão Conectada:** O sistema busca as regras no JSON e cruza com o texto oficial da **LCP 214/2025** direto do site do Planalto.
""")
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
    # URL Oficial da Lei Complementar 214
    url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Garante que o site respondeu
        
        # Limpeza do HTML (BeautifulSoup)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove scripts e estilos CSS para pegar só o texto puro
        for script in soup(["script", "style"]):
            script.extract()
            
        texto_limpo = soup.get_text(separator=' ')
        
        # Remove excesso de espaços
        texto_limpo = re.sub(r'\s+', ' ', texto_limpo).lower()
        
        return texto_limpo
    except Exception as e:
        st.error(f"Erro ao acessar site do Planalto: {e}")
        return None

# --- 3. LÓGICA DE INTELIGÊNCIA ---

def limpar_descricao(descricao):
    desc = descricao.lower()
    desc = re.sub(r'[0-9]', '', desc) 
    desc = desc.replace('.', '').replace('-', '')
    palavras_ignoradas = ['kg', 'un', 'pct', 'cx', 'lt', 'ml', 'g', 'garrafa', 'pote']
    palavras = [p for p in desc.split() if p not in palavras_ignoradas and len(p) > 2]
    return " ".join(palavras)

def verificar_na_lei(produto, texto_lei):
    if not texto_lei:
        return "-"
    
    termo_busca = limpar_descricao(produto)
    
    if len(termo_busca) < 4: # Ignora palavras muito curtas
        return "-"

    if termo_busca in texto_lei:
        index = texto_lei.find(termo_busca)
        inicio = max(0, index - 80)
        fim = min(len(texto_lei), index + 80)
        trecho = texto_lei[inicio:fim]
        return f"...{trecho}..."
    
    return "-"

def classificar_item(ncm, cfop, df_regras):
    ncm = str(ncm)
    cfop = str(cfop).replace('.', '')
    
    termo_busca = ""
    status = "PADRAO" 

    if cfop.startswith('7'): 
        termo_busca = "exportação"
        status = "IMUNE"
    elif cfop in ['6109', '6110', '5109', '5110']:
        termo_busca = "zona franca"
        status = "BENEFICIO"
    elif cfop in ['5901', '5902', '5949', '6901']:
        return '-', 'Remessa/Devolução', 'OUTROS', '999'
        
    elif ncm.startswith('30'):
        termo_busca = "medicamentos"
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
        resultado = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
        if not resultado.empty:
            codigo = resultado.iloc[0]['Código da Classificação Tributária']
            desc = resultado.iloc[0]['Descrição do Código da Classificação Tributária']
            cst = resultado.iloc[0].get('Código da Situação Tributária', '?')
            return codigo, desc, status, cst
    
    return 'VERIFICAR', f'Regra não achada: {termo_busca}', 'ATENCAO', '?'

# --- 4. INTERFACE ---
with st.sidebar:
    st.header("📂 Arquivos")
    uploaded_files = st.file_uploader("XMLs de Venda", type=['xml'], accept_multiple_files=True)
    st.success("🟢 Conectado à Base Legal do Planalto")

df_regras = carregar_regras()
texto_lei = carregar_texto_lei_online() # Acessa a internet aqui

if uploaded_files:
    if df_regras.empty:
        st.error("🚨 JSON de regras não encontrado.")
    else:
        with st.spinner('Lendo XMLs e Baixando Lei do Planalto...'):
            # Processamento dos XMLs
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
                
                # Busca na Lei Online
                if texto_lei:
                    df_analise['Citado na Lei 214?'] = df_analise['Produto'].apply(lambda x: verificar_na_lei(x, texto_lei))
                
                # Exibição
                col1, col2 = st.columns(2)
                col1.metric("Produtos Processados", len(df_analise))
                
                # Conta quantos foram achados na lei
                achados_lei = len(df_analise[df_analise['Citado na Lei 214?'] != "-"])
                col2.metric("Produtos Citados na Lei", achados_lei, delta="Atenção" if achados_lei > 0 else None)
                
                if achados_lei > 0:
                    st.info("🔎 Encontramos termos exatos na Lei para os produtos abaixo:")
                    st.dataframe(df_analise[df_analise['Citado na Lei 214?'] != "-"][['Produto', 'Citado na Lei 214?']], use_container_width=True)
                
                st.write("### Análise Completa")
                st.dataframe(df_analise, use_container_width=True)
                
                csv = df_analise.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
                st.download_button("📥 Baixar Relatório", csv, "Auditoria_Online.csv", "text/csv")
            else:
                st.warning("Nenhum dado encontrado.")