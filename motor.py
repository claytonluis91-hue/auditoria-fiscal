import pandas as pd
import json
import xml.etree.ElementTree as ET
import requests
import os
import re
import io

# --- 1. MAPA DE INTELIGÊNCIA (CSTs Baseados no JSON) ---
MAPA_CST_CORRETO = {
    "200003": "200", "200004": "200", "200005": "200", 
    "200009": "200", "200010": "200", "200014": "200",
    "200022": "200", "200030": "200", "200032": "200", 
    "200034": "200", "200035": "200",
    "000001": "000", "000002": "000", "000003": "000",
    "410001": "410", "410003": "410", "410004": "410", "410999": "410",
    "400001": "400", "550001": "550", "550020": "550",
    "510001": "510", "620001": "620"
}

# --- 2. DADOS E REGRAS (MANTIDOS) ---
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
    "ANEXO I":   {"Descricao": "Cesta Básica Nacional", "cClassTrib": "200003", "Reducao": 1.0, "CST_Default": "200", "Status": "ZERO (Anexo I)", "Caps": []},
    "ANEXO IV":  {"Descricao": "Dispositivos Médicos", "cClassTrib": "200005", "Reducao": 0.6, "CST_Default": "200", "Status": "REDUZIDA 60% (Anexo IV)", "Caps": ["30","90"]},
    "ANEXO VII": {"Descricao": "Alimentos Reduzidos", "cClassTrib": "200034", "Reducao": 0.6, "CST_Default": "200", "Status": "REDUZIDA 60% (Anexo VII)", "Caps": ["03","04","07","08","10","11","12","15","16","19","20","21","22"]},
    "ANEXO VIII":{"Descricao": "Higiene Pessoal/Limp", "cClassTrib": "200035", "Reducao": 0.6, "CST_Default": "200", "Status": "REDUZIDA 60% (Anexo VIII)", "Caps": ["33","34","48","96"]},
    "ANEXO XII": {"Descricao": "Dispositivos Médicos (Z)", "cClassTrib": "200004", "Reducao": 1.0, "CST_Default": "200", "Status": "ZERO (Anexo XII)", "Caps": ["90"]},
    "ANEXO XIV": {"Descricao": "Medicamentos (Zero)", "cClassTrib": "200009", "Reducao": 1.0, "CST_Default": "200", "Status": "ZERO (Anexo XIV)", "Caps": ["30"]},
    "ANEXO XV":  {"Descricao": "Hortifruti e Ovos", "cClassTrib": "200014", "Reducao": 1.0, "CST_Default": "200", "Status": "ZERO (Anexo XV)", "Caps": ["04","06","07","08"]}
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
            df = pd.DataFrame(dados, dtype=str)
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
    return mapa_existente

def carregar_base_legal():
    mapa = {}
    mapa = extrair_regras(TEXTO_MESTRA, mapa, "BACKUP")
    caps_anexo_vii = ['10', '11', '12'] 
    for cap in caps_anexo_vii:
        if cap not in mapa: mapa[cap] = "ANEXO VII"
    return mapa

def verificar_seletivo(ncm):
    ncm = str(ncm).replace('.', '')
    return any(ncm.startswith(p) for p in ['2203','2204','2205','2206','2207','2208','24','87','93'])

def obter_cst_final(c_class_trib, df_json):
    c_class_trib = str(c_class_trib).strip()
    if c_class_trib in MAPA_CST_CORRETO:
        return MAPA_CST_CORRETO[c_class_trib]
    if not df_json.empty:
        col_class = 'Código da Classificação Tributária'
        col_cst = 'Código da Situação Tributária'
        if col_class in df_json.columns and col_cst in df_json.columns:
            match = df_json[df_json[col_class].str.strip() == c_class_trib]
            if not match.empty:
                return str(match.iloc[0][col_cst]).strip()
    return '000'

