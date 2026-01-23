from flask import Flask, render_template, redirect, url_for, session, request, make_response, flash
from xhtml2pdf import pisa
from io import BytesIO
from flask import make_response
from datetime import datetime
import random
import json
from decimal import Decimal
import MySQLdb
from flask_mysqldb import MySQL #main work for connection of db

app = Flask(__name__)
app.secret_key = "avani_secret_key"

# ================= DATABASE CONFIG =================
app.config["MYSQL_HOST"] = "localhost"
app.config["MYSQL_USER"] = "root"
app.config["MYSQL_PASSWORD"] = "Swaraj@1"          # put your password if any
app.config["MYSQL_DB"] = "billing_software"
app.config["MYSQL_CURSORCLASS"] = "DictCursor"

mysql = MySQL(app)

@app.route("/test-db")
def test_db():
    cur = mysql.connection.cursor()
    cur.execute("SHOW TABLES")
    tables = cur.fetchall()
    cur.close()
    return {"tables": tables}

#HELPER FUNCTION (Invoice No)
def generate_invoice_no():
    return "INV-" + datetime.now().strftime("%Y%m%d") + "-" + str(random.randint(100, 999))

#HELPER FUNCTION (Receipt No.)
def generate_receipt_no():
    return "RCPT-" + datetime.now().strftime("%Y%m%d") + "-" + str(random.randint(100, 999))

# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "admin123":
            session["admin"] = True
            return redirect(url_for("dashboard"))
        flash("✅ Invalid Id & Password!", "danger")

    return render_template("login.html")

@app.route("/credit-notes")
def credit_notes():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT *
        FROM receipts
        WHERE payment_status = 'DUE'
        ORDER BY id DESC
    """)
    data = cur.fetchall()
    cur.close()

    return render_template("credit_notes_list.html", credits=data)


@app.route("/settle-credit-notes", methods=["GET", "POST"])
def settle_credit_notes():
    if not login_required():
        return redirect(url_for("login"))

    rid = request.args.get("rid")

    cur = mysql.connection.cursor()

    # ================= GET RECEIPT =================
    cur.execute("SELECT * FROM receipts WHERE id=%s", (rid,))
    receipt = cur.fetchone()

    if not receipt:
        cur.close()
        flash("Credit receipt not found", "danger")
        return redirect(url_for("credit_notes"))

    # ================= SUBMIT SETTLEMENT =================
    if request.method == "POST":
        payment_mode = request.form.get("payment_mode")

        cur.execute("""
            UPDATE receipts
            SET payment_status='PAID',
                payment_mode=%s
            WHERE id=%s
        """, (payment_mode, rid))

        mysql.connection.commit()
        cur.close()

        flash("✅ Credit settled successfully!", "success")
        return redirect(url_for("credit_notes"))

    cur.close()

    return render_template("settle_credit.html", r=receipt)


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

    cur = mysql.connection.cursor()

    # ================= TODAY SALES =================
    cur.execute("""
        SELECT 
            COALESCE(SUM(amount), 0) AS total,
            COUNT(*) AS invoices
        FROM receipts
        WHERE DATE(created_at) = CURDATE()
          AND payment_status = 'PAID'
    """)
    today = cur.fetchone()
    today_sales = today["total"]
    today_invoices = today["invoices"]

    # ================= MONTHLY REVENUE =================
    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM receipts
        WHERE MONTH(created_at) = MONTH(CURDATE())
          AND YEAR(created_at) = YEAR(CURDATE())
          AND payment_status = 'PAID'
    """)
    monthly_revenue = cur.fetchone()["total"]

    # ================= OUTSTANDING RECEIVABLES =================
    cur.execute("""
        SELECT 
            COALESCE(SUM(amount), 0) AS total,
            COUNT(DISTINCT customer_name) AS customers
        FROM receipts
        WHERE payment_status = 'DUE'
    """)
    due = cur.fetchone()
    outstanding_amount = due["total"]
    pending_customers = due["customers"]

    # ================= GST LIABILITY (CGST + SGST) =================
    cur.execute("""
        SELECT 
            COALESCE(SUM(cgst + sgst), 0) AS gst
        FROM receipts
        WHERE payment_status = 'PAID'
          AND MONTH(created_at) = MONTH(CURDATE())
          AND YEAR(created_at) = YEAR(CURDATE())
    """)
    gst_liability = cur.fetchone()["gst"]

    cur.close()

    # ================= CURRENT MONTH NAME =================
    current_month = datetime.now().strftime("%B %Y")

    return render_template(
        "dashboard.html",
        today_sales=round(today_sales, 2),
        today_invoices=today_invoices,
        monthly_revenue=round(monthly_revenue, 2),
        current_month=current_month,
        outstanding_amount=round(outstanding_amount, 2),
        pending_customers=pending_customers,
        gst_liability=round(gst_liability, 2)
    )

@app.route("/reports/today-sales")
def today_sales_report():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT *
        FROM receipts
        WHERE DATE(created_at) = CURDATE()
          AND payment_status = 'PAID'
        ORDER BY created_at DESC
    """)
    data = cur.fetchall()
    cur.close()

    return render_template("receipts_list.html", receipts=data)


@app.route("/reports/monthly-sales")
def monthly_sales_report():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT *
        FROM receipts
        WHERE MONTH(created_at) = MONTH(CURDATE())
          AND YEAR(created_at) = YEAR(CURDATE())
          AND payment_status = 'PAID'
        ORDER BY created_at DESC
    """)
    data = cur.fetchall()
    cur.close()

    return render_template("receipts_list.html", receipts=data)

@app.route("/gst-2b")
def gst_2b():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # MONTH FILTER (default current month)
    cur.execute("""
        SELECT 
            p.bill_no,
            p.bill_date,
            p.vendor_name,
            p.total_amount
        FROM purchases p
        WHERE MONTH(p.bill_date) = MONTH(CURDATE())
          AND YEAR(p.bill_date) = YEAR(CURDATE())
        ORDER BY p.bill_date DESC
    """)

    rows = cur.fetchall()
    cur.close()

    gst_2b = []
    total_taxable = 0
    total_itc = 0

    for r in rows:
        total = float(r["total_amount"])
        taxable = round(total / 1.18, 2)
        gst = round(total - taxable, 2)

        total_taxable += taxable
        total_itc += gst

        gst_2b.append({
            "invoice": r["bill_no"],
            "vendor": r["vendor_name"],
            "date": r["bill_date"],
            "taxable": taxable,
            "gst": gst,
            "status": "ELIGIBLE"
        })

    return render_template(
        "gst_2b.html",
        data=gst_2b,
        total_taxable=round(total_taxable, 2),
        total_itc=round(total_itc, 2)
    )

