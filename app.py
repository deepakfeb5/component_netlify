from flask import Flask, render_template, request, send_file
import csv
import io
from mouser_client import MouserClient
import os

app = Flask(__name__)


MOUSER_API_KEY = os.getenv("MOUSER_API_KEY", "")
mouser = MouserClient(MOUSER_API_KEY)

@app.route("/", methods=["GET", "POST"])
def index():
    
    bom_data = []
    total_bom_cost = 0

    if request.method == "POST":
        file = request.files.get("csv_file")

        if file and file.filename.endswith(".csv"):

            # ✅ Safe UTF‑8 decode (prevents ±, Ω errors)
            raw_bytes = file.read()
            decoded_text = raw_bytes.decode("utf-8", errors="ignore")

            stream = io.StringIO(decoded_text)
            csv_reader = csv.DictReader(stream)

            for row in csv_reader:
                mpn = row.get("PartNumber", "").strip()
                qty = int(row.get("Quantity", 0))

                # ✅ Call Mouser API (or cached)
                main_data, alternates, error = mouser.search_part(mpn)

                if main_data:
                    price = main_data["price"] or "0"
                    try:
                        unit_price = float(price.replace("$", "").strip())
                    except:
                        unit_price = 0.0
                else:
                    unit_price = 0.0

                total_price = round(unit_price * qty, 2)
                total_bom_cost += total_price

                bom_data.append({
                    "PartNumber": mpn,
                    "Quantity": qty,
                    "Manufacturer": (main_data or {}).get("manufacturer", "None"),
                    "Lifecycle": (main_data or {}).get("lifecycle", "None"),
                    "StockInfo": (main_data or {}).get("stock", "None"),
                    "UnitPrice": unit_price,
                    "TotalPrice": total_price,
                    "Alternates": ", ".join(alternates) if alternates else "None",
                    "Error": error or "None"
                })

        return render_template("index.html",
                               bom=bom_data,
                               total_cost=total_bom_cost)

    return render_template("index.html", bom=None, total_cost=None)


@app.route("/download_results_csv", methods=["POST"])
def download_results_csv():
    bom_data = request.get_json().get("bom", [])

    proxy = io.StringIO()
    writer = csv.writer(proxy)
    writer.writerow([
        "Part Number", "Quantity", "Manufacturer", "Lifecycle",
        "Stock Info", "Unit Price", "Total Price", "Alternates", "Error"
    ])

    for item in bom_data:
        writer.writerow([
            item["PartNumber"],
            item["Quantity"],
            item["Manufacturer"],
            item["Lifecycle"],
            item["StockInfo"],
            item["UnitPrice"],
            item["TotalPrice"],
            item["Alternates"],
            item["Error"]
        ])

    mem = io.BytesIO(proxy.getvalue().encode("utf-8"))
    mem.seek(0)

    return send_file(
        mem,
        as_attachment=True,
        download_name="BOM_Results.csv",
        mimetype="text/csv"
    )


if __name__ == "__main__":
    app.run(debug=True)