def classificar_item(row, mapa_regras, df_json, df_tipi, aliq_ibs, aliq_cbs):
    ncm = str(row['NCM']).replace('.', '')
    cfop_raw = str(row['CFOP']).replace('.', '') if 'CFOP' in row else '0000'
    cfop = cfop_raw
    
    valor_prod = float(row.get('Valor', 0.0))
    tipo_op = row.get('Tipo', 'SAIDA')
    
    v_icms = float(row.get('vICMS', 0))
    v_pis = float(row.get('vPIS', 0))
    v_cofins = float(row.get('vCOFINS', 0))
    imposto_atual = v_icms + v_pis + v_cofins
    
    base_liquida = max(0, valor_prod - imposto_atual)
    ibs_padrao = base_liquida * aliq_ibs
    cbs_padrao = base_liquida * aliq_cbs
    
    validacao = "⚠️ NCM Ausente (TIPI)"
    if ncm == 'SEM_DETALHE': validacao = "ℹ️ SPED Perfil B"
    elif not df_tipi.empty:
        if ncm in df_tipi.index: validacao = "✅ NCM Válido"
        elif ncm[:4] in df_tipi.index: validacao = "✅ Posição Válida"

    cfops_bonificacao = ['1910', '2910', '5910', '6910']
    cfops_amostra = ['1911', '2911', '5911', '6911', '5912', '6912', '5913', '6913']
    cfops_suspensao = ['5901', '6901', '5902', '6902', '5915', '6915', '5916', '6916']
    cfops_zfm = ['5109', '6109', '5110', '6110']
    cfops_export = ['7101', '7102', '7127', '7501', '7930', '7949'] 

    cClassTrib = '000001'
    desc_final = 'Padrão - Tributação Integral'
    status_final = 'PADRAO'
    cst_final = '000'
    origem_final = "Regra Geral"
    v_ibs_final = ibs_padrao
    v_cbs_final = cbs_padrao

    anexo_encontrado = None
    for tent in [ncm, ncm[:6], ncm[:4], ncm[:2]]:
        if tent in mapa_regras:
            anexo_encontrado = mapa_regras[tent]
            origem_final = f"{anexo_encontrado} (via {tent})"
            break
            
    if anexo_encontrado:
        regra = CONFIG_ANEXOS[anexo_encontrado]
        cClassTrib = regra['cClassTrib']
        desc_final = regra['Descricao']
        status_final = regra['Status']
        fator = regra.get('Reducao', 0.0)
        v_ibs_final = ibs_padrao * (1 - fator)
        v_cbs_final = cbs_padrao * (1 - fator)
        cst_final = obter_cst_final(cClassTrib, df_json)

    if cfop in cfops_zfm:
        cClassTrib = '200022' 
        desc_final = f"Venda Incentivada ZFM (Lei Comp. 214/2025)"
        status_final = 'REDUZIDA 100% (ZFM) *Se ALC: Usar CST 550 / cClass 550020' 
        cst_final = '200' 
        origem_final = "Regra ZFM/JSON"
        v_ibs_final = 0.0
        v_cbs_final = 0.0

    elif cfop.startswith('7') or cfop in cfops_export:
        cClassTrib = '410004'
        desc_final = "Exportação de Bens e Serviços"
        status_final = 'IMUNE (EXP)'
        cst_final = '410'
        origem_final = "Regra Exportação/JSON"
        v_ibs_final = 0.0
        v_cbs_final = 0.0

    elif cfop in cfops_bonificacao:
        cClassTrib = '410001'
        desc_final = f"Bonificação (CFOP {cfop})"
        status_final = 'NÃO INCIDÊNCIA'
        cst_final = '410'
        origem_final = "Regra Bonificação/JSON"
        v_ibs_final = 0.0
        v_cbs_final = 0.0

    elif cfop in cfops_amostra:
        cClassTrib = '410999'
        desc_final = f"Op. Não Onerosa (Amostra/Brinde)"
        status_final = 'ZERO (Genérico)'
        cst_final = '410'
        origem_final = "Regra CFOP"
        v_ibs_final = 0.0
        v_cbs_final = 0.0

    elif cfop in cfops_suspensao:
        cClassTrib = '410999' 
        desc_final = f"Suspensão/Retorno (CFOP {cfop})"
        status_final = 'ZERO (Suspensão)'
        cst_final = '410' 
        origem_final = "Regra CFOP"
        v_ibs_final = 0.0
        v_cbs_final = 0.0

    cfop_base = cfop[1:]
    eh_uso_consumo = cfop_base in ['556', '407', '551', '406']
    if tipo_op == 'ENTRADA' and eh_uso_consumo:
         return '000001', 'Crédito de Uso/Consumo ou Ativo', 'CREDITO PERMITIDO', '000', f'CFOP {cfop}', validacao, 0.0, ibs_padrao+cbs_padrao, ibs_padrao, cbs_padrao

    if verificar_seletivo(ncm):
        return '000001', 'Produto sujeito a Seletivo', 'ALERTA SELETIVO', '002', 'Trava Seletivo', validacao, imposto_atual, v_ibs_final+v_cbs_final, v_ibs_final, v_cbs_final

    imposto_futuro = v_ibs_final + v_cbs_final
    return cClassTrib, desc_final, status_final, cst_final, origem_final, validacao, imposto_atual, imposto_futuro, v_ibs_final, v_cbs_final

def extrair_nome_empresa_xml(tree, ns):
    root = tree.getroot()
    emit = root.find('.//ns:emit', ns)
    if emit is not None:
        xNome = emit.find('ns:xNome', ns)
        if xNome is not None: return xNome.text
    return "Empresa Desconhecida"