@app.route("/gst-summary")
def gst_summary():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            SUM(cgst) AS cgst,
            SUM(sgst) AS sgst
        FROM receipts
        WHERE payment_status = 'PAID'
          AND MONTH(created_at) = MONTH(CURDATE())
          AND YEAR(created_at) = YEAR(CURDATE())
    """)
    gst = cur.fetchone()
    cur.close()

    return render_template("gst_summary.html", gst=gst)

# ================= SALES Analytics=================
@app.route("/analytics")
def analytics():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/api/sales-analytics")
def sales_analytics():
    # APIs must never redirect
    if "admin" not in session:
        return {"labels": [], "paid": [], "credit": []}

    view = request.args.get("view", "monthly")

    if view == "daily":
        label_sql = "DATE_FORMAT(created_at, '%d %b')"
        group_sql = label_sql

    elif view == "weekly":
        label_sql = "CONCAT(YEAR(created_at), '-W', WEEK(created_at))"
        group_sql = label_sql

    else:  # monthly
        label_sql = "DATE_FORMAT(created_at, '%b %Y')"
        group_sql = label_sql

    cur = mysql.connection.cursor()
    cur.execute(f"""
        SELECT 
            {label_sql} AS label,
            SUM(CASE WHEN payment_status = 'PAID' THEN amount ELSE 0 END) AS paid,
            SUM(CASE WHEN payment_status = 'DUE' THEN amount ELSE 0 END) AS credit
        FROM receipts
        GROUP BY {group_sql}
        ORDER BY MIN(created_at)
    """)
    rows = cur.fetchall()
    cur.close()

    return {
        "labels": [r["label"] for r in rows],
        "paid": [float(r["paid"] or 0) for r in rows],
        "credit": [float(r["credit"] or 0) for r in rows]
    }



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

    stock = get_available_stock()

    pre_oil = request.args.get("oil")
    pre_size = request.args.get("size")
    print("SALE OPENED:", pre_oil, pre_size)

    return render_template(
        "sale.html",
        stock=stock,
        pre_oil=pre_oil,
        pre_size=pre_size
    )


def get_or_create_customer(name, mobile):
    cur = mysql.connection.cursor()

    # Check if customer already exists
    cur.execute(
        "SELECT id FROM customers WHERE mobile = %s",
        (mobile,)
    )
    row = cur.fetchone()

    if row:
        customer_id = row[0]
    else:
        # Insert new customer
        cur.execute(
            "INSERT INTO customers (name, mobile) VALUES (%s, %s)",
            (name, mobile)
        )
        mysql.connection.commit()
        customer_id = cur.lastrowid

    cur.close()
    return customer_id

@app.route("/save-sale", methods=["POST"])
def save_sale():
    if not login_required():
        return redirect(url_for("login"))

    customer_name = request.form.get("customer_name")
    mobile = request.form.get("customer_mobile")
    address = request.form.get("customer_address")
    items_json = request.form.get("items_json")
    payment_mode = request.form.get("payment_mode", "PENDING")

    if not customer_name or not mobile or not items_json:
        flash("Customer details missing", "danger")
        return redirect(url_for("sale"))

    items = json.loads(items_json)
    total_amount = sum(float(i["price"]) * int(i["quantity"]) for i in items)

    cur = mysql.connection.cursor()

    # ================= CUSTOMER =================
    cur.execute("SELECT id FROM customers WHERE mobile=%s", (mobile,))
    row = cur.fetchone()

    if row:
        customer_id = row["id"]
    else:
        cur.execute("""
            INSERT INTO customers (name, mobile, address)
            VALUES (%s,%s,%s)
        """, (customer_name, mobile, address))
        customer_id = cur.lastrowid

    # ================= SALE =================
    cur.execute("""
        INSERT INTO sales
        (customer_id, customer_address, total_amount, payment_mode, payment_status)
        VALUES (%s,%s,%s,%s,'PENDING')
    """, (customer_id, address, total_amount, payment_mode))

    sale_id = cur.lastrowid

    # ================= ITEMS + STOCK =================
    for item in items:

        qty = int(item["quantity"])
        price = float(item["price"])
        source = item.get("source")

        # =================================================
        # 🔹 MANUAL ITEM (NO STOCK, NO VALIDATION)
        # =================================================
        if source == "MANUAL":
            cur.execute("""
                INSERT INTO sale_items
                (sale_id, item_name, unit, quantity, price)
                VALUES (%s,%s,%s,%s,%s)
            """, (
                sale_id,
                item["item_name"],
                item.get("unit", ""),
                qty,
                price
            ))
            continue  # 🚨 VERY IMPORTANT

        # =================================================
        # 🔹 OIL PRODUCT (Finished Stock Only)
        # =================================================
        if source == "OIL":
            oil = item["item_name"]
            size = int(item["bottle_size_ml"])

            cur.execute("""
                SELECT quantity
                FROM finished_stock
                WHERE oil_type=%s
                  AND bottle_size_ml=%s
                  AND is_ready_for_sale = 1
            """, (oil, size))

            fs = cur.fetchone()

            if not fs or fs["quantity"] < qty:
                flash(f"❌ Not enough stock for {oil} {size} ml", "danger")
                mysql.connection.rollback()
                return redirect(url_for("sale"))

            # Save sale item
            cur.execute("""
                INSERT INTO sale_items
                (sale_id, oil_type, bottle_size_ml, quantity, price)
                VALUES (%s,%s,%s,%s,%s)
            """, (sale_id, oil, size, qty, price))

            # Reduce finished stock
            cur.execute("""
                UPDATE finished_stock
                SET quantity = quantity - %s
                WHERE oil_type=%s AND bottle_size_ml=%s
            """, (qty, oil, size))

        # =================================================
        # 🔹 DIRECT PRODUCT (Sale Stock + FIFO)
        # =================================================
        else:
            name = item["item_name"]
            unit = item["unit"]

            cur.execute("""
                INSERT INTO sale_items
                (sale_id, item_name, unit, quantity, price)
                VALUES (%s,%s,%s,%s,%s)
            """, (sale_id, name, unit, qty, price))

            # Reduce sale stock
            cur.execute("""
                UPDATE sale_stock
                SET quantity = quantity - %s
                WHERE item_name=%s AND unit=%s
            """, (qty, name, unit))

            # FIFO from purchase_items
            cur.execute("""
                SELECT id, quantity, used_qty
                FROM purchase_items
                WHERE item_name=%s AND unit=%s
                ORDER BY id ASC
            """, (name, unit))

            rows = cur.fetchall()
            qty_to_reduce = qty

            for r in rows:
                available = float(r["quantity"]) - float(r["used_qty"])
                if available <= 0:
                    continue

                take = min(available, qty_to_reduce)

                cur.execute("""
                    UPDATE purchase_items
                    SET used_qty = COALESCE(used_qty, 0) + %s
                    WHERE id = %s
                """, (take, r["id"]))

                qty_to_reduce -= take
                if qty_to_reduce <= 0:
                    break

    mysql.connection.commit()
    cur.close()

    return redirect(url_for(
        "payments",
        sale_id=sale_id,
        customer=customer_name,
        mobile=mobile,
        total=total_amount
    ))

@app.route("/sales-history")
def sales_list():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # 🔹 Get sales + customer + receipt status
    cur.execute("""
        SELECT
            s.id,
            s.total_amount,
            s.created_at,
            c.name AS customer,
            r.payment_status,
            r.payment_mode
        FROM sales s
        JOIN customers c ON c.id = s.customer_id
        LEFT JOIN receipts r ON r.sale_id = s.id
        ORDER BY s.id DESC
    """)
    sales = cur.fetchall()

    # 🔹 Fetch items for each sale
    for s in sales:
        cur.execute("""
            SELECT
                COALESCE(oil_type, item_name) AS product,
                bottle_size_ml,
                unit,
                quantity,
                price
            FROM sale_items
            WHERE sale_id = %s
        """, (s["id"],))

        s["items"] = cur.fetchall()

        # If no receipt yet
        if not s["payment_status"]:
            s["payment_status"] = "PENDING"

    cur.close()

    return render_template("sales_list.html", sales=sales)


# ================= Save sale return =================
@app.route("/save-sale-return", methods=["POST"])
def save_sale_return():
    if not login_required():
        return redirect(url_for("login"))

    sale_id = request.form["sale_id"]
    qty = int(request.form["quantity"])
    reason = request.form.get("reason", "")

    # These decide product type
    oil = request.form.get("oil_type")              # present only for OIL
    size = request.form.get("bottle_size_ml")
    item_name = request.form.get("item_name")       # present only for DIRECT
    unit = request.form.get("unit")

    cur = mysql.connection.cursor()

    # ================= OIL RETURN (KEEP YOUR EXISTING LOGIC) =================
    if oil and size:
        size = int(size)

        # 🔹 Get price from sale_items
        cur.execute("""
            SELECT price
            FROM sale_items
            WHERE sale_id=%s AND oil_type=%s AND bottle_size_ml=%s
        """, (sale_id, oil, size))

        row = cur.fetchone()
        if not row:
            flash("❌ Sale item not found", "danger")
            return redirect(url_for("dashboard"))

        refund_amount = float(row["price"]) * qty

        # 🔹 Save return record
        cur.execute("""
            INSERT INTO sale_returns
            (sale_id, oil_type, bottle_size_ml, quantity, return_amount, reason, return_date)
            VALUES (%s,%s,%s,%s,%s,%s,CURDATE())
        """, (sale_id, oil, size, qty, refund_amount, reason))

        # 🔹 Restore finished stock
        cur.execute("""
            UPDATE finished_stock
            SET quantity = quantity + %s
            WHERE oil_type=%s AND bottle_size_ml=%s
        """, (qty, oil, size))

    # ================= DIRECT PRODUCT RETURN (NEW LOGIC) =================
    else:
        # 🔹 Get price from sale_items
        cur.execute("""
            SELECT price
            FROM sale_items
            WHERE sale_id=%s AND item_name=%s AND unit=%s
        """, (sale_id, item_name, unit))

        row = cur.fetchone()
        if not row:
            flash("❌ Sale item not found", "danger")
            return redirect(url_for("dashboard"))

        refund_amount = float(row["price"]) * qty

        # 🔹 Save return record
        cur.execute("""
            INSERT INTO sale_returns
            (sale_id, item_name, unit, quantity, return_amount, reason, return_date)
            VALUES (%s,%s,%s,%s,%s,%s,CURDATE())
        """, (sale_id, item_name, unit, qty, refund_amount, reason))

        # 🔹 Restore SALE STOCK
        cur.execute("""
            UPDATE sale_stock
            SET quantity = quantity + %s
            WHERE item_name=%s AND unit=%s
        """, (qty, item_name, unit))

        # 🔹 RESTORE PURCHASE ITEMS (FIFO REVERSE)
        cur.execute("""
            SELECT id, used_qty
            FROM purchase_items
            WHERE item_name=%s AND unit=%s AND used_qty > 0
            ORDER BY id DESC
        """, (item_name, unit))

        rows = cur.fetchall()
        qty_to_restore = qty

        for r in rows:
            if qty_to_restore <= 0:
                break

            take = min(float(r["used_qty"]), qty_to_restore)

            cur.execute("""
                UPDATE purchase_items
                SET used_qty = used_qty - %s
                WHERE id = %s
            """, (take, r["id"]))

            qty_to_restore -= take

    mysql.connection.commit()
    cur.close()

    flash("✅ Sale return processed successfully", "success")
    return redirect(url_for("dashboard"))






# ================= CUSTOMERS =================
@app.route("/customers")
def customers():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("SELECT name, mobile, created_at FROM customers ORDER BY id DESC")
    customers = cur.fetchall()

    cur.close()

    return render_template("customers.html", customers=customers)





@app.route("/production")
def production():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT category, product_name
        FROM product_master
        WHERE is_active = 1
        ORDER BY category, product_name
    """)
    rows = cur.fetchall()
    cur.close()

    products = {}
    for r in rows:
        products.setdefault(r["category"], []).append(r["product_name"])

    return render_template("production.html", products=products)



