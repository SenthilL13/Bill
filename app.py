from flask import Flask, send_file, render_template, request, redirect, url_for, flash
from dataclasses import dataclass
import datetime
from datetime import datetime
from typing import List
from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import sqlite3


app = Flask(__name__)
app.secret_key = "your-secret-key-here"

@dataclass
class InvoiceItem:
    item_name: str
    quantity: float
    rate: float
    hsn_code: str = ""

    @property
    def amount(self) -> float:
        return round(self.quantity * self.rate, 2)

def get_db_connection():
    conn = sqlite3.connect('invoices.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # # Check if 'status' column exists in 'invoices' table
    # c.execute("PRAGMA table_info(invoices)")
    # columns = [column[1] for column in c.fetchall()]
    # if 'status' not in columns:
    #     c.execute('ALTER TABLE invoices ADD COLUMN status TEXT DEFAULT "pending"')

    # # Check if 'cgst' column exists in 'invoice_items' table
    # c.execute("PRAGMA table_info(invoice_items)")
    # item_columns = [column[1] for column in c.fetchall()]
    # if 'cgst' not in item_columns:
    #     c.execute('ALTER TABLE invoice_items ADD COLUMN cgst REAL')

    # Create 'invoices' table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        customer_name TEXT, 
        customer_address TEXT, 
        party_gstin TEXT, 
        date TEXT, 
        status TEXT DEFAULT 'pending', 
        notes TEXT, 
        items TEXT
    )''')

    # Create 'invoice_items' table if not exists
    c.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        invoice_id INTEGER, 
        item_name TEXT, 
        quantity REAL, 
        rate REAL, 
        amount REAL, 
        hsn_code TEXT, 
        cgst REAL, 
        sgst REAL, 
        FOREIGN KEY (invoice_id) REFERENCES invoices (id)
    )''')


    conn.commit()
    conn.close()

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT i.*, COALESCE(COUNT(ii.id), 0) as items_count, 
                   COALESCE(SUM(ii.amount), 0) as total_amount
                   FROM invoices i 
                   LEFT JOIN invoice_items ii ON i.id = ii.invoice_id
                   GROUP BY i.id
                   ORDER BY i.id DESC''')
    invoices = cur.fetchall()
    conn.close()
    return render_template('dashboard.html', invoices=invoices)

@app.route('/invoice/<int:invoice_id>', methods=['GET', 'POST'])
def c(invoice_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,))
    invoice = cur.fetchone()
    
    if not invoice:
        conn.close()
        return "Invoice not found", 404

    # Get invoice items
    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
    items = cur.fetchall()
    conn.close()

    # Convert items to list of dictionaries for easier handling
    items_list = []
    for item in items:
        items_list.append({
            'item_name': item['item_name'],
            'quantity': item['quantity'],
            'rate': item['rate'],
            'amount': item['amount'],
            'hsn_code': item['hsn_code'] if 'hsn_code' in item.keys() else ""
        })

    return render_template('invoice.html', 
                         invoice_no=invoice['id'], 
                         date=invoice['date'], 
                         customer_name=invoice['customer_name'], 
                         customer_address=invoice['customer_address'], 
                         party_gstin=invoice['party_gstin'],
                         items=items_list,
                         total_amount=invoice['total_amount'] if 'total_amount' in invoice.keys() else 0,
                         cgst=invoice['cgst'] if 'cgst' in invoice.keys() else 0,
                         sgst=invoice['sgst'] if 'sgst' in invoice.keys() else 0,
                         grand_total=invoice['grand_total'] if 'grand_total' in invoice.keys() else 0,
                         grand_total_words=invoice['grand_total_words'] if 'grand_total_words' in invoice.keys() else "")


@app.route('/invoice/new', methods=['GET', 'POST'])
def new_invoice():
    if request.method == 'POST':
        customer_name = request.form['customerName']
        customer_address = request.form['customerAddress']
        party_gstin = request.form['partyGstin']
        date = request.form['date']
        notes = request.form.get('notes', '')
        
        items = []
        item_names = request.form.getlist('itemName[]')
        quantities = request.form.getlist('quantity[]')
        rates = request.form.getlist('rate[]')
        hsn_codes = request.form.getlist('hsnCode[]')
        
        for i in range(len(item_names)):
            if item_names[i] and quantities[i] and rates[i]:
                items.append(InvoiceItem(
                    item_name=item_names[i],
                    quantity=float(quantities[i]),
                    rate=float(rates[i]),
                    hsn_code=hsn_codes[i] if i < len(hsn_codes) else ""
                ))
        
        invoice_id = save_invoice(customer_name, customer_address, party_gstin, items, date, notes)
        flash('Invoice created successfully!')
        return redirect(url_for('view_invoice', invoice_id=invoice_id))
    
    invoice_no = get_next_invoice_number()
    return render_template('new_invoice.html', invoice_no=invoice_no, date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT id, date, customer_name, customer_address, party_gstin, items, total_amount, cgst, sgst, grand_total, grand_total_words FROM invoices WHERE id = ?', (invoice_id,))
    invoice = cur.fetchone()
    
    if not invoice:
        conn.close()
        flash('Invoice not found')
        return redirect(url_for('dashboard'))
    
    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
    items = cur.fetchall()
    conn.close()
    
    # Convert items to InvoiceItem objects
    invoice_items = [InvoiceItem(
        item['item_name'],
        float(item['quantity']),
        float(item['rate']),
        item['hsn_code'] if 'hsn_code' in item.keys() else ""
    ) for item in items]
    
    totals = calculate_totals(invoice_items)
    grand_total_words = format_amount_words(totals['grand_total'])
    
    return render_template('view_invoice.html', 
                           invoice=invoice, 
                           items=invoice_items, 
                           total_amount=invoice['total_amount'], 
                           cgst=invoice['cgst'], 
                           sgst=invoice['sgst'], 
                           grand_total=invoice['grand_total'], 
                           grand_total_words=invoice['grand_total_words'])

@app.route('/invoice/<int:invoice_id>/pdf')
def generate_pdf(invoice_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,))
    invoice = cur.fetchone()
    
    if not invoice:
        conn.close()
        flash('Invoice not found')
        return redirect(url_for('dashboard'))
    
    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
    items = cur.fetchall()
    conn.close()
    
    # Convert items to InvoiceItem objects
    invoice_items = [InvoiceItem(
        item['item_name'],
        float(item['quantity']),
        float(item['rate']),
        item['hsn_code'] if 'hsn_code' in item else ""
    ) for item in items]
    
    totals = calculate_totals(invoice_items)
    grand_total_words = format_amount_words(totals['grand_total'])
    
    # Create a PDF using reportlab
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Add invoice header
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Invoice #{invoice['id']}", styles['Title']))
    elements.append(Spacer(1, 12))
    
    # Add invoice details
    elements.append(Paragraph(f"Date: {invoice['date']}", styles['Normal']))
    elements.append(Paragraph(f"Customer: {invoice['customer_name']}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Add items table
    data = [['Item', 'Quantity', 'Rate', 'Amount']]
    for item in invoice_items:
        data.append([item.item_name, item.quantity, item.rate, item.amount])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    
    # Add totals
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Subtotal: {totals['subtotal']:.2f}", styles['Normal']))
    elements.append(Paragraph(f"CGST (2.5%): {totals['cgst']:.2f}", styles['Normal']))
    elements.append(Paragraph(f"SGST (2.5%): {totals['sgst']:.2f}", styles['Normal']))
    elements.append(Paragraph(f"Grand Total: {totals['grand_total']:.2f}", styles['Normal']))
    elements.append(Paragraph(f"Amount in words: {grand_total_words}", styles['Normal']))
    
    # Generate PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        download_name=f'invoice_{invoice_id}.pdf',
        mimetype='application/pdf'
    )


@app.route('/search')
def search_invoices():
    query = request.args.get('q', '')
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''SELECT i.*, COALESCE(COUNT(ii.id), 0) as items_count, 
                   COALESCE(SUM(ii.amount), 0) as total_amount
                   FROM invoices i 
                   LEFT JOIN invoice_items ii ON i.id = ii.invoice_id
                   WHERE i.customer_name LIKE ? OR i.party_gstin LIKE ?
                   GROUP BY i.id
                   ORDER BY i.date DESC''', 
                (f'%{query}%', f'%{query}%'))
    
    invoices = cur.fetchall()
    conn.close()
    return render_template('search_results.html', invoices=invoices, query=query)

