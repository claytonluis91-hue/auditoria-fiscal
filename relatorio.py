from fpdf import FPDF
from datetime import datetime
import pandas as pd

class PDFAuditoria(FPDF):
    def __init__(self, empresa):
        super().__init__()
        self.empresa = empresa
        self.data_emissao = datetime.now().strftime("%d/%m/%Y")

    def header(self):
        # Logo (se tiver um arquivo logo.png na pasta, ele carrega)
        # self.image('logo.png', 10, 8, 33) 
        
        # Título
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(44, 62, 80) # Azul Escuro
        self.cell(0, 10, 'Laudo Técnico de Auditoria Fiscal', ln=True, align='C')
        
        # Subtítulo
        self.set_font('Helvetica', 'I', 10)
        self.set_text_color(127, 140, 141) # Cinza
        self.cell(0, 5, f'Preparado para: {self.empresa}', ln=True, align='C')
        self.cell(0, 5, f'Data de Emissão: {self.data_emissao}', ln=True, align='C')
        self.ln(10)
        
        # Linha divisória
        self.set_draw_color(230, 126, 34) # Laranja Nascel
        self.set_line_width(1)
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}} - Gerado por cClass Auditor AI', align='C')

    def chapter_title(self, label):
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 10, f'  {label}', ln=True, fill=True)
        self.ln(4)

    def card_resumo(self, debito, credito, saldo):
        self.set_font('Helvetica', '', 10)
        
        # Tabela de Resumo Financeiro
        self.set_fill_color(255, 255, 255)
        self.cell(60, 10, "Débitos Estimados (Vendas):", border=1)
        self.set_font('Helvetica', 'B', 10)
        self.cell(0, 10, f"R$ {debito:,.2f}", border=1, ln=True)
        
        self.set_font('Helvetica', '', 10)
        self.cell(60, 10, "Créditos Estimados (Compras):", border=1)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(39, 174, 96) # Verde
        self.cell(0, 10, f"R$ {credito:,.2f}", border=1, ln=True)
        self.set_text_color(0) # Reset cor
        
        self.set_font('Helvetica', 'B', 10)
        self.cell(60, 10, "Saldo Final (IBS/CBS):", border=1)
        
        cor_saldo = (192, 57, 43) if saldo > 0 else (39, 174, 96)
        self.set_text_color(*cor_saldo)
        tipo = "A PAGAR" if saldo > 0 else "CREDOR"
        self.cell(0, 10, f"R$ {abs(saldo):,.2f} ({tipo})", border=1, ln=True)
        self.set_text_color(0)
        self.ln(10)

    def tabela_itens(self, df):
        # Cabeçalho da Tabela
        self.set_font('Helvetica', 'B', 8)
        self.set_fill_color(230, 126, 34) # Laranja
        self.set_text_color(255) # Branco
        
        # Colunas: Produto (80), NCM (20), CST (15), Valor (35), Imposto (35)
        self.cell(80, 7, 'Produto', 1, 0, 'C', True)
        self.cell(20, 7, 'NCM', 1, 0, 'C', True)
        self.cell(15, 7, 'CST', 1, 0, 'C', True)
        self.cell(35, 7, 'Valor Base', 1, 0, 'C', True)
        self.cell(35, 7, 'IBS+CBS', 1, 1, 'C', True) # ln=1 quebra linha
        
        # Dados
        self.set_font('Helvetica', '', 7)
        self.set_text_color(0)
        self.set_fill_color(245, 245, 245)
        
        fill = False
        # Limita a 50 itens para não gerar PDF gigante no teste
        for _, row in df.head(100).iterrows():
            prod = str(row['Produto'])[:45] # Corta nome muito longo
            ncm = str(row['NCM'])
            cst = str(row.get('Novo CST', ''))
            val = f"R$ {row.get('Valor', 0):,.2f}"
            imp = f"R$ {row.get('Carga Projetada', 0):,.2f}"
            
            self.cell(80, 6, prod, 1, 0, 'L', fill)
            self.cell(20, 6, ncm, 1, 0, 'C', fill)
            self.cell(15, 6, cst, 1, 0, 'C', fill)
            self.cell(35, 6, val, 1, 0, 'R', fill)
            self.cell(35, 6, imp, 1, 1, 'R', fill)
            fill = not fill # Alterna cor (Zebrado)
            
        self.ln(5)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 5, '* Listagem limitada aos primeiros 100 itens para fins de demonstração.', ln=True)

def gerar_pdf_bytes(empresa, df_vendas, df_compras):
    pdf = PDFAuditoria(empresa)
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 1. Resumo
    pdf.chapter_title("1. Resumo Executivo")
    deb = df_vendas['Carga Projetada'].sum() if not df_vendas.empty else 0
    cred = df_compras['Carga Projetada'].sum() if not df_compras.empty else 0
    saldo = deb - cred
    pdf.card_resumo(deb, cred, saldo)
    
    # 2. Vendas
    if not df_vendas.empty:
        pdf.chapter_title("2. Detalhamento de Saídas (Débitos)")
        # Filtra colunas necessárias
        df_v = df_vendas[['Produto', 'NCM', 'Novo CST', 'Valor', 'Carga Projetada']].copy()
        pdf.tabela_itens(df_v)
        
    # 3. Compras
    if not df_compras.empty:
        pdf.add_page()
        pdf.chapter_title("3. Detalhamento de Entradas (Créditos)")
        df_c = df_compras[['Produto', 'NCM', 'Novo CST', 'Valor', 'Carga Projetada']].copy()
        pdf.tabela_itens(df_c)
        
    return pdf.output(dest='S').encode('latin-1') # Retorna bytes