@app.route("/save-production-batch", methods=["POST"])
def save_production_batch():
    if not login_required():
        return redirect(url_for("login"))

    oil_type = request.form["oil_type"]
    raw_material = request.form["raw_material"]
    raw_qty = float(request.form["raw_qty"])
    oil_extracted = float(request.form["oil_extracted"])
    oil_cake = float(request.form.get("oil_cake") or 0)
    wastage = float(request.form.get("wastage") or 0)
    container = request.form["container_code"]
    machine = request.form["machine"]
    operator = request.form["operator"]

    yield_percent = round((oil_extracted / raw_qty) * 100, 2)
    batch_no = f"PRD-{oil_type[:2].upper()}-{datetime.now().strftime('%Y%m%d%H%M')}"

    cur = mysql.connection.cursor()

    # Save production batch
    cur.execute("""
        INSERT INTO production_batches
        (batch_no, oil_type, raw_material, raw_qty_kg,
         oil_extracted_ltr, oil_cake_kg, wastage_kg,
         yield_percent, container_code, production_date,
         machine, operator)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURDATE(),%s,%s)
    """, (
        batch_no, oil_type, raw_material, raw_qty,
        oil_extracted, oil_cake, wastage,
        yield_percent, container, machine, operator
    ))

    # Update container stock
    cur.execute("""
        INSERT INTO oil_containers (container_code, oil_type, current_qty_ltr)
        VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE
        current_qty_ltr = current_qty_ltr + %s
    """, (container, oil_type, oil_extracted, oil_extracted))

    mysql.connection.commit()
    cur.close()

    flash("✅ Production batch saved successfully", "success")
    return redirect(url_for("bottling"))


