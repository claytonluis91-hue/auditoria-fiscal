import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import re
import os

# --- DADOS E REGRAS ---
TEXTO_MESTRA = """
ANEXO I (ZERO)
1006.20 1006.30 1006.40.00 0401.10.10 0401.10.90 0401.20.10 0401.20.90 0401.40.10 0401.50.10
0402.10.10 0402.10.90 0402.21.10 0402.21.20 0402.29.10 0402.29.20 1901.10.10 1901.10.90 2106.90.90
0405.10.00 1517.10.00 0713.33.19 0713.33.29 0713.33.99 0713.35.90 09.01 2101.1 1513.21.20
1106.20.00 1903.00.00 1102.20.00 1103.13.00 1104.19.00 1104.23.00 1101.00.10 1104.12.00 1104.22.00 1102.90.00
1701.14.00 1701.99.00 1902.1 1905.90.90 1901.20.10 1901.20.90
02.01 02.02 02.03 02.04 02.07 0206.2 0206.4 0210.1 03.02 03.03 03.04
0406.10.10 0406.10.90 0406.20.00 0406.90.10 0406.90.20 0406.90.30 2501.00.20 2501.00.90 09.03

ANEXO VII (RED 60%)
0306.1 0306.3 0307 0403 2202.99.00 0409.00.00
1101 1102 1103 1104 1105 1106 1208 1108 1507 1508 1511 1512 1513 1514 1515
1902 2009 2008 1905.90.10 2002 2004 2005
Capítulo 10 Capítulo 12 Capítulo 07 Capítulo 08

ANEXO VIII (RED 60%)
3401 3306 9603.21.00 4818.10.00 9619.00.00

ANEXO XIV (ZERO)
3004 3002

ANEXO XV (ZERO)
0407.2 0701 0702 0703 0704 0705 0706 0708 0709 0710 0803 0804 0805 0806 0807 0808 0809 0810 0811 0714 0801
"""

CONFIG_ANEXOS = {
    "ANEXO I": {"Descricao": "Cesta Básica Nacional", "cClassTrib": "200003", "CST": "40", "Reducao": 1.0, "Status": "ZERO (Anexo I)", "Caps": []},
    "ANEXO IV": {"Descricao": "Dispositivos Médicos", "cClassTrib": "200005", "CST": "20", "Reducao": 0.6, "Status": "REDUZIDA 60% (Anexo IV)", "Caps": ["30","90"]},
    "ANEXO VII": {"Descricao": "Alimentos Reduzidos", "cClassTrib": "200003", "CST": "20", "Reducao": 0.6, "Status": "REDUZIDA 60% (Anexo VII)", "Caps": ["03","04","07","08","10","11","12","15","16","19","20","21","22"]},
    "ANEXO VIII": {"Descricao": "Higiene Pessoal e Limpeza", "cClassTrib": "200035", "CST": "20", "Reducao": 0.6, "Status": "REDUZIDA 60% (Anexo VIII)", "Caps": ["33","34","48","96"]},
    "ANEXO XII": {"Descricao": "Dispositivos Médicos (Zero)", "cClassTrib": "200005", "CST": "40", "Reducao": 1.0, "Status": "ZERO (Anexo XII)", "Caps": ["90"]},
    "ANEXO XIV": {"Descricao": "Medicamentos (Zero)", "cClassTrib": "200009", "CST": "40", "Reducao": 1.0, "Status": "ZERO (Anexo XIV)", "Caps": ["30"]},
    "ANEXO XV": {"Descricao": "Hortifruti e Ovos", "cClassTrib": "200003", "CST": "40", "Reducao": 1.0, "Status": "ZERO (Anexo XV)", "Caps": ["04","06","07","08"]}
}

def carregar_tipi(uploaded_file=None):
    arquivo = uploaded_file if uploaded_file else ("tipi.xlsx" if os.path.exists("tipi.xlsx") else None)
    if not arquivo: return pd.DataFrame()
    try:
        try: df = pd.read_excel(arquivo, dtype=str)
        except: df = pd.read_csv(arquivo, dtype=str, on_bad_lines='skip')
        df['NCM_Limpo'] = df.iloc[:, 0].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
        df = df[df['NCM_Limpo'].str.len().isin([4, 8])]
        return df.set_index('NCM_Limpo')
    except: return pd.DataFrame()