def processar_xml_detalhado(tree, ns, tipo_op='SAIDA'):
    lista = []
    root = tree.getroot()
    infNFe = root.find('.//ns:infNFe', ns)
    chave = 'N/A'
    num_nfe = 'N/A' # NOVO: Captura Número
    
    if infNFe is not None:
        chave = infNFe.attrib.get('Id', '')[3:]
        ide = infNFe.find('ns:ide', ns)
        if ide is not None:
            nNF = ide.find('ns:nNF', ns)
            if nNF is not None: num_nfe = nNF.text

    for det in root.findall('.//ns:det', ns):
        prod = det.find('ns:prod', ns)
        c_prod = prod.find('ns:cProd', ns).text
        v_icms = 0.0; v_pis = 0.0; v_cofins = 0.0
        imposto_node = det.find('ns:imposto', ns)
        if imposto_node is not None:
            for child in imposto_node.iter():
                tag_name = child.tag.split('}')[-1] 
                if tag_name in ['vICMS', 'vICMSSN']: v_icms += float(child.text)
                elif tag_name == 'vPIS': v_pis += float(child.text)
                elif tag_name == 'vCOFINS': v_cofins += float(child.text)
        lista.append({
            'Cód. Produto': c_prod, 'Chave NFe': chave, 'Num NFe': num_nfe, # Adicionado
            'NCM': prod.find('ns:NCM', ns).text,
            'Produto': prod.find('ns:xProd', ns).text, 'CFOP': prod.find('ns:CFOP', ns).text,
            'Valor': float(prod.find('ns:vProd', ns).text), 'vICMS': v_icms, 'vPIS': v_pis, 'vCOFINS': v_cofins, 'Tipo': tipo_op
        })
    return lista

def to_float(val):
    try: return float(val.replace(',', '.'))
    except: return 0.0

def processar_sped_fiscal(arquivo):
    vendas = []
    compras = []
    nome_empresa = "Empresa SPED"
    
    raw_content = arquivo.getvalue()
    try: conteudo = raw_content.decode('latin-1')
    except: 
        try: conteudo = raw_content.decode('utf-8')
        except: conteudo = raw_content.decode('latin-1', errors='ignore')

    lines = conteudo.split('\n')
    mapa_produtos = {}
    
    for linha in lines:
        if not linha.startswith('|'): continue
        campos = linha.split('|')
        if campos[1] == '0000' and len(campos) > 6: nome_empresa = campos[6]
        elif campos[1] == '0200' and len(campos) > 8:
            mapa_produtos[campos[2]] = {'NCM': campos[8], 'Produto': campos[3]}

    nota_atual = None
    buffer_itens = []
    usou_c170 = False
    
    def fechar_nota(nota, itens, usou_detalhe):
        if not nota: return
        lista_final = [i for i in itens if i['Origem'] == ('C170' if usou_detalhe else 'C190')]
        if nota['Tipo'] == 'SAIDA': vendas.extend(lista_final)
        else: compras.extend(lista_final)

    for linha in lines:
        if not linha.startswith('|'): continue
        campos = linha.split('|')
        reg = campos[1]
        
        if reg == 'C100':
            fechar_nota(nota_atual, buffer_itens, usou_c170)
            nota_atual = None
            buffer_itens = []
            usou_c170 = False
            cod_sit = campos[6]
            if cod_sit in ['00', '01', '1', '06', '6']: 
                ind_oper = campos[2]
                chave = campos[9] if len(campos) > 9 else f"DOC_{campos[8]}"
                num_nfe = campos[8] # Captura Campo 08 (NUM_DOC)
                nota_atual = {
                    'Tipo': 'SAIDA' if ind_oper == '1' else 'ENTRADA',
                    'Chave': chave,
                    'Num NFe': num_nfe
                }
                
        elif nota_atual:
            if reg == 'C170' and len(campos) > 10:
                usou_c170 = True
                cod_item = campos[3]
                dados = mapa_produtos.get(cod_item, {'NCM': '', 'Produto': 'Item Não Cadastrado'})
                buffer_itens.append({
                    'Cód. Produto': cod_item, 'Chave NFe': nota_atual['Chave'], 'Num NFe': nota_atual['Num NFe'],
                    'NCM': dados['NCM'], 'Produto': dados['Produto'],
                    'CFOP': campos[11], 'Valor': to_float(campos[7]),
                    'vICMS': to_float(campos[15]) if len(campos)>15 else 0.0,
                    'vPIS': to_float(campos[25]) if len(campos)>25 else 0.0,
                    'vCOFINS': to_float(campos[26]) if len(campos)>26 else 0.0,
                    'Tipo': nota_atual['Tipo'], 'Origem': 'C170'
                })
            elif reg == 'C190' and len(campos) > 5:
                cst = campos[2]
                cfop = campos[3]
                buffer_itens.append({
                    'Cód. Produto': 'RESUMO', 'Chave NFe': nota_atual['Chave'], 'Num NFe': nota_atual['Num NFe'],
                    'NCM': 'SEM_DETALHE',
                    'Produto': f"Resumo CST {cst} CFOP {cfop}",
                    'CFOP': cfop, 'Valor': to_float(campos[5]),
                    'vICMS': to_float(campos[7]), 'vPIS': 0.0, 'vCOFINS': 0.0,
                    'Tipo': nota_atual['Tipo'], 'Origem': 'C190'
                })

    fechar_nota(nota_atual, buffer_itens, usou_c170)
    return nome_empresa, vendas, compras