@app.route("/production-history")
def production_history():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
    pb.production_date,
    pb.batch_no,
    pb.oil_type,
    pb.container_code,
    pb.oil_extracted_ltr,

    COALESCE(
        SUM(br.quantity * br.bottle_size_ml) / 1000,
        0
    ) AS bottled_ltr,

    pb.oil_extracted_ltr
      - COALESCE(
            SUM(br.quantity * br.bottle_size_ml) / 1000,
            0
        ) AS remaining_ltr

FROM production_batches pb
LEFT JOIN bottling_records br
    ON pb.batch_no = br.batch_no
GROUP BY pb.id
ORDER BY pb.production_date DESC;
    """)

    rows = cur.fetchall()
    cur.close()

    return render_template("production_history.html", data=rows)


@app.route("/allocate-rack-stock", methods=["POST"])
def allocate_rack_stock():
    if not login_required():
        return {"status": "unauthorized"}, 401

    data = request.get_json()
    items = data.get("items", [])

    if not items:
        return {"status": "error", "msg": "No items"}, 400

    cur = mysql.connection.cursor()

    try:
        for item in items:
            oil = item.get("oil")
            size = item.get("size")          # ml / gram / pcs value
            qty = int(item.get("quantity"))
            price = float(item.get("price"))
            source = item.get("source", "RACK")

            # ================= MANUAL ITEM =================
            if source == "MANUAL":
                unit = item.get("unit")

                cur.execute("""
                    INSERT INTO sale_stock
                    (item_name, unit, quantity, selling_price)
                    VALUES (%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        quantity = quantity + %s,
                        selling_price = %s
                """, (oil, unit, qty, price, qty, price))

                continue

            # ================= RACK (BOTTLED) ITEM =================
            size = int(size)

            # 🔒 Validate rack stock
            cur.execute("""
                SELECT quantity
                FROM finished_stock
                WHERE oil_type=%s AND bottle_size_ml=%s
            """, (oil, size))
            row = cur.fetchone()

            if not row or row["quantity"] < qty:
                mysql.connection.rollback()
                return {
                    "status": "error",
                    "msg": f"Not enough rack stock for {oil} {size}"
                }, 400

            # 🔹 Reduce rack stock
            cur.execute("""
                UPDATE finished_stock
                SET quantity = quantity - %s
                WHERE oil_type=%s AND bottle_size_ml=%s
            """, (qty, oil, size))

            # 🔹 Add to sale stock
            cur.execute("""
                INSERT INTO sale_stock
                (item_name, unit, quantity, selling_price)
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    quantity = quantity + %s,
                    selling_price = %s
            """, (
                oil,
                f"{size} ML",
                qty,
                price,
                qty,
                price
            ))

        mysql.connection.commit()
        return {"status": "success"}

    except Exception as e:
        mysql.connection.rollback()
        return {"status": "error", "msg": str(e)}, 500

    finally:
        cur.close()


@app.route("/bottling")
def bottling():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT container_code, oil_type, current_qty_ltr
        FROM oil_containers
        WHERE current_qty_ltr > 0
        ORDER BY container_code
    """)
    containers = cur.fetchall()
    cur.close()

    return render_template("bottling.html", containers=containers)


@app.route("/save-bottling", methods=["POST"])
def save_bottling():
    if not login_required():
        return redirect(url_for("login"))

    container = request.form["container_code"]
    oil_type = request.form["oil_type"]
    bottle_size_ml = int(request.form["bottle_size"])
    qty = int(request.form["quantity"])

    oil_used_ltr = round((bottle_size_ml * qty) / 1000, 2)

    cur = mysql.connection.cursor()

    # 🔹 Check container stock
    cur.execute("""
        SELECT current_qty_ltr
        FROM oil_containers
        WHERE container_code=%s AND oil_type=%s
    """, (container, oil_type))
    row = cur.fetchone()

    if not row:
        flash("❌ Container not found for this oil", "danger")
        return redirect(url_for("bottling"))

    if row["current_qty_ltr"] < oil_used_ltr:
        flash("❌ Not enough oil in container", "danger")
        return redirect(url_for("bottling"))

    # 🔹 Find latest production batch for this container
    cur.execute("""
        SELECT batch_no
        FROM production_batches
        WHERE container_code = %s AND oil_type = %s
        ORDER BY id DESC
        LIMIT 1
    """, (container, oil_type))
    batch = cur.fetchone()

    if not batch:
        flash("❌ No production batch found for this container", "danger")
        return redirect(url_for("bottling"))

    batch_no = batch["batch_no"]

    # 🔹 Deduct oil from container
    cur.execute("""
        UPDATE oil_containers
        SET current_qty_ltr = current_qty_ltr - %s
        WHERE container_code = %s AND oil_type = %s
    """, (oil_used_ltr, container, oil_type))

    # 🔹 Save bottling record with batch number
    cur.execute("""
        INSERT INTO bottling_records
        (batch_no, container_code, oil_type, bottle_size_ml, quantity, oil_used_ltr, bottling_date)
        VALUES (%s,%s,%s,%s,%s,%s,CURDATE())
    """, (batch_no, container, oil_type, bottle_size_ml, qty, oil_used_ltr))

    # 🔹 Add bottles to rack stock
    cur.execute("""
        INSERT INTO finished_stock
        (oil_type, bottle_size_ml, quantity, is_ready_for_sale)
        VALUES (%s,%s,%s,0)
        ON DUPLICATE KEY UPDATE
            quantity = quantity + %s
    """, (oil_type, bottle_size_ml, qty, qty))

    mysql.connection.commit()
    cur.close()

    flash(f"✅ Bottling saved from Batch {batch_no}", "success")
    return redirect(url_for("finished_stock"))


#==================Add heloer for billing====================
def get_available_stock():
    cur = mysql.connection.cursor()

    # 🛢 Bottled oils
    cur.execute("""
        SELECT 
            fs.oil_type AS item_name,
            CONCAT(fs.bottle_size_ml, ' ML') AS unit,
            fs.quantity,
            fs.selling_price,
            'OIL' AS source,
            fs.bottle_size_ml
        FROM finished_stock fs
        WHERE fs.quantity > 0
          AND fs.is_ready_for_sale = 1
    """)

    oils = cur.fetchall()

    # 📦 Direct resale items
    cur.execute("""
        SELECT
            item_name,
            unit,
            quantity,
            selling_price,
            'DIRECT' AS source,
            NULL AS bottle_size_ml
        FROM sale_stock
        WHERE quantity > 0
    """)
    resale = cur.fetchall()

    cur.close()
    return oils + resale