def carregar_json_regras():
    try:
        with open('classificacao_tributaria.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)
            df = pd.DataFrame(dados)
            if 'Descrição do Código da Classificação Tributária' in df.columns:
                df['Busca'] = df['Descrição do Código da Classificação Tributária'].str.lower()
            else: df['Busca'] = ""
            return df
    except: return pd.DataFrame(columns=['Busca'])

def extrair_regras(texto_fonte, mapa_existente, nome_fonte):
    texto = re.sub(r'\s+', ' ', texto_fonte)
    anexos_pos = []
    for anexo in CONFIG_ANEXOS.keys():
        pos = texto.upper().find(anexo)
        if pos != -1: anexos_pos.append((pos, anexo))
    anexos_pos.sort()
    for i in range(len(anexos_pos)):
        nome_anexo = anexos_pos[i][1]
        inicio = anexos_pos[i][0]
        fim = anexos_pos[i+1][0] if i+1 < len(anexos_pos) else len(texto)
        bloco = texto[inicio:fim]
        ncms_raw = re.findall(r'(?<!\d)(\d{2,4}\.?\d{0,2}\.?\d{0,2})(?!\d)', bloco)
        caps = CONFIG_ANEXOS[nome_anexo]["Caps"]
        for codigo in ncms_raw:
            c = codigo.replace('.', '')
            if len(c) in [4,6,8]:
                if not caps or any(c.startswith(cap) for cap in caps):
                    if c not in mapa_existente or nome_fonte == "BACKUP":
                        mapa_existente[c] = nome_anexo
                        if len(c) == 8: mapa_existente[c[:4]] = nome_anexo
                        if len(c) == 6: mapa_existente[c[:4]] = nome_anexo
    return mapa_existente

def carregar_base_legal():
    mapa = {}
    try:
        url = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.content, 'html.parser')
        mapa = extrair_regras(soup.get_text(separator=' '), mapa, "SITE")
    except: pass
    mapa = extrair_regras(TEXTO_MESTRA, mapa, "BACKUP")
    caps_anexo_vii = ['10', '11', '12'] 
    for cap in caps_anexo_vii:
        if cap not in mapa: mapa[cap] = "ANEXO VII"
    return mapa

def verificar_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    return any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93'])

def classificar_item(row, mapa_regras, df_json, df_tipi, aliquota_padrao):
    ncm = str(row['NCM']).replace('.', '')
    cfop = str(row['CFOP']).replace('.', '')
    valor_prod = float(row['Valor'])
    
    v_icms = float(row.get('vICMS', 0))
    v_pis = float(row.get('vPIS', 0))
    v_cofins = float(row.get('vCOFINS', 0))
    imposto_atual = v_icms + v_pis + v_cofins

    base_liquida = valor_prod - imposto_atual
    if base_liquida < 0: base_liquida = 0 
    
    imposto_padrao_projetado = base_liquida * aliquota_padrao
    imposto_futuro = imposto_padrao_projetado

    validacao = "⚠️ NCM Ausente (TIPI)"
    if not df_tipi.empty:
        if ncm in df_tipi.index: validacao = "✅ NCM Válido"
        elif ncm[:4] in df_tipi.index: validacao = "✅ Posição Válida"

    if verificar_seletivo(ncm):
        return '000001', f'Produto sujeito a Imposto Seletivo', 'ALERTA SELETIVO', '02', 'Trava', validacao, imposto_atual, imposto_padrao_projetado

    anexo, origem = None, "Regra Geral"
    for tent in [ncm, ncm[:6], ncm[:4], ncm[:2]]:
        if tent in mapa_regras:
            anexo = mapa_regras[tent]
            origem = f"{anexo} (via {tent})"
            break
            
    if cfop.startswith('7'): 
        return '410004', 'Exportação', 'IMUNE', '50', 'CFOP', validacao, 0.0, 0.0
        
    elif anexo:
        regra = CONFIG_ANEXOS[anexo]
        fator_reducao = regra.get('Reducao', 0.0) 
        imposto_futuro = imposto_padrao_projetado * (1 - fator_reducao)
        return regra['cClassTrib'], f"{regra['Descricao']} - {origem}", regra['Status'], regra['CST'], origem, validacao, imposto_atual, imposto_futuro
    
    else:
        termo = "medicamentos" if ncm.startswith('30') else ("cesta básica" if ncm.startswith('10') else "tributação integral")
        if not df_json.empty and 'Busca' in df_json.columns:
            res = df_json[df_json['Busca'].str.contains(termo, na=False)]
            if not res.empty:
                return res.iloc[0]['Código da Classificação Tributária'], res.iloc[0]['Descrição do Código da Classificação Tributária'], "SUGESTAO JSON", res.iloc[0].get('Código da Situação Tributária', '01'), origem, validacao, imposto_atual, imposto_padrao_projetado

    return '000001', 'Padrão - Tributação Integral', 'PADRAO', '01', origem, validacao, imposto_atual, imposto_padrao_projetado

def processar_xml_detalhado(tree, ns):
    """Extrai dados do XML com foco nos impostos"""
    lista = []
    root = tree.getroot()
    infNFe = root.find('.//ns:infNFe', ns)
    chave = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else 'N/A'
    
    for det in root.findall('.//ns:det', ns):
        prod = det.find('ns:prod', ns)
        c_prod = prod.find('ns:cProd', ns).text
        
        v_icms = 0.0
        v_pis = 0.0
        v_cofins = 0.0
        
        imposto_node = det.find('ns:imposto', ns)
        if imposto_node is not None:
            for child in imposto_node.iter():
                tag_name = child.tag.split('}')[-1] 
                if tag_name in ['vICMS', 'vICMSSN']: v_icms += float(child.text)
                elif tag_name == 'vPIS': v_pis += float(child.text)
                elif tag_name == 'vCOFINS': v_cofins += float(child.text)

        lista.append({
            'Cód. Produto': c_prod,
            'Chave NFe': chave,
            'NCM': prod.find('ns:NCM', ns).text,
            'Produto': prod.find('ns:xProd', ns).text,
            'CFOP': prod.find('ns:CFOP', ns).text,
            'Valor': float(prod.find('ns:vProd', ns).text),
            'vICMS': v_icms,
            'vPIS': v_pis,
            'vCOFINS': v_cofins
        })
    return lista