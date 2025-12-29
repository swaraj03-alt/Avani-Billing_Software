from flask import Flask, render_template, redirect, url_for, session, request, make_response
from xhtml2pdf import pisa
from io import BytesIO
from datetime import datetime


app = Flask(__name__)
app.secret_key = "avani_secret_key"


# ---------- AUTH ----------
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


# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "admin" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ---------- MODULE ROUTES ----------
@app.route("/sale")
def sale():
    return render_template("sale.html")


@app.route("/purchase")
def purchase():
    return render_template("purchase.html")


@app.route('/payments')
def payments():
    # Get data from the URL (sent by the billing page)
    customer_name = request.args.get('customer', 'Walking Customer')
    total_amount = request.args.get('total', '0.00')

    # Generate a random voucher number for the UI
    import random
    voucher_no = random.randint(1000, 9999)

    return render_template("payments.html",
                           customer_name=customer_name,
                           total_amount=total_amount,
                           voucher_no=voucher_no)

#
# @app.route("/receipts")
# def receipts():
#     return render_template("receipts.html")


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


@app.route("/production")
def production():
    return render_template("production.html")

@app.route("/save-sale", methods=["POST"])
def save_sale():
    # Customer & invoice info
    customer = request.form.get("customer_id")
    invoice_no = request.form.get("invoice_no")
    invoice_date = request.form.get("invoice_date")
    payment_mode = request.form.get("payment_mode")

    # Product details (arrays)
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
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        payment_mode=payment_mode,
        items=items,
        subtotal=f"{subtotal:.2f}",
        gst_total=f"{gst_total:.2f}",
        roundoff=f"{roundoff:.2f}",
        grand_total=f"{grand_total:.2f}",
        today=datetime.now().strftime("%d-%b-%Y")
    )


@app.route("/quotations")
def quotations():
    return render_template("quotations.html")


@app.route("/quotation-pdf")
def quotation_pdf():
    if "admin" not in session:
        return redirect(url_for("login"))

    html = render_template("quotations.html", pdf=True)
    result = BytesIO()

    pisa_status = pisa.CreatePDF(
        html,
        dest=result
    )

    if pisa_status.err:
        return "PDF generation error"

    response = make_response(result.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "inline; filename=quotation.pdf"

    return response


@app.route("/eway-bill")
def eway_bill():
    return render_template("eway_bill.html")


@app.route("/gst-return")
def gst_return():
    return render_template("gst_return.html")


@app.route("/gstr-2a")
def gstr_2a():
    return render_template("gstr_2a.html")


@app.route("/gstr-2b")
def gstr_2b():
    return render_template("gstr_2b.html")


@app.route("/reconciliation")
def reconciliation():
    return render_template("reconciliation.html")


if __name__ == "__main__":
    app.run(debug=True)