@app.route("/sale-stock")
def sale_stock_page():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT item_name, unit, quantity, cost_price, selling_price
        FROM sale_stock
        ORDER BY item_name
    """)
    data = cur.fetchall()
    cur.close()

    return render_template("sale_stock.html", stock=data)

# ================= PAYMENTS RECEIVED =================
@app.route("/payments")
def payments():
    if not login_required():
        return redirect(url_for("login"))

    customer_name = request.args.get("customer", "Walking Customer")
    total_amount = request.args.get("total", "0.00")
    voucher_no = random.randint(1000, 9999)
    sale_id = request.args.get("sale_id")

    return render_template(
        "payments.html",
        customer_name=customer_name,
        total_amount=total_amount,
        voucher_no=voucher_no,
        sale_id=sale_id  # 🔑 REQUIRED
    )


@app.route("/generate-invoice")
def generate_invoice():
    customer = request.args.get("cust")
    amount = request.args.get("amt")
    mode = request.args.get("mode")
    sale_id = request.args.get("sale_id")

    if not customer or not amount or not mode or not sale_id:
        flash("Invalid access to invoice", "danger")
        return redirect(url_for("receipts"))

    amount = Decimal(str(amount))

    # ================= GST RULE =================
    # GST applies to Credit, UPI, Card
    # GST does NOT apply only for Cash
    if mode != "Cash":
        gst_rate = Decimal("0.05")  # 5%
        taxable = (amount / (1 + gst_rate)).quantize(Decimal("0.01"))
        gst = (amount - taxable).quantize(Decimal("0.01"))
        cgst = (gst / 2).quantize(Decimal("0.01"))
        sgst = (gst / 2).quantize(Decimal("0.01"))
    else:
        taxable = amount
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")

    # ================= PAYMENT STATUS =================
    payment_status = "DUE" if mode == "Credit" else "PAID"
    entry_type = "CREDIT_NOTE" if mode == "Credit" else "RECEIPT"

    receipt_no = generate_receipt_no()

    # ================= SAVE RECEIPT =================
    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO receipts
        (receipt_no, sale_id, customer_name, amount, taxable,
         cgst, sgst, payment_mode, payment_status, entry_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        receipt_no,
        sale_id,
        customer,
        amount,
        taxable,
        cgst,
        sgst,
        mode,
        payment_status,
        entry_type
    ))

    receipt_id = cur.lastrowid
    mysql.connection.commit()
    cur.close()

    return redirect(url_for("view_receipt", rid=receipt_id))

# ================= RECEIPTS =================
@app.route("/receipts")
def receipts():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM receipts ORDER BY id DESC")
    data = cur.fetchall()
    cur.close()

    return render_template("receipts_list.html", receipts=data)


@app.route("/receipt/<int:rid>")
def view_receipt(rid):
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # ================= RECEIPT =================
    cur.execute("SELECT * FROM receipts WHERE id = %s", (rid,))
    r = cur.fetchone()

    if not r:
        cur.close()
        flash("Receipt not found", "danger")
        return redirect(url_for("receipts"))

    # ================= CUSTOMER MOBILE =================
    cur.execute("""
        SELECT c.mobile
        FROM sales s
        JOIN customers c ON c.id = s.customer_id
        WHERE s.id = %s
    """, (r["sale_id"],))
    cust = cur.fetchone()
    mobile = str(cust["mobile"]).strip() if cust else ""

    # ================= SALE ITEMS =================
    cur.execute("""
        SELECT 
            COALESCE(oil_type, item_name) AS product,
            bottle_size_ml,
            unit,
            batch_no,
            quantity,
            price
        FROM sale_items
        WHERE sale_id = %s
    """, (r["sale_id"],))

    raw_items = cur.fetchall()

    # ================= BUILD ITEMS =================
    items = []

    for i in raw_items:
        price = Decimal(str(i["price"]))
        qty = int(i["quantity"])
        subtotal = price * qty

        # GST only for UPI / Card
        if r["payment_mode"] in ["UPI", "Card"]:
            taxable = subtotal / Decimal("1.05")
            gst = subtotal - taxable
        else:
            taxable = subtotal
            gst = Decimal("0.00")

        # Name formatting
        if i["bottle_size_ml"]:
            name = f'{i["product"]} ({i["bottle_size_ml"]} ml)'
        else:
            name = f'{i["product"]} ({i["unit"]})'

        items.append({
            "name": name,
            "batch_no": i["batch_no"] or "",
            "quantity": qty,
            "subtotal": float(subtotal),
            "taxable": float(taxable),
            "gst": float(gst),
            "total": float(subtotal)
        })

    cur.close()

    # ================= RENDER =================
    return render_template(
        "receipts.html",
        datetime=datetime,
        customer=r["customer_name"],
        mobile=mobile,
        receipt_no=r["receipt_no"],
        amount=float(r["amount"]),
        taxable=float(r["taxable"]),
        cgst=float(r["cgst"]),
        sgst=float(r["sgst"]),
        mode=r["payment_mode"],
        payment_status=r["payment_status"],
        items=items
    )



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

@app.route("/reports/monthly-sales-data")
def monthly_sales_data():
    # IMPORTANT: APIs must NEVER redirect
    if "admin" not in session:
        return {"labels": [], "values": []}

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            DATE_FORMAT(created_at, '%b %Y') AS month,
            SUM(amount) AS total
        FROM receipts
        WHERE payment_status = 'PAID'
        GROUP BY YEAR(created_at), MONTH(created_at)
        ORDER BY YEAR(created_at), MONTH(created_at)
    """)
    rows = cur.fetchall()
    cur.close()

    return {
        "labels": [r["month"] for r in rows],
        "values": [float(r["total"]) for r in rows]
    }


