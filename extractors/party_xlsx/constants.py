import re

SUBTOTAL_RE = re.compile(r"^\s*(total|sub.?total|grand total|party\s*total|customer\s*total|cus\.?\s*total|net amount|print health qrcode|marg erp|opening value|closing value|sales value|report date|sales$|mg\d+)\b", re.I)
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
    r"^\s*(grand\s*total|sub\s*-?\s*total|total|net\s+amount|opening\s+value|closing\s+value|sales\s+value)\s*[:\-]?\s*[\d.,]*$",
    re.IGNORECASE,
)

LAYOUT_LABELS = {
    "customer_items_new_xlsx": "Customer & Items New (banded, Area-glued)",
    "company_customer_itemwise_banded": "Company - Customer - Item Wise Sale (banded)",
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
