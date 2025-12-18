import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - Reforma Tributária (Raio-X)",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Auditoria Fiscal & Anexos da Lei")
st.markdown("Auditoria cruzando XMLs com regras de negócio e **varredura de NCMs citados na LCP 214**.")
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
def carregar_ncm_da_lei_online():
    """
    Esta função vai no site do Planalto, baixa o texto e extrai TODOS os NCMs citados lá.
    Retorna uma lista de NCMs que possuem benefícios ou regras específicas.
    """
    url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    lista_ncms_lei = set() # Usamos set para não repetir
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
            texto = soup.get_text(separator=' ')
            
            # --- O PULO DO GATO: REGEX ---
            # Procura padrões de NCM: 4 a 8 dígitos, as vezes com ponto
            # Ex: 1006.30, 3004, 96190000
            # O padrão abaixo busca números de 4 a 8 digitos próximos a palavra NCM ou soltos em tabelas
            
            # Limpa pontos para padronizar
            texto_limpo = texto.replace('.', '') 
            
            # Busca sequências de 8 números (NCM completo)
            ncms_encontrados = re.findall(r'\b\d{8}\b', texto_limpo)
            lista_ncms_lei.update(ncms_encontrados)
            
            # Busca sequências de 4 números (Capítulos/Posições citadas, ex: 3004)
            capitulos_encontrados = re.findall(r'\b\d{4}\b', texto_limpo)
            lista_ncms_lei.update(capitulos_encontrados)
            
            return lista_ncms_lei
        else:
            return set()
    except:
        return set()

# --- 3. LÓGICA DE INTELIGÊNCIA ---

def classificar_item_avancado(ncm, cfop, produto, df_regras, ncms_da_lei):
    ncm = str(ncm).replace('.', '')
    cfop = str(cfop).replace('.', '')
    
    termo_busca = ""
    status = "PADRAO" 
    origem_regra = "Regra Geral"

    # --- FASE 1: CONFIRMAÇÃO NA LEI (PRIORIDADE MÁXIMA) ---
    # Se o NCM exato (8 dígitos) ou o Capítulo (4 primeiros) estiver na Lei, é exceção!
    
    citado_na_lei = False
    if ncm in ncms_da_lei:
        citado_na_lei = True
    elif ncm[:4] in ncms_da_lei: # Verifica os 4 primeiros dígitos (Ex: 3004)
        citado_na_lei = True
        
    # --- FASE 2: REGRAS DE NEGÓCIO ---
    
    # 1. Operações (CFOP)
    if cfop.startswith('7'): 
        termo_busca = "exportação"
        status = "IMUNE"
    elif cfop in ['6109', '6110', '5109', '5110']:
        termo_busca = "zona franca"
        status = "BENEFICIO"
    elif cfop in ['5901', '5902', '5949', '6901']:
        return '-', 'Remessa/Devolução', 'OUTROS', '999', 'Não'
    
    # 2. Produtos (NCM) - Agora turbinado com a checagem da Lei
    else:
        # Se foi citado na lei, força uma busca por exceção
        if citado_na_lei:
            origem_regra = "Encontrado na LCP 214"
            # Tenta inferir o tipo pela família do NCM para buscar no JSON
            if ncm.startswith('30'): termo_busca = "medicamentos"
            elif ncm.startswith('9619'): termo_busca = "higiene"
            elif ncm.startswith('10') or ncm.startswith('02'): termo_busca = "cesta básica"
            elif ncm.startswith('87'): termo_busca = "veículos"
            else: 
                # Se achou na lei mas não sabemos o que é, marca para atenção
                return 'VERIFICAR NA LEI', 'NCM citado no texto legal - Verificar Anexo', 'ATENCAO LEI', '?', 'Sim'
                
        # Se NÃO foi citado na lei explicitamente, segue regra padrão
        else:
            if ncm.startswith('30'): termo_busca = "medicamentos"; status="REDUZIDA"
            elif ncm.startswith('1006'): termo_busca = "cesta básica"; status="ZERO"
            else:
                termo_busca = "tributação integral"
                status = "PADRAO"

    # --- FASE 3: BUSCA NO JSON ---
    if termo_busca:
        if not df_regras.empty:
            # Busca parcial
            resultado = df_regras[df_regras['Busca'].str.contains(termo_busca, na=False)]
            if not resultado.empty:
                codigo = resultado.iloc[0]['Código da Classificação Tributária']
                desc = resultado.iloc[0]['Descrição do Código da Classificação Tributária']
                cst = resultado.iloc[0].get('Código da Situação Tributária', '?')
                
                # Se veio da lei, o status muda
                if citado_na_lei and status == "PADRAO": status = "REDUZIDA (LEI)"
                
                return codigo, desc, status, cst, "Sim" if citado_na_lei else "Não"
    
    return '000001', 'Padrão - Tributação Integral', 'PADRAO', '01', 'Não'

# --- 4. INTERFACE ---
df_regras = carregar_regras()

with st.sidebar:
    st.header("📂 Arquivos")
    uploaded_files = st.file_uploader("XMLs", type=['xml'], accept_multiple_files=True)
    
    with st.spinner("Baixando NCMs da Lei..."):
        lista_ncms_lei = carregar_ncm_da_lei_online()
    
    if lista_ncms_lei:
        st.success(f"🟢 LCP 214 Mapeada: {len(lista_ncms_lei)} NCMs identificados no texto.")
    else:
        st.warning("🔴 Falha ao ler NCMs do site.")

if uploaded_files:
    if df_regras.empty:
        st.error("Falta JSON.")
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
            
            # APLICA A NOVA CLASSIFICAÇÃO
            resultados = df_analise.apply(
                lambda row: classificar_item_avancado(row['NCM'], row['CFOP'], row['Produto'], df_regras, lista_ncms_lei), 
                axis=1, result_type='expand'
            )
            
            df_analise['Novo cClassTrib'] = resultados[0]
            df_analise['Descrição'] = resultados[1]
            df_analise['Status'] = resultados[2]
            df_analise['Novo CST'] = resultados[3]
            df_analise['Consta na Lei?'] = resultados[4]
            
            col1, col2 = st.columns(2)
            col1.metric("Itens Analisados", len(df_analise))
            col2.metric("NCMs Citados na Lei", len(df_analise[df_analise['Consta na Lei?']=='Sim']), delta="Benefício Provável")
            
            st.dataframe(df_analise, use_container_width=True)
            
            csv = df_analise.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button("Baixar Relatório", csv, "Auditoria_Anexos.csv", "text/csv")