@app.route("/gst-return")
def gst_return():
    if not login_required():
        return redirect(url_for("login"))

    # 📅 Month selection (YYYY-MM)
    month = request.args.get("month")
    if not month:
        month = datetime.now().strftime("%Y-%m")

    cur = mysql.connection.cursor()  # DictCursor already configured

    # 🔒 Check if GST return already locked
    cur.execute("""
        SELECT *
        FROM gst_returns
        WHERE return_month = %s
    """, (month,))
    gst = cur.fetchone()

    # 🧮 If not locked, calculate GST fresh
    if not gst:
        # 🔹 Output GST from PAID receipts
        cur.execute("""
            SELECT 
                COALESCE(SUM(taxable), 0) AS taxable,
                COALESCE(SUM(cgst), 0) AS cgst,
                COALESCE(SUM(sgst), 0) AS sgst
            FROM receipts
            WHERE payment_status = 'PAID'
              AND DATE_FORMAT(created_at, '%%Y-%%m') = %s
        """, (month,))
        r = cur.fetchone()

        taxable = float(r["taxable"])
        cgst = float(r["cgst"])
        sgst = float(r["sgst"])
        igst = 0.0  # ✅ No IGST in current system (intra-state sales)

        # 🔹 Input Tax Credit from GSTR-2B (eligible only)
        cur.execute("""
            SELECT 
                COALESCE(SUM(cgst + sgst), 0) AS itc
            FROM gstr_2b
            WHERE itc_status = 'ELIGIBLE'
              AND return_period = %s
        """, (month,))
        itc = float(cur.fetchone()["itc"])

        # 🔹 Net GST payable
        net_gst = (cgst + sgst + igst) - itc

        # 💾 Lock GST return (very important in real systems)
        cur.execute("""
            INSERT INTO gst_returns
            (return_month, taxable_sales, cgst, sgst, igst, itc, net_gst)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (month, taxable, cgst, sgst, igst, itc, net_gst))
        mysql.connection.commit()

        # 🔄 Fetch locked record
        cur.execute("""
            SELECT *
            FROM gst_returns
            WHERE return_month = %s
        """, (month,))
        gst = cur.fetchone()

    # 🧾 Audit log (mandatory in real ERP / CA systems)
    cur.execute("""
        INSERT INTO gst_audit_logs
        (return_month, action, user_role)
        VALUES (%s, 'VIEWED', 'ADMIN')
    """, (month,))
    mysql.connection.commit()
    cur.close()

    return render_template(
        "gst_return.html",
        gst=gst,
        current_month=datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    )





@app.route("/gstr-2a")
def gstr_2a():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    return_period = datetime.now().strftime("%Y-%m")

    cur.execute("""
        SELECT invoice_no, supplier_name, supplier_gstin,
               invoice_date, taxable,
               (cgst + sgst + igst) AS gst
        FROM gstr_2a
        WHERE return_period = %s
        ORDER BY invoice_date
    """, (return_period,))
    invoices = cur.fetchall()

    cur.close()

    return render_template(
        "gstr_2a.html",
        invoices=invoices,
        return_period=return_period
    )


@app.route("/gstr-2b")
def gstr_2b():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            p.bill_no AS invoice_no,
            p.bill_date AS invoice_date,
            p.vendor_name AS supplier_name,
            p.gstin AS supplier_gstin,
            pi.taxable_amount AS taxable,
            pi.gst_amount AS gst,
            pi.itc_status
        FROM purchases p
        JOIN purchase_items pi ON p.id = pi.purchase_id
    """)
    rows = cur.fetchall()
    cur.close()

    invoices = []
    eligible_itc = 0
    ineligible_itc = 0
    reversed_itc = 0

    for r in rows:
        taxable = float(r["taxable"] or 0)
        gst = float(r["gst"] or 0)
        status = r["itc_status"] or "ELIGIBLE"

        if status == "ELIGIBLE":
            eligible_itc += gst
        elif status == "INELIGIBLE":
            ineligible_itc += gst
        else:
            reversed_itc += gst

        invoices.append({
            "invoice_no": r["invoice_no"],
            "invoice_date": r["invoice_date"].strftime("%d-%m-%Y"),
            "supplier_name": r["supplier_name"],
            "supplier_gstin": r["supplier_gstin"],
            "taxable": taxable,
            "gst": gst,
            "itc_status": status
        })

    summary = {
        "total_invoices": len(invoices),
        "eligible_itc": eligible_itc,
        "ineligible_itc": ineligible_itc,
        "reversed_itc": reversed_itc
    }

    return render_template(
        "gstr_2b.html",
        summary=summary,
        invoices=invoices
    )

@app.route("/download-gstr-3b")
def download_gstr_3b():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # ===== OUTPUT GST (FROM PAID RECEIPTS) =====
    cur.execute("""
        SELECT 
            COALESCE(SUM(taxable), 0) AS taxable,
            COALESCE(SUM(cgst), 0) AS cgst,
            COALESCE(SUM(sgst), 0) AS sgst
        FROM receipts
        WHERE payment_status = 'PAID'
          AND DATE_FORMAT(created_at, '%%Y-%%m') = DATE_FORMAT(CURDATE(), '%%Y-%%m')
    """)
    sales = cur.fetchone()

    output_gst = float(sales["cgst"]) + float(sales["sgst"])

    # ===== INPUT TAX CREDIT (GSTR-2B) =====
    cur.execute("""
        SELECT 
            COALESCE(SUM(cgst + sgst), 0) AS itc
        FROM gstr_2b
        WHERE itc_status = 'ELIGIBLE'
          AND return_period = DATE_FORMAT(CURDATE(), '%%Y-%%m')
    """)
    itc = float(cur.fetchone()["itc"])

    cur.close()

    net_gst = output_gst - itc
    igst = 0.0  # currently no interstate sales

    return render_template(
        "gstr_3b_pdf.html",
        taxable=float(sales["taxable"]),
        cgst=float(sales["cgst"]),
        sgst=float(sales["sgst"]),
        igst=igst,
        output_gst=output_gst,
        itc=itc,
        net_gst=net_gst,
        date=datetime.now().strftime("%d-%m-%Y")
    )

@app.route("/gst-audit")
def gst_audit():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()  # ✅ DictCursor already applied globally
    cur.execute("""
        SELECT * FROM gst_audit_logs
        ORDER BY action_time DESC
    """)
    logs = cur.fetchall()
    cur.close()

    return render_template("gst_audit.html", logs=logs)

# ================= OTHER MODULES =================
@app.route("/purchase")
def purchase():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, bank_name, account_name, account_no, ifsc
        FROM bank_accounts
        WHERE is_active = 1
        ORDER BY bank_name
    """)
    banks = cur.fetchall()
    cur.close()

    return render_template("purchase.html", banks=banks)

@app.route("/api/save-bank", methods=["POST"])
def save_bank():
    if not login_required():
        return {"status": "error"}

    data = request.get_json()

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO bank_accounts
        (bank_name, account_name, account_no, ifsc, branch)
        VALUES (%s,%s,%s,%s,%s)
    """, (
        data["bank_name"],
        data["account_name"],
        data["account_no"],
        data["ifsc"],
        data["branch"]
    ))
    mysql.connection.commit()

    bank_id = cur.lastrowid
    cur.close()

    return {
        "status": "success",
        "id": bank_id,
        "label": f'{data["bank_name"]} | {data["account_no"][-4:]} | {data["account_name"]}'
    }



