import streamlit as st
import pandas as pd
import json
import xml.etree.ElementTree as ET
from pypdf import PdfReader
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Fiscal - Reforma Tributária (Anexos)",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Auditoria Fiscal: Leitor de Anexos (LCP 214)")
st.markdown("O sistema identifica em **qual Anexo da Lei** o NCM está e aplica o CST/cClassTrib correspondente.")
st.divider()

# --- 2. CONFIGURAÇÃO DE INTELIGÊNCIA (O CÉREBRO) ---
# Aqui definimos o que cada Anexo significa em termos de tributação
# ATENÇÃO: Ajuste os códigos 'cClassTrib' e 'CST' conforme o seu JSON ou entendimento da lei
CONFIG_ANEXOS = {
    "ANEXO I": {
        "Descricao": "Cesta Básica Nacional (Alíquota Zero)",
        "cClassTrib": "200003", 
        "CST": "40", # Isenta/Não Tributada
        "Status": "ZERO (Anexo I)"
    },
    "ANEXO II": {
        "Descricao": "Medicamentos (Redução 60%)",
        "cClassTrib": "200009", 
        "CST": "20", # Com redução
        "Status": "REDUZIDA 60% (Anexo II)"
    },
    "ANEXO III": {
        "Descricao": "Dispositivos Médicos (Redução 60%)",
        "cClassTrib": "200005", 
        "CST": "20",
        "Status": "REDUZIDA 60% (Anexo III)"
    },
    "ANEXO IV": {
        "Descricao": "Produtos de Higiene (Redução 60%)",
        "cClassTrib": "200035", 
        "CST": "20",
        "Status": "REDUZIDA 60% (Anexo IV)"
    },
    # Adicione outros anexos se necessário (V, VI, etc)
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
def mapear_ncms_por_anexo_pdf():
    """
    Lê o PDF e cria um dicionário: {'100630': 'ANEXO I', '3004': 'ANEXO II'}
    """
    nome_ficheiro = "Lcp 214.pdf"
    mapa_ncm_anexo = {}
    
    try:
        reader = PdfReader(nome_ficheiro)
        texto_completo = ""
        for page in reader.pages:
            texto_completo += page.extract_text() + "\n"
        
        # Limpeza básica
        texto_limpo = re.sub(r'\n+', ' ', texto_completo)
        
        # Estratégia: Dividir o texto pelos cabeçalhos dos Anexos
        # Vamos procurar onde começa cada anexo
        # Atenção: A ordem da lista importa (do último para o primeiro ajuda no fatiamento, ou split)
        
        anexos_encontrados = []
        for anexo in CONFIG_ANEXOS.keys():
            # Procura "ANEXO I", "ANEXO II" no texto (case insensitive)
            posicao = texto_limpo.upper().find(anexo)
            if posicao != -1:
                anexos_encontrados.append((posicao, anexo))
        
        # Ordena pelo local onde aparece no texto
        anexos_encontrados.sort()
        
        # Agora varre os blocos de texto
        for i in range(len(anexos_encontrados)):
            nome_anexo = anexos_encontrados[i][1]
            inicio = anexos_encontrados[i][0]
            
            # O fim é o início do próximo anexo, ou o fim do arquivo
            if i + 1 < len(anexos_encontrados):
                fim = anexos_encontrados[i+1][0]
            else:
                fim = len(texto_limpo)
            
            # Extrai o texto só daquele anexo
            texto_do_anexo = texto_limpo[inicio:fim]
            
            # Extrai NCMs (8 dígitos) e Capítulos (4 dígitos) deste bloco
            texto_sem_pontos = texto_do_anexo.replace('.', '')
            ncms = re.findall(r'\b\d{8}\b', texto_sem_pontos)
            capitulos = re.findall(r'\b\d{4}\b', texto_sem_pontos)
            
            # Grava no dicionário mestre
            for n in ncms:
                mapa_ncm_anexo[n] = nome_anexo
            for c in capitulos:
                if c not in mapa_ncm_anexo: # Prioriza NCM completo se já existir
                    mapa_ncm_anexo[c] = nome_anexo
                    
        return mapa_ncm_anexo
        
    except FileNotFoundError:
        st.warning(f"⚠️ Ficheiro '{nome_ficheiro}' não encontrado.")
        return {}
    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
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
    
    # --- PASSO 1: VERIFICA SE ESTÁ EM ALGUM ANEXO DA LEI ---
    anexo_encontrado = None
    
    # Tenta NCM completo (8 dígitos)
    if ncm_limpo in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo]
    # Tenta Capítulo (4 dígitos)
    elif ncm_limpo[:4] in mapa_anexos:
        anexo_encontrado = mapa_anexos[ncm_limpo[:4]]
    # Tenta Posição (2 dígitos - mais arriscado, mas possível para cap 30)
    elif ncm_limpo[:2] in mapa_anexos: # Ex: Capítulo 30 inteiro no anexo
        anexo_encontrado = mapa_anexos[ncm_limpo[:2]]

    # --- PASSO 2: APLICA A REGRA DO ANEXO OU DO CFOP ---
    
    # Prioridade para Imunidade/Exportação (CFOP ganha de NCM)
    if cfop_limpo.startswith('7'):
        return '410004', 'Exportação', 'IMUNE', '50', 'Não' # CST 50 suspensão/saída
        
    elif anexo_encontrado:
        # BINGO! Achou na lei
        regra = CONFIG_ANEXOS[anexo_encontrado]
        cClassTrib = regra['cClassTrib']
        cst = regra['CST']
        status = regra['Status']
        desc_legal = f"{regra['Descricao']} (Encontrado via {anexo_encontrado})"
        origem = anexo_encontrado
        
    else:
        # Se não achou na lei, tenta a sorte no JSON por palavras-chave (Fallback)
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
    with st.spinner("Mapeando Lei..."):
        # Executa o scanner do PDF
        mapa_anexos = mapear_ncms_por_anexo_pdf()
    
    if mapa_anexos:
        st.success(f"📘 Lei Mapeada! {len(mapa_anexos)} NCMs distribuídos nos Anexos.")
        # Debug: Mostra alguns exemplos
        with st.expander("Ver Mapeamento"):
            st.write(list(mapa_anexos.items())[:10])
    else:
        st.warning("O PDF da lei não foi processado corretamente ou não tem NCMs explícitos.")

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
            
            # APLICA CLASSIFICAÇÃO COM O MAPA DE ANEXOS
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
            col2.metric("Enquadrados nos Anexos", lei_count, delta="Alta Precisão")
            
            st.write("### Resultado da Auditoria Cruzada")
            
            # Filtro rápido
            if lei_count > 0:
                st.info("💡 Produtos abaixo foram encontrados diretamente nas tabelas de Anexos da Lei:")
                st.dataframe(df_analise[df_analise['Origem Legal'].str.contains("ANEXO")], use_container_width=True)
                st.divider()

            st.dataframe(df_analise, use_container_width=True)
            
            csv = df_analise.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button("Baixar Auditoria.csv", csv, "Auditoria_Anexos.csv", "text/csv")