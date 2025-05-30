import os
import requests
import subprocess
from xml.etree.ElementTree import Element, SubElement, ElementTree
from datetime import datetime

# ----------------------------------------
# 1) Ayarlar
# ----------------------------------------
ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
if not ACCESS_TOKEN:
    raise RuntimeError("❌ SHOPIFY_ACCESS_TOKEN ortam değişkeni tanımlı değil!")

STORE_NAME  = "fliqa-online"
API_VERSION = "2025-04"
BASE_URL    = f"https://{STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/"
HEADERS     = {
    "X-Shopify-Access-Token": ACCESS_TOKEN,
    "Content-Type": "application/json"
}

# ----------------------------------------
# 2) Ürünleri çek (options, images, variants ve vendor dahil)
# ----------------------------------------
def fetch_all_products():
    all_products = []
    since_id = 0

    while True:
        params = {
            "limit": 250,
            "since_id": since_id,
            "fields": "id,handle,product_type,title,body_html,options,images,variants,vendor"
        }
        try:
            resp = requests.get(BASE_URL + "products.json", headers=HEADERS, params=params)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            status = err.response.status_code if err.response else None
            if status == 401:
                print("🚫 Yetkisiz Erişim (401): ACCESS_TOKEN veya izinleri kontrol edin.")
            else:
                print(f"🚫 HTTP Hatası ({status}): {err}")
            break
        except requests.exceptions.RequestException as exc:
            print(f"🚫 İstek hatası: {exc}")
            break

        batch = resp.json().get("products", [])
        if not batch:
            break

        all_products.extend(batch)
        since_id = batch[-1]["id"]

    print(f"{len(all_products)} ürün çekildi.")
    return all_products

# ----------------------------------------
# 3) XML feed’i oluştur ("Default Title" varyantını atla)
#    – Ayrıca her seferinde değişecek bir generatedAt özniteliği ekliyoruz
# ----------------------------------------
def build_products_feed(products):
    root = Element(
        "products",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "generatedAt": datetime.now().isoformat()
        }
    )

    for p in products:
        handle       = p.get('handle', '')
        title        = p.get('title', '')
        description  = p.get('body_html', '')
        category     = p.get('product_type', '')
        brand        = p.get('vendor', '').strip()
        images       = p.get('images', [])
        variants     = p.get('variants', [])
        options_meta = p.get('options', [])

        for v in variants:
            price_v = float(v.get('price', 0) or 0)
            qty_v   = v.get('inventory_quantity', 0) or 0
            if price_v < 5 or qty_v <= 0:
                continue

            # Varyant etiketleri
            variant_labels = []
            for idx, opt in enumerate(options_meta):
                name = opt.get('name', '').strip()
                val  = v.get(f"option{idx+1}", '').strip()
                if name and val and val != 'Default Title':
                    variant_labels.append(val)

            prod = SubElement(root, "product")

            # <name>
            label_text = title
            if variant_labels:
                label_text += " - " + " / ".join(variant_labels)
            SubElement(prod, "name").text = label_text

            # SKU, URL
            SubElement(prod, "sku").text = v.get('sku', '')
            SubElement(prod, "url").text = f"https://fliqa.com.tr/products/{handle}?variant={v.get('id')}"

            # brand
            SubElement(prod, "brand").text = brand

            # Seçenekler
            for idx, opt in enumerate(options_meta):
                tag_name = opt.get('name', '').replace(' ', '')
                val = v.get(f"option{idx+1}", '').strip()
                if tag_name and val and val != 'Default Title':
                    SubElement(prod, tag_name).text = val

            # Görseller
            for idx_i, img in enumerate(images):
                tag = "imgUrl" if idx_i == 0 else f"imgUrl{idx_i}"
                SubElement(prod, tag).text = img.get('src', '')

            # Diğer alanlar
            SubElement(prod, "productCategory").text     = category
            SubElement(prod, "description").text         = description
            SubElement(prod, "price").text               = str(price_v)
            SubElement(prod, "quantity").text            = str(qty_v)
            SubElement(prod, "shipPrice").text           = "0"
            SubElement(prod, "distributor")
            SubElement(prod, "shipmentVolume").text      = "[price1kdvli]"
            SubElement(prod, "dayOfDelivery").text       = "0"
            SubElement(prod, "expressDeliveryTime").text = "13"

    return root

# ----------------------------------------
# 4) XML dosyaya yaz
# ----------------------------------------
def write_xml(element, filename="feed.xml"):
    ElementTree(element).write(filename, encoding="utf-8", xml_declaration=True)

# ----------------------------------------
# 5) GitHub push (sadece feed.xml)
# ----------------------------------------
def push_to_github(filename="feed.xml"):
    # 1) Sadece feed.xml'i stage et
    subprocess.run(["git", "add", filename], check=True)

    # 2) Staged değişiklik kalmış mı kontrol et
    diff = subprocess.run(["git", "diff", "--cached", "--exit-code"])
    if diff.returncode == 0:
        print("🔄 Yeni değişiklik yok; push atlandı.")
        return

    # 3) Commit → pull --rebase → push
    msg = f"Update feed at {datetime.now().isoformat()}"
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "pull", "--rebase"], check=True)
    subprocess.run(["git", "push"], check=True)

# ----------------------------------------
# 6) Çalıştır
# ----------------------------------------
if __name__ == "__main__":
    products = fetch_all_products()
    feed     = build_products_feed(products)
    write_xml(feed)
    push_to_github()
    print(f"Feed güncellendi: {len(feed.findall('product'))} ürün yazıldı.")
