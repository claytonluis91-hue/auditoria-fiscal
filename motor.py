import pandas as pd
import json
import xml.etree.ElementTree as ET

# --- CARREGAMENTO DE DADOS SIMULADOS (MANTENHA SUA LÓGICA DE BANCO AQUI) ---
def carregar_base_legal():
    # AQUI VOCÊ DEVE CONECTAR COM SEU EXCEL/CSV DE REGRAS DE NCM
    # Estou simulando alguns casos para teste. 
    # No seu uso real, isso deve vir do arquivo que você carrega no app.py
    return {
        # EX: ARROZ (Cesta Básica)
        "10063021": {"cClass": "100001", "desc": "Cesta Básica Nacional", "redutor": 0.0, "status": "ZERO"},
        # EX: FEIJÃO
        "07133319": {"cClass": "100001", "desc": "Cesta Básica Nacional", "redutor": 0.0, "status": "ZERO"},
        # EX: MEDICAMENTO (Reduzida 60% - Paga 40%)
        "30049069": {"cClass": "500001", "desc": "Medicamento Reduzido", "redutor": 0.4, "status": "REDUZIDA"},
        # Adicione outros NCMs conforme sua base real
    }

def carregar_json_regras():
    return pd.DataFrame([
        {"cClass": "000001", "Descricao": "Tributação Padrão", "Aliquota": "Cheia"},
        {"cClass": "410999", "Descricao": "Operação Não Onerosa / Imune / Isenta / Suspensão", "Aliquota": "Zero"},
    ])

def carregar_tipi(uploaded_file):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                return pd.read_csv(uploaded_file, encoding='latin1', sep=';', dtype=str)
            else:
                return pd.read_excel(uploaded_file, dtype=str)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

# --- PARSERS (XML & SPED) ---
def extrair_nome_empresa_xml(tree, ns):
    try:
        emit = tree.find('.//ns:emit', ns)
        return emit.find('ns:xNome', ns).text
    except:
        return "Empresa Desconhecida"

def processar_xml_detalhado(tree, ns, tipo_arquivo):
    itens = []
    try:
        infNFe = tree.find('.//ns:infNFe', ns)
        chave = infNFe.attrib.get('Id', '')[3:]
        ide = infNFe.find('ns:ide', ns)
        natOp = ide.find('ns:natOp', ns).text
    except:
        return []

    for det in infNFe.findall('ns:det', ns):
        prod = det.find('ns:prod', ns)
        imposto = det.find('ns:imposto', ns)
        
        item = {
            'Tipo Arquivo': tipo_arquivo,
            'Chave NFe': chave,
            'Natureza Op.': natOp,
            'Cód. Produto': prod.find('ns:cProd', ns).text,
            'Produto': prod.find('ns:xProd', ns).text,
            'NCM': prod.find('ns:NCM', ns).text,
            'CFOP': prod.find('ns:CFOP', ns).text,
            'Valor': float(prod.find('ns:vProd', ns).text),
        }
        
        # Extração de Tributos Atuais
        try:
            icms = imposto.find('.//ns:ICMS', ns)
            tags_icms = icms[0] if len(icms) > 0 else None
            item['vICMS'] = float(tags_icms.find('ns:vICMS', ns).text) if tags_icms is not None and tags_icms.find('ns:vICMS', ns) is not None else 0.0
        except: item['vICMS'] = 0.0
            
        try:
            pis = imposto.find('.//ns:PIS', ns)
            tags_pis = pis[0] if len(pis) > 0 else None
            item['vPIS'] = float(tags_pis.find('ns:vPIS', ns).text) if tags_pis is not None and tags_pis.find('ns:vPIS', ns) is not None else 0.0
        except: item['vPIS'] = 0.0
            
        try:
            cofins = imposto.find('.//ns:COFINS', ns)
            tags_cofins = cofins[0] if len(cofins) > 0 else None
            item['vCOFINS'] = float(tags_cofins.find('ns:vCOFINS', ns).text) if tags_cofins is not None and tags_cofins.find('ns:vCOFINS', ns) is not None else 0.0
        except: item['vCOFINS'] = 0.0
        
        itens.append(item)
    return itens