@app.route("/save-purchase", methods=["POST"])
def save_purchase():
    if not login_required():
        return redirect(url_for("login"))

    vendor = request.form.get("vendor_name")
    bill_no = request.form.get("bill_no")
    bill_date = request.form.get("bill_date")
    total = float(request.form.get("total_amount") or 0)

    payment_mode = request.form.get("payment_mode")

    # 🔑 Payment status logic
    payment_status = "PAID"
    if payment_mode == "CREDIT":
        payment_status = "DUE"

    items_json = request.form.get("items_json")
    items = json.loads(items_json) if items_json else []

    cur = mysql.connection.cursor()

    # 1️⃣ Save purchase master
    cur.execute("""
        INSERT INTO purchases 
        (vendor_name, bill_no, bill_date, total_amount, payment_mode, payment_status)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        vendor,
        bill_no,
        bill_date,
        total,
        payment_mode,
        payment_status
    ))
    purchase_id = cur.lastrowid

    # 🔹 Save vendor payment if PAID
    if payment_status == "PAID":
        cur.execute("""
            INSERT INTO vendor_payments
            (vendor_name, purchase_id, amount, payment_mode, payment_status, payment_date)
            VALUES (%s,%s,%s,%s,'PAID',CURDATE())
        """, (
            vendor,
            purchase_id,
            total,
            payment_mode
        ))

    for item in items:
        cur.execute("""
            INSERT INTO purchase_items
            (purchase_id, item_name, quantity, remaining_qty, cost_price, total, unit)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            purchase_id,
            item["item"],
            item["qty"],
            item["qty"],
            item["cost"],
            item["total"],
            item["unit"]
        ))

        # 🔥 If this item is for SALE
        if item["add_to_sale"]:
            cur.execute("""
                INSERT INTO sale_stock
                (item_name, unit, quantity, cost_price, selling_price)
                VALUES (%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    quantity = quantity + %s,
                    cost_price = %s,
                    selling_price = %s
            """, (
                item["item"],
                item["unit"],
                item["qty"],
                item["cost"],
                item["sell"],
                item["qty"],
                item["cost"],
                item["sell"]
            ))

    mysql.connection.commit()
    cur.close()

    flash("✅ Purchase saved successfully", "success")
    return redirect(url_for("purchase_list"))

from MySQLdb.cursors import DictCursor

@app.route("/purchase-list")
def purchase_list():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor(DictCursor)

    cur.execute("""
        SELECT 
            p.id,
            p.bill_date,
            p.vendor_name,
            p.bill_no,
            p.total_amount
        FROM purchases p
        ORDER BY p.id DESC
    """)
    purchases = cur.fetchall()
    # 🔁 Fetch items for each purchase
    for p in purchases:
        cur.execute("""
            SELECT 
                item_name,
                quantity,
                unit,
                cost_price,
                COALESCE(used_qty, 0) AS used_qty
            FROM purchase_items
            WHERE purchase_id = %s
        """, (p["id"],))

        p["purchase_items"] = cur.fetchall()

    cur.close()
    return render_template("purchase_list.html", purchases=purchases)




@app.route("/eway-bill")
def eway_bill():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("eway_bill.html")



@app.route("/reconciliation")
def reconciliation():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            p.bill_no AS invoice_no,
            p.vendor_name,
            p.supplier_gstin,
            p.taxable AS system_taxable,
            g.taxable AS gstr_taxable,
            p.cgst + p.sgst + p.igst AS system_gst,
            g.cgst + g.sgst + g.igst AS gstr_gst,
            CASE
                WHEN g.invoice_no IS NULL THEN 'MISSING'
                WHEN ABS(p.taxable - g.taxable) > 1 THEN 'MISMATCH'
                ELSE 'MATCHED'
            END AS status
        FROM purchases p
        LEFT JOIN gstr_2b g
            ON p.bill_no = g.invoice_no
           AND p.supplier_gstin = g.supplier_gstin
    """)

    rows = cur.fetchall()
    cur.close()

    return render_template("reconciliation.html", rows=rows)


#=============Finished Stock==================
@app.route("/finished-stock")
def finished_stock():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # Products for dropdown
    cur.execute("""
        SELECT product_name, unit_type
        FROM product_master
        WHERE is_active = 1
        ORDER BY product_name
    """)
    products = cur.fetchall()

    # Rack stock (SHOW ALL, BUT WITH STATUS)
    cur.execute("""
        SELECT
            oil_type,
            bottle_size_ml,
            quantity,
            selling_price,
            is_ready_for_sale
        FROM finished_stock
        WHERE quantity > 0
        ORDER BY oil_type, bottle_size_ml
    """)
    rack = cur.fetchall()

    cur.close()

    return render_template(
        "finished_stock.html",
        products=products,
        rack=rack
    )

@app.route("/save-finished-stock", methods=["POST"])
def save_finished_stock():
    if not login_required():
        return redirect(url_for("login"))

    # 🔹 REQUIRED FIELDS
    selling_price = float(request.form.get("selling_price") or 0)
    product = request.form.get("oil_type")
    new_product = request.form.get("new_product")
    size_val = request.form.get("bottle_size_ml")
    custom_size = request.form.get("custom_size")
    qty = int(request.form.get("quantity"))

    if selling_price <= 0:
        flash("❌ Selling price must be greater than 0", "danger")
        return redirect(url_for("finished_stock"))

    # 🔹 HANDLE NEW PRODUCT
    if product == "__new__":
        product = new_product.strip()

        if not product:
            flash("❌ Product name required", "danger")
            return redirect(url_for("finished_stock"))

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT IGNORE INTO product_master (product_name, category)
            VALUES (%s,'Custom')
        """, (product,))
        mysql.connection.commit()
        cur.close()

    # 🔹 HANDLE SIZE (NORMAL + CUSTOM)
    if size_val == "CUSTOM":
        if not custom_size:
            flash("❌ Enter custom size", "danger")
            return redirect(url_for("finished_stock"))

        s = custom_size.lower().strip()
        num = "".join(c for c in s if c.isdigit() or c == ".")
        unit = "".join(c for c in s if c.isalpha())

        if not num or not unit:
            flash("❌ Invalid custom size format", "danger")
            return redirect(url_for("finished_stock"))

        num = float(num)

        if unit in ["ml"]:
            size = int(num)
        elif unit in ["l", "litre", "liter"]:
            size = int(num * 1000)
        elif unit in ["g", "gm", "gram"]:
            size = int(num)
        elif unit in ["kg"]:
            size = int(num * 1000)
        elif unit in ["pc", "pcs"]:
            size = int(num)
        else:
            flash("❌ Unsupported size unit", "danger")
            return redirect(url_for("finished_stock"))
    else:
        size = int(size_val)

    # 🔐 VALIDATIONS
    product_lower = product.lower()

    if "ghee" in product_lower and size not in (200, 250, 500, 1000):
        flash("❌ Invalid size for ghee", "danger")
        return redirect(url_for("finished_stock"))

    if "ghee" not in product_lower and size < 200:
        flash("❌ Invalid size for oil/product", "danger")
        return redirect(url_for("finished_stock"))

    # 🔹 SAVE / UPDATE FINISHED STOCK
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT id FROM finished_stock
        WHERE oil_type=%s AND bottle_size_ml=%s
    """, (product, size))

    row = cur.fetchone()

    if row:
        # ✅ UPDATE EXISTING STOCK
        cur.execute("""
                   UPDATE finished_stock
        SET
            quantity = quantity + %s,
            selling_price = %s,
            is_ready_for_sale = 1
        WHERE oil_type=%s AND bottle_size_ml=%s
        """, (qty, selling_price, product, size))


    else:
        # ✅ INSERT NEW STOCK
        cur.execute("""
                 INSERT INTO finished_stock
        (oil_type, bottle_size_ml, quantity, selling_price, is_ready_for_sale)
        VALUES (%s,%s,%s,%s,1)
        """, (product, size, qty, selling_price))

    mysql.connection.commit()
    cur.close()

    flash("✅ Finished stock saved successfully", "success")
    return redirect(url_for("finished_stock"))

#####################BANK######################
@app.route("/bank-accounts")
def bank_accounts():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, bank_name, account_name, account_no, ifsc, branch
        FROM bank_accounts
        WHERE is_active = 1
        ORDER BY bank_name
    """)
    banks = cur.fetchall()
    cur.close()

    return render_template("bank_accounts.html", banks=banks)

