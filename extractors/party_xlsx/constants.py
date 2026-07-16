import re

SUBTOTAL_RE = re.compile(r"^\s*(total|sub.?total|grand total|party\s*total|customer\s*total|company\s*total|cus\.?\s*total|net amount|print health qrcode|marg erp|opening value|closing value|sales value|report date|sales$|mg\d+)\b", re.I)
PARTY_BAND_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s&.,()\-/'\"]+$")
SKIP_ROW_RE = re.compile(r"^(\+|\-|\.|->\d+)$", re.I)
# A band/section header that introduces a customer group, e.g. "Customer :AISHWARI"
# or "Party Name : RATAN PHARMACY" / "Party : ...". The colon/dash after the keyword
# keeps it from matching a "Party Total" / "Party" header row.
CUSTOMER_BAND_RE = re.compile(r"^\s*(?:customer|party(?:\s+name)?)\s*[:\-]\s*(.+)$", re.IGNORECASE)
# An address line carried on a customer band row, e.g. "Add :MIRYALAGUDA".
ADDR_BAND_RE = re.compile(r"^\s*add(?:ress)?\s*[:\-]\s*(.+)$", re.IGNORECASE)
# A *pure* subtotal/footer label sitting in a band column, e.g. "Total", "Grand Total :",
# "Total : 5586.29". Deliberately stricter than SUBTOTAL_RE so a customer whose name merely
# starts with a total-ish word (e.g. "TOTAL CARE PHARMA", "SALES INDIA") is NOT dropped.
BARE_TOTAL_RE = re.compile(
    r"^\s*(customer\s+sub\s*-?\s*total|area\s*total|grand\s*total|sub\s*-?\s*total|total|net\s+amount|opening\s+value|closing\s+value|sales\s+value)\s*[:\-]?\s*[\d.,]*$",
    re.IGNORECASE,
)

LAYOUT_LABELS = {
    "areawise_sales_statement": "Areawise Sales Statement — BlueFox bill-wise, AREA/PARTY column-index bands (TELY DRUGS / KLM)",
    "bhaskara_code_customer_banded": "Customer & Product — Code:/Customer: banded, qty-only (BHASKARA / KLM)",
    "klm_order_form_xlsx": "KLM Product Order Form — ordered-lines only, qty-only (PHARMA ASIA / KLM)",
    "klm_warehouse_pincode_sale_dump": "KLM Warehouse/Pincode raw sale dump — positional DB fields (ARYAN WELLNESS / KLM)",
    "retailer_band_cgst_sgst": "KLM LAB per-division sale — Retailer: banded, Name=product, CGSTRs/SGSTRs (THANE / KLM)",
    "outward_detail_firm_partywise": "Marg Outward Detail(s) — firm-level (no customer column; party=firm) (DEEPALI / KLM)",
    "customer_item_invoicewise_banded": "Customer Item - Invoice Wise — banded (party in merged CUSTOMER:...CITY band rows; Item Name/Qty/Value; KLM)",
    "item_customerwise_sale": "Item Wise - Customer Wise Sale (Item-Banded, Customer detail)",
    "areacity_wise_sale_pivot": "AreaCity Wise Sale Report (Pivot unpivot, AC-grid + legend)",
    "party_discount_summary_xlsx": "Party Discount Summary on Sales (Text)",
    "marg_outward_detail_partywise": "Marg Outward Detail Partywise Sale",
    "customer_product_banded_grsamt": "Customer/Product-wise Sale Report — banded (Product/Qty/Free/GrsAmt/Area City; party in band rows) — G.S. DISTRIBUTORS",
    "customer_product_banded_area_first": "Customer + Product Wise Sale Summary — banded, Area-first (Area/Product/Qty/Free/GrsAmt; party in band rows) — NAVNEET",
    "swil_html_billwise": "SwilERP Party Billwise (HTML-in-.xls)",
    "customer_product_sale_dc_summary": "Customer-wise Product-wise Sale/DC Summary (MediVision, Banded XLSX)",
    "klm_customer_vs_groups_text": "KRISHNA MEDICAL — Customer Vs Groups Report (KLM, single-column text)",
    "item_vs_parties_scheme_register": "Item VS Parties Wise Sale Scheme Register (Product-Banded)",
    "customer_product_banded_text": "Customer & Product Analysis (Customer-Banded, Text)",
    "manufacturer_itemwise_secondary_xlsx": "Shri Jayanthi Pharma — Manufacturer Wise Item Wise (Secondary Sales) XLSX (banded, index-mapped)",
    "customer_items_new_xlsx": "Customer & Items New (banded, Area-glued)",
    "company_customer_itemwise_banded": "Company - Customer - Item Wise Sale (banded)",
    "company_customer_itemwise_area": "Company - Customer - Item Wise Sale (banded, Area; PONDY / no Barcoode)",
    "csquare_raw_invoice": "C-Square Raw DB-Field Invoice Dump (positional; n_srno/d_inv_date/repeated c_name; HERITAGE MARKTEERS)",
    "product_areawise_pivot": "Product-wise Area-wise Sale/DC Summary (Pivot Unpivot)",
    "areawise_partywise_summary_xlsx": "Areawise Partywise Sales Summary (Paren Qty/Free)",
    "marg_sales_analysis_xlsx": "MARG Sales Analysis (Party, XLSX)",
    "party_product_net_sales_xlsx": "\"party_product_net_sales_xlsx\": \"Party/Product Wise Net Sales (Marg Band)\",",
    "tabular_party_product": "EasyAC / Tabular Party-Product",
    "marg_busy": "Busy/Tally Party-Itemwise",
    "marg_register_excel": "Marg ERP Sales Register",
    "infosoft_bandwise": "Visual Infosoft Bandwise",
    "jaimini_partywise": "Jaimini Partywise Sale",
    "painkiller_partywise": "Painkiller Party+Product",
    "data_spec_sale_by_item": "Data Spec Sale-by-Item",
    "fawin_partywise": "Fawin Partywise Outward",
    "itemwise_party_column": "Itemwise Sales (Party-as-Column)",
    "customer_product_banded": "Customer-Banded Party-Product",
    "partywise_band": "Party-Band (Areawise/Customerwise)",
    "area_party_billwise": "Area/Party/Billwise Register",
    "company_area_wise_sales": "Company Wise Area Wise Sales (Bill-wise, Banded)",
    "product_customer_wise_sales_xlsx": "Product-Customer Wise Sales (SwilERP, Banded XLSX)",
    "company_area_customer_product_wise": "Company/Area/Customer/Product Wise Sales (Col-0 Band)",
    "companywise_customerwise": "Companywise Customerwise (Wide)",
    "salesmen_partywise": "Salesmen-wise (Customer-Banded)",
    "party_item_summary": "Party/Item-wise Sales Summary (Text)",
    "product_name_city": "Product/Name/City Columnar",
    "product_party_banded": "Product+Party Wise (Band)",
    "customer_product_wise_band": "Customer+Product Wise Sale (Band)",
    "customer_company_itemwise": "Customer/Company Itemwise Sales",
    "company_party_product_xlsx": "Company Party Wise Product Sale (KLM bands)",
    "party_item_wise_sale": "Party+Item Wise Sale (Columnar, Hyphen Area)",
    "area_item_sales_summary": "Area/Item Wise Sales Summary (Text)",
    "item_item_sales_summary": "Item/Item Wise Sales Summary (Product-Banded, Columnar)",
    "item_item_sales_summary_text": "Item/Item Wise Sales Summary (Product-Banded, Text)",
    "tabular": "Generic Tabular",
    "unknown": "Unknown",
}