def processar_sped_fiscal(file_obj):
    content = file_obj.getvalue().decode('latin1').splitlines()
    nome_empresa = "Empresa SPED"
    vendas = []
    compras = []
    mapa_itens = {} 
    
    for line in content:
        if not line.startswith('|'): continue
        campos = line.split('|')
        registro = campos[1]
        
        if registro == '0000':
            nome_empresa = campos[6]
        elif registro == '0200':
            cod_item = campos[2]
            descr = campos[3]
            ncm = campos[7] if len(campos) > 7 else ""
            mapa_itens[cod_item] = {'Produto': descr, 'NCM': ncm}
        elif registro == 'C170':
            cfop = campos[11]
            cod_item = campos[3]
            valor = float(campos[7].replace(',', '.'))
            dados_prod = mapa_itens.get(cod_item, {'Produto': 'Item ' + cod_item, 'NCM': ''})
            
            item = {
                'Chave NFe': 'SPED (S/ Chave Link)',
                'CFOP': cfop,
                'Valor': valor,
                'Produto': dados_prod['Produto'],
                'NCM': dados_prod['NCM'],
                'vICMS': float(campos[15].replace(',', '.')) if len(campos) > 15 and campos[15] else 0.0,
                'vPIS': float(campos[25].replace(',', '.')) if len(campos) > 25 and campos[25] else 0.0,
                'vCOFINS': float(campos[31].replace(',', '.')) if len(campos) > 31 and campos[31] else 0.0
            }
            if cfop.startswith('1') or cfop.startswith('2') or cfop.startswith('3'): compras.append(item)
            elif cfop.startswith('5') or cfop.startswith('6') or cfop.startswith('7'): vendas.append(item)
            
    return nome_empresa, vendas, compras

# --- CLASSIFICADOR INTELIGENTE (CORRIGIDO) ---
def classificar_item(row, mapa_lei, df_regras, df_tipi, aliq_ibs, aliq_cbs):
    ncm = str(row['NCM']).replace('.', '').strip()
    cfop = str(row['CFOP']).replace('.', '').strip()
    
    # ---------------------------------------------------------------------
    # PASSO 1: Busca a Regra pelo NCM (Base Legal)
    # ---------------------------------------------------------------------
    # Tenta encontrar o NCM no dicionário de leis.
    # Se não achar, aplica a regra PADRÃO (Tributado Integral).
    
    regra_encontrada = mapa_lei.get(ncm)
    
    if regra_encontrada:
        # Achou NCM na base (Ex: Cesta Básica, Reduzida)
        cClass = regra_encontrada.get('cClass', '000001')
        desc_regra = regra_encontrada.get('desc', 'Regra Específica NCM')
        status = regra_encontrada.get('status', 'DIFERENCIADA')
        redutor = float(regra_encontrada.get('redutor', 1.0)) # 0.0 = Isento, 0.4 = Paga 40% (Red. 60%)
        origem_legal = f"Base NCM ({ncm})"
        novo_cst = '01' if redutor > 0 else '20'
    else:
        # NCM não mapeado -> Considera Padrão Full
        cClass = '000001'
        desc_regra = 'Tributação Padrão'
        status = 'PADRAO'
        redutor = 1.0 # Paga 100%
        origem_legal = 'Regra Geral (NCM ñ mapeado)'
        novo_cst = '01'

    # ---------------------------------------------------------------------
    # PASSO 2: Verifica CFOP (Operações Não Onerosas)
    # ---------------------------------------------------------------------
    # Se for operação não onerosa, SOBRESCREVE a regra do NCM.
    # Ex: Mesmo que seja um iPhone (Tributado), se for Doação (5910), zera.
    
    cfops_nao_onerosos = [
        '1910', '2910', '5910', '6910', # Bonificação/Doação
        '1911', '2911', '5911', '6911', # Amostra Grátis
        '5912', '6912', '5913', '6913', # Demonstração
        '5901', '6901', '5902', '6902', # Industrialização
        '5903', '6903', 
        '5915', '6915', '5916', '6916', # Conserto
        '5949', '6949'                  # Outras saídas (Cuidado, mas geralmente não gera receita)
    ]
    
    if cfop in cfops_nao_onerosos:
        cClass = '410999'
        desc_regra = f"Op. Não Onerosa (CFOP {cfop})"
        status = 'ZERO (CFOP)'
        redutor = 0.0 # ZERA TUDO
        origem_legal = 'Regra de CFOP'
        novo_cst = '410'

    # ---------------------------------------------------------------------
    # PASSO 3: Validação TIPI e Cálculos
    # ---------------------------------------------------------------------
    validacao_tipi = "N/A"
    if not df_tipi.empty:
        if ncm in df_tipi.values: validacao_tipi = "✅ TIPI OK"
        else: validacao_tipi = "⚠️ NCM Inválido/Antigo"

    # Cálculos Finais
    carga_atual = row.get('vICMS', 0) + row.get('vPIS', 0) + row.get('vCOFINS', 0)
    valor_base = row['Valor']
    
    # Aplica o redutor definido no Passo 1 ou Passo 2
    v_ibs = valor_base * aliq_ibs * redutor
    v_cbs = valor_base * aliq_cbs * redutor
    carga_projetada = v_ibs + v_cbs
    
    return [cClass, desc_regra, status, novo_cst, origem_legal, validacao_tipi, carga_atual, carga_projetada, v_ibs, v_cbs]