def get_next_invoice_number() -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT MAX(id) FROM invoices')
    result = cur.fetchone()[0]
    conn.close()
    return (result or 0) + 1

def save_invoice(customer_name: str, customer_address: str, party_gstin: str, items: List[InvoiceItem], date: str, notes: str) -> int:
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''INSERT INTO invoices (customer_name, customer_address, party_gstin, date, status, notes)
                 VALUES (?, ?, ?, ?, ?, ?)''', (customer_name, customer_address, party_gstin, date, 'pending', notes))
    invoice_id = c.lastrowid
    
    for item in items:
        c.execute('''INSERT INTO invoice_items 
                    (invoice_id, item_name, quantity, rate, amount, hsn_code)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (invoice_id, item.item_name, item.quantity, item.rate, item.amount, item.hsn_code))
    
    conn.commit()
    conn.close()
    return invoice_id

def calculate_totals(items: List[InvoiceItem]) -> dict:
    if not items:
        return {
            'subtotal': 0,
            'cgst': 0,
            'sgst': 0,
            'grand_total': 0
        }
    
    subtotal = sum(item.amount for item in items)
    cgst = round(subtotal * 0.025, 2)
    sgst = round(subtotal * 0.025, 2)
    grand_total = round(subtotal + cgst + sgst, 2)
    
    return {
        'subtotal': subtotal,
        'total_amount': subtotal,
        'cgst': cgst,
        'sgst': sgst,
        'grand_total': grand_total
    }

def format_amount_words(amount: float) -> str:
    amount = round(amount, 2)
    whole = int(amount)
    decimal = int((amount - whole) * 100)
    
    if decimal > 0:
        return f"{num2words(whole, lang='en').title()} Rupees and {num2words(decimal, lang='en').title()} Paise Only"
    return f"{num2words(whole, lang='en').title()} Rupees Only"

@app.route('/')
def invoice():
    # Example grand total value
    grand_total = 1200.50  # This should be dynamically calculated

    # Convert grand total to words
    grand_total_words = format_amount_words(grand_total)

    # Pass data to the template
    return render_template('invoice_template.html', grand_total=grand_total, grand_total_words=grand_total_words)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