@app.route("/add-bank-account", methods=["POST"])
def add_bank_account():
    if not login_required():
        return redirect(url_for("login"))

    bank_name = request.form["bank_name"]
    account_name = request.form["account_name"]
    account_no = request.form["account_no"]
    ifsc = request.form["ifsc"]
    branch = request.form["branch"]

    cur = mysql.connection.cursor()
    cur.execute("""
        INSERT INTO bank_accounts
        (bank_name, account_name, account_no, ifsc, branch)
        VALUES (%s,%s,%s,%s,%s)
    """, (bank_name, account_name, account_no, ifsc, branch))

    mysql.connection.commit()
    cur.close()

    flash("✅ Bank account added", "success")
    return redirect(url_for("bank_accounts"))

@app.route("/cash-in-hand")
def cash_in_hand():
    return render_template("cash_in_hand.html")

@app.route("/cheques")
def cheques():
    return render_template("cheques.html")



# ================= PDF PREVIEW =================
@app.route("/invoice/<int:invoice_id>/pdf")
def invoice_pdf(invoice_id):
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor(DictCursor)

    # 1️⃣ Invoice / Sale master
    cur.execute("""
        SELECT 
            id,
            customer_name,
            payment_mode,
            total_amount,
            taxable,
            cgst,
            sgst,
            created_at
        FROM sales
        WHERE id = %s
    """, (invoice_id,))
    invoice = cur.fetchone()

    if not invoice:
        cur.close()
        flash("Invoice not found", "error")
        return redirect(url_for("sales_list"))

    # 2️⃣ Sold items
    cur.execute("""
        SELECT 
            item_name,
            quantity,
            price,
            total
        FROM sale_items
        WHERE sale_id = %s
    """, (invoice_id,))
    items = cur.fetchall()

    cur.close()

    return render_template(
        "invoice_pdf.html",
        invoice=invoice,
        items=items
    )

@app.route("/api/vendors")
def api_vendors():
    if "admin" not in session:
        return []

    q = request.args.get("q", "").strip()

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT DISTINCT vendor_name
        FROM purchases
        WHERE vendor_name LIKE %s
        ORDER BY vendor_name
        LIMIT 10
    """, (q + "%",))
    rows = cur.fetchall()
    cur.close()

    return [r["vendor_name"] for r in rows]


###############VENDOR ACC>####################

@app.route("/vendor-accounts", methods=["GET"])
def vendor_accounts():
    if not login_required():
        return redirect(url_for("login"))

    cur = mysql.connection.cursor()

    # ================= OUTSTANDING VENDORS =================
    cur.execute("""
        SELECT 
            vendor_name,
            SUM(CASE WHEN payment_status='DUE' THEN total_amount ELSE 0 END) AS due_amount
        FROM purchases
        GROUP BY vendor_name
    """)
    vendors = cur.fetchall()

    selected_vendor = request.args.get("vendor")

    ledger = []
    total_debit = 0
    total_credit = 0
    running_balance = 0

    if selected_vendor:
        # ================= LEDGER DATA =================
        cur.execute("""
            SELECT 
                bill_date AS date,
                bill_no AS ref,
                total_amount AS debit,
                0 AS credit,
                payment_mode AS mode,
                payment_status
            FROM purchases
            WHERE vendor_name=%s

            UNION ALL

            SELECT
                payment_date AS date,
                CONCAT('PAY-', id) AS ref,
                0 AS debit,
                amount AS credit,
                payment_mode AS mode,
                'PAID' AS payment_status
            FROM vendor_payments
            WHERE vendor_name=%s

            ORDER BY date
        """, (selected_vendor, selected_vendor))

        rows = cur.fetchall()

        # ================= CALCULATIONS =================
        for r in rows:
            debit = float(r["debit"] or 0)
            credit = float(r["credit"] or 0)

            total_debit += debit
            total_credit += credit

            running_balance += debit
            running_balance -= credit

            ledger.append({
                "date": r["date"],
                "ref": r["ref"],
                "debit": debit,
                "credit": credit,
                "mode": r["mode"],
                "payment_status": r["payment_status"],
                "balance": running_balance
            })

    remaining_due = total_debit - total_credit

    cur.close()

    return render_template(
        "vendor_accounts.html",
        vendors=vendors,
        ledger=ledger,
        selected_vendor=selected_vendor,
        total_debit=total_debit,
        total_credit=total_credit,
        remaining_due=remaining_due
    )

@app.route("/pay-vendor", methods=["POST"])
def pay_vendor():
    if not login_required():
        return redirect(url_for("login"))

    vendor = request.form["vendor_name"]
    amount = float(request.form["amount"])
    mode = request.form["payment_mode"]

    cur = mysql.connection.cursor()

    # 1️⃣ Save vendor payment
    cur.execute("""
        INSERT INTO vendor_payments
        (vendor_name, amount, payment_mode, payment_status, payment_date)
        VALUES (%s,%s,%s,'PAID',CURDATE())
    """, (vendor, amount, mode))

    # 2️⃣ Clear vendor DUE purchases (FIFO – oldest first)
    cur.execute("""
        SELECT id, total_amount
        FROM purchases
        WHERE vendor_name = %s
          AND payment_status = 'DUE'
        ORDER BY bill_date
    """, (vendor,))
    dues = cur.fetchall()

    remaining = amount

    for d in dues:
        if remaining <= 0:
            break

        if remaining >= float(d["total_amount"]):
            # Fully paid
            cur.execute("""
                UPDATE purchases
                SET payment_status = 'PAID'
                WHERE id = %s
            """, (d["id"],))
            remaining -= float(d["total_amount"])
        else:
            # Partial payment (leave DUE)
            break

    mysql.connection.commit()
    cur.close()

    flash("✅ Vendor payment successful", "success")
    return redirect(url_for("vendor_accounts", vendor=vendor))

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
