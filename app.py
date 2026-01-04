from flask import Flask, render_template, redirect, url_for, session, request, make_response, flash
from xhtml2pdf import pisa
from io import BytesIO
from datetime import datetime
import random

app = Flask(__name__)
app.secret_key = "avani_secret_key"


# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "admin123":
            session["admin"] = True
            return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def login_required():
    if "admin" not in session:
        return False
    return True


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ================= SALES =================

# Invoice list (MAIN ENTRY POINT)
@app.route("/invoices")
def invoice_list():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("invoice_list.html")


# Create new invoice
@app.route("/sale")
def sale():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("sale.html")


# Save invoice (NO DB YET)
@app.route("/save-sale", methods=["POST"])
def save_sale():
    if not login_required():
        return redirect(url_for("login"))

    customer = request.form.get("customer_id")
    invoice_date = request.form.get("invoice_date")
    payment_mode = request.form.get("payment_mode")

    products = request.form.getlist("product[]")
    hsn = request.form.getlist("hsn[]")
    qty = request.form.getlist("qty[]")
    rate = request.form.getlist("rate[]")
    discount = request.form.getlist("discount[]")
    tax = request.form.getlist("tax[]")

    items = []
    subtotal = gst_total = 0

    for i in range(len(products)):
        taxable = (float(qty[i]) * float(rate[i])) - float(discount[i])
        gst_amt = taxable * float(tax[i]) / 100
        total = taxable + gst_amt

        subtotal += taxable
        gst_total += gst_amt

        items.append({
            "product": products[i],
            "hsn": hsn[i],
            "qty": qty[i],
            "rate": rate[i],
            "discount": discount[i],
            "tax": tax[i],
            "total": f"{total:.2f}"
        })

    grand_total = round(subtotal + gst_total)
    roundoff = grand_total - (subtotal + gst_total)

    return render_template(
        "save-sale.html",
        customer=customer,
        invoice_date=invoice_date,
        payment_mode=payment_mode,
        items=items,
        subtotal=f"{subtotal:.2f}",
        gst_total=f"{gst_total:.2f}",
        roundoff=f"{roundoff:.2f}",
        grand_total=f"{grand_total:.2f}",
        invoice_no=f"INV/{random.randint(1000,9999)}",
        today=datetime.now().strftime("%d-%b-%Y")
    )


# ================= CUSTOMERS =================
@app.route("/customers")
def customers():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("customers.html")


# ================= ITEMS =================
@app.route("/items")
def items():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("items.html")

@app.route("/save-production", methods=["POST"])
def save_production():
    try:
        # =============================
        # BASIC BATCH INFO
        # =============================
        production_date = request.form.get("production_date")
        oil_type = request.form.get("oil_type")
        machine = request.form.get("machine")
        operator = request.form.get("operator")
        status = request.form.get("status")

        # =============================
        # RAW MATERIAL (MULTIPLE ROWS)
        # =============================
        raw_materials = request.form.getlist("raw_material[]")
        raw_qtys = request.form.getlist("raw_qty[]")
        raw_rates = request.form.getlist("raw_rate[]")

        raw_items = []
        total_raw_qty = 0
        total_raw_cost = 0

        for i in range(len(raw_materials)):
            qty = float(raw_qtys[i])
            rate = float(raw_rates[i])
            total = qty * rate

            raw_items.append({
                "material": raw_materials[i],
                "qty": qty,
                "rate": rate,
                "total": total
            })

            total_raw_qty += qty
            total_raw_cost += total

        # =============================
        # PRODUCTION OUTPUT
        # =============================
        oil_extracted = float(request.form.get("oil_extracted") or 0)
        oil_cake = float(request.form.get("oil_cake") or 0)
        wastage = float(request.form.get("wastage") or 0)

        yield_percent = (oil_extracted / total_raw_qty * 100) if total_raw_qty > 0 else 0

        # =============================
        # QUALITY CHECK
        # =============================
        temperature = request.form.get("temperature")
        qc_status = request.form.get("qc_status")
        qc_remarks = request.form.get("qc_remarks")

        # =============================
        # PASS DATA TO CONFIRMATION PAGE
        # =============================
        return render_template(
            "production_success.html",
            production_date=production_date,
            oil_type=oil_type,
            machine=machine,
            operator=operator,
            status=status,
            raw_items=raw_items,
            total_raw_qty=total_raw_qty,
            total_raw_cost=total_raw_cost,
            oil_extracted=oil_extracted,
            oil_cake=oil_cake,
            wastage=wastage,
            yield_percent=yield_percent,
            temperature=temperature,
            qc_status=qc_status,
            qc_remarks=qc_remarks,
            today=datetime.now().strftime("%d-%m-%Y")
        )

    except Exception as e:
        flash(f"Error saving production: {str(e)}", "danger")
        return redirect(url_for("production"))


# ================= PAYMENTS RECEIVED =================
@app.route("/payments")
def payments():
    if not login_required():
        return redirect(url_for("login"))

    customer_name = request.args.get("customer", "Walking Customer")
    total_amount = request.args.get("total", "0.00")
    voucher_no = random.randint(1000, 9999)

    return render_template(
        "payments.html",
        customer_name=customer_name,
        total_amount=total_amount,
        voucher_no=voucher_no
    )

@app.route('/generate-invoice')
def generate_invoice():
    # Capture data from the Payment Page
    customer = request.args.get('cust', 'Walking Customer')
    amount = request.args.get('amt', '0.00')
    mode = request.args.get('mode', 'Cash')
    ref = request.args.get('ref', '-')

    # Generate real-world bill details
    from datetime import datetime
    import random
    date_now = datetime.now().strftime("%d-%b-%Y | %I:%M %p")
    bill_no = random.randint(5000, 9999)

    # RENDER YOUR EXISTING receipts.html
    return render_template("receipts.html",
                           customer=customer,
                           amount=amount,
                           mode=mode,
                           ref=ref,
                           date=date_now,
                           bill_no=bill_no)


# ================= QUOTATIONS =================
@app.route("/quotations")
def quotations():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("quotations.html")


@app.route("/quotation-pdf")
def quotation_pdf():
    if not login_required():
        return redirect(url_for("login"))

    html = render_template("quotations.html", pdf=True)
    result = BytesIO()
    pisa.CreatePDF(html, dest=result)

    response = make_response(result.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "inline; filename=quotation.pdf"
    return response


# ================= GST & REPORTS =================
@app.route("/sales-reports")
def sales_reports():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("gst_reports.html")


@app.route("/gst-return")
def gst_return():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("gst_return.html")


@app.route("/gstr-2a")
def gstr_2a():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("gstr_2a.html")


@app.route("/gstr-2b")
def gstr_2b():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("gstr_2b.html")


# ================= OTHER MODULES =================
@app.route("/purchase")
def purchase():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("purchase.html")


@app.route("/production")
def production():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("production.html")


@app.route("/eway-bill")
def eway_bill():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("eway_bill.html")


@app.route("/reconciliation")
def reconciliation():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("reconciliation.html")


# ================= PDF PREVIEW =================
@app.route("/invoice/<int:invoice_id>/pdf")
def invoice_pdf(invoice_id):
    if not login_required():
        return redirect(url_for("login"))
    return render_template("invoice_pdf.html", invoice_id=invoice_id)


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
