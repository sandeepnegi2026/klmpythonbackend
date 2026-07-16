import re

from core.header_match import map_headers, normalize

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.parse_common import cell_text, compact, is_subtotal

# A "Customer :<name>" band row introduces a customer group in banded party-wise
# reports (the party is the band, not a column). Kept here (not imported from the
# layout) so detection stays dependency-light.
_CUSTOMER_BAND_RE = re.compile(r"^\s*(?:customer|party(?:\s+name)?)\s*[:\-]\s*\S", re.IGNORECASE)
_BANDED_PRODUCT_HDR = ("prodname", "productname", "product name")
_BANDED_VALUE_HDR = ("qty", "rate", "pvalue", "amount", "value")


def _has_bare_name_bands(rows, header_idx):
    """True for banded reports whose customer name sits in *bare* band rows.

    Some ERP exports (e.g. RUSHABH 'Particulars … Vch no', RAVINDRA 'Item Name …
    Bill No#') have no party column; the customer is a plain text row above each
    product group, recognisable because its invoice no/date (voucher) columns are
    blank while the product rows below carry them.

    Gated hard on "no party_name column was mapped" — a file that already maps a
    party column extracts fine via ``tabular`` and is never diverted, so currently
    passing files cannot regress. Requires at least one voucher column plus a real
    mix of band rows and product rows so plain product summaries are not claimed.
    """
    headers = [str(cell) for cell in rows[header_idx]]
    detected = {raw: info["canonical"] for raw, info in map_headers(headers, "party").items()}
    col = {}
    for idx, raw in enumerate(headers):
        key = detected.get(raw)
        if key and key not in col:
            col[key] = idx
    if "party_name" in col:
        return False
    if "product_name" not in col:
        # No product column to anchor line items on (e.g. a name-only column that maps
        # to vendor_name) -> not a banded party-product report; leave it to tabular.
        return False
    voucher_idx = [col[k] for k in ("invoice_number", "invoice_date") if k in col]
    if not voucher_idx:
        return False
    bands = prods = 0
    for row in rows[header_idx + 1 : header_idx + 400]:
        if not row:
            continue
        first = cell_text(row[0])
        voucher_empty = all(
            not (cell_text(row[i]) if i < len(row) else "") for i in voucher_idx
        )
        if first and voucher_empty and not is_subtotal(first):
            bands += 1
        elif not voucher_empty:
            prods += 1
    return bands >= 2 and prods >= 2


def _has_columnar_party_header(rows):
    """True for a flat per-row table with an explicit *Party Name* column (plus a
    product/item column and a value/qty/rate column).

    Such files carry the customer on every line, so ``tabular`` maps them correctly.
    They must NOT be diverted to the band-style ``marg_busy`` reader, which over-claims
    on the shared "party-itemwise" title and "description"+"qty" header tokens and then
    mis-parses the columns (party_name <- Cust code / "Party Total" subtotal, dates <-
    Value). Real marg_busy (Busy/Tally) exports carry the party in a *band* row and have
    no Party Name column, so they fail this test and are unaffected.
    """
    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is None:
        return False
    detected = {raw: info["canonical"]
                for raw, info in map_headers([str(c) for c in rows[header_idx]], "party").items()}
    keys = set(detected.values())
    return "party_name" in keys and "product_name" in keys and bool(keys & {"amount", "qty", "rate"})


def detect_layout(rows):
    # C-Square raw DB-field invoice dump (HERITAGE MARKTEERS / KLM per-division books). The
    # header row is the underlying view's literal column names and repeats 'c_name' four times
    # (item / pack / customer / firm), so text-keyed map_headers clobbers them and the customer
    # column is dropped -> RED. Parsed POSITIONALLY. Gated on the exact raw-field header run
    # (n_srno + d_inv_date + c_cust_code + >=3 c_name cells), which no other corpus file carries.
    # FIRST so no coarse tabular fallback grabs it.
    from extractors.party_xlsx.layouts.csquare_raw_invoice_dump import detect as _csquare_raw_detect
    if _csquare_raw_detect(rows):
        return "csquare_raw_invoice"
    # "Selected sale types, companies: product-wise, area-wise sale/DC summary" — KLM/Marg
    # (MediVision Platinum) product-wise / area-wise sale PIVOT (FLORA AGENCIES). One row per
    # product; the sale is spread across repeated `<AREA> qty` + `<AREA> amt` column PAIRS
    # (no customer column at all). The new layout unpivots those pairs into (product, area)
    # party rows. Gated on the unique compact title token so it can only ever claim this
    # exact report — proven to hit 1/183 party_xlsx samples (target only, zero theft). MUST
    # be the FIRST check so no coarse tabular/band fallback can grab it first.
    from extractors.party_xlsx.parse_common import compact as _compact_pawp
    if "productwiseareawisesaledcsummary" in _compact_pawp(
        " ".join(" ".join(cell_text(c) for c in r) for r in rows[:8])
    ):
        return "product_areawise_pivot"
    # "Areawise Partywise Sales Summary" — KLM/Marg Gujarat export whose sale qty/free
    # are encoded only in a "(qty+free)" sub-row below each product line (the visible
    # "May"/"Total" columns are rupee VALUE). Keyed on the exact compact title token, so
    # it claims only this report. MUST sit ABOVE the jaimini_partywise check below, which
    # otherwise steals it on the loose "partywise sale" substring and mis-reads the blank
    # qty column (every product becomes a fake party band).
    from extractors.party_xlsx.parse_common import compact as _compact_awps
    if "areawisepartywisesalessummary" in _compact_awps(
        " ".join(" ".join(cell_text(c) for c in r) for r in rows[:8])
    ):
        return "areawise_partywise_summary_xlsx"
    # MARG "Sales Analysis" party report (XLSX) — VENUS PHARMA "KLM MAY PARTY.XLSX".
    # 3-level banded: Manufacturer band (division, ignored) -> Customer band (party, emitted
    # into col3 of every product line) -> item lines (Item | Qty | Free | Value #). Title-gated
    # on the "Sales Analysis" + "Item Qty Free Value" + Manufacturer/Customer signature, so it
    # diverts only this specific export (currently falls to tabular and fails). Placed with the
    # other title-gated MARG/KLM Excel layouts, above every coarse band/qty fallback.
    from extractors.party_xlsx.layouts.marg_sales_analysis_xlsx import detect as _marg_sales_analysis_detect
    if _marg_sales_analysis_detect(rows):
        return "marg_sales_analysis_xlsx"
    # "Party/Product Wise Net Sales" — Marg ERP 9+ export (BADAL ENTERPRISE / KLM). The
    # party is a bare col0 band row (the three qty cells blank), then product rows carrying
    # Sale Qty / Ret Qty / Net Qty. The header maps only 2 canonical keys so detect_header_row
    # never fires and tabular/band readers ignore it. Gated hard on the distinctive title
    # fingerprint PLUS the four exact header cells, so it can never steal another vendor.
    from extractors.party_xlsx.layouts.party_product_net_sales_xlsx import detect as _party_product_net_sales_detect
    if _party_product_net_sales_detect(rows):
        return "party_product_net_sales_xlsx"
    # Itemwise Sales Details: product-banded report whose sale lines carry the customer
    # in a "Party Code & Name" column. Very specific (the Marg-style "Party Code" header
    # paired with "Qnty"/"Bill No"), so it is checked first and diverts no other layout.
    from extractors.party_xlsx.layouts.itemwise_party_column import detect as _itemwise_detect
    if _itemwise_detect(rows):
        return "itemwise_party_column"

    # "Area/Party/Billwise" multi-level code+name register (party is a band row whose
    # Name carries an address). Title-gated, so it diverts only this specific export.
    from extractors.party_xlsx.layouts.area_party_billwise import detect as _area_party_billwise_detect
    if _area_party_billwise_detect(rows):
        return "area_party_billwise"

    # "Detailed Company Wise Area Wise Sales Report" (CHAITANYA / KLM) — company + bare-name party
    # bands over a Bill No/Product/Qty/Free/Amount table. The party's text lands in col0 (the Bill
    # No column) so the bare-band heuristics see it as a product row and the file falls to tabular
    # (no party column -> RED). Title-gated ("area wise sales report"), so it diverts only this.
    from extractors.party_xlsx.layouts.company_area_wise_sales import detect as _company_area_detect
    if _company_area_detect(rows):
        return "company_area_wise_sales"

    # "Product-Customer Wise Sales" SwilERP Excel export (CAPITAL PHARMA / KLM) — DIVISION and
    # PRODUCT bands (single-cell rows) over customer rows (Customer|Station|Qty|Sales Value). The
    # product is a band, so tabular maps the four customer columns but leaves product_name empty
    # -> RED. Gated on the SwilERP title + the exact Customer/Station/Qty/Sales-Value header.
    from extractors.party_xlsx.layouts.product_customer_wise_sales_xlsx import detect as _prod_cust_ws_detect
    if _prod_cust_ws_detect(rows):
        return "product_customer_wise_sales_xlsx"

    # "Salesmen wise Report" (SAFE LIFE / KLM) — SwilERP export with a Manufacturer/Division band
    # + Area City/Product Name/PCode/Qty columns. Its GrsAmt + Area City header (no party column)
    # ALSO matches customer_product_banded_grsamt below, which mis-reads it positionally, so this
    # tightly title-gated ('salesmen wise') check MUST run first.
    from extractors.party_xlsx.layouts.salesmen_partywise import detect as _salesmen_detect_pre
    if _salesmen_detect_pre(rows):
        return "salesmen_partywise"

    # G.S. DISTRIBUTORS "<Division>-Sales Report" (KCOSMO/KDERMA/KPED/...) — customer is a
    # bare BAND row (header Product Name|Qty|Free|GrsAmt|Area City, NO party column). tabular
    # maps the product columns but never binds party_name -> RED. Gated on the banded GrsAmt +
    # Area City header WITHOUT a party_name column, so a columnar sibling with a real Customer
    # Name column (Kishore) stays on tabular.
    from extractors.party_xlsx.layouts.customer_product_banded_grsamt import detect as _cpb_grsamt_detect
    if _cpb_grsamt_detect(rows):
        return "customer_product_banded_grsamt"

    # NAVNEET "Customer + Product Wise Sale (Summary)" — same banded shape as the G.S.
    # reader but Area-FIRST columns (Area|Product Name|Qty|Free|GrsAmt, no 'Area City').
    from extractors.party_xlsx.layouts.customer_product_banded_area_first import detect as _cpb_area_first_detect
    if _cpb_area_first_detect(rows):
        return "customer_product_banded_area_first"

    # "Customer-wise, product-wise sale/DC summary" — MediVision Platinum Excel export
    # (BLUMAX / KLM). Two-level banded: the CUSTOMER is a band row (its division cell blank,
    # Qty/Amount = subtotals) over product lines carrying a non-blank division code. No party
    # column -> tabular maps Particulars->product_name and never attaches party_name (RED).
    # Title-gated on the distinct "customerwiseproductwisesaledcsummary" token, so it claims
    # only this report; placed with the other title-gated MediVision/KLM XLSX layouts.
    from extractors.party_xlsx.layouts.customer_product_sale_dc_summary import detect as _cust_prod_dc_detect
    if _cust_prod_dc_detect(rows):
        return "customer_product_sale_dc_summary"

    # KLM "Customer Item - Invoice Wise" party export (SANTOSH ENTERPRISES) — merged-cell
    # CUSTOMER bands (party+code+CITY written into every column) over a Date/Item Name/Qty/
    # Value table. customer_product_banded's merged-furniture guard eats the band and its
    # style-1 gate needs a 'Product Name' header. Title-gated on unique 'customeriteminvoicewise'.
    from extractors.party_xlsx.layouts.customer_item_invoicewise_banded import detect as _cii_banded_detect
    if _cii_banded_detect(rows):
        return "customer_item_invoicewise_banded"

    # "Item Wise - Customer Wise Sale" (SAI KRISHNA / KLM) — product is a col0 band row
    # ("Item :<name>  PACK :<pack>") over CUSTOMER detail rows. The Item/PACK band leaks into
    # every tabular field (fmt None). Title-gated on unique 'itemwisecustomerwisesale'.
    from extractors.party_xlsx.layouts.item_customerwise_sale import detect as _item_custws_detect
    if _item_custws_detect(rows):
        return "item_customerwise_sale"

    # "AreaCity Wise Sale Report" — Marg (SHREE UNITED / KLM) product-wise PIVOT whose total
    # qty is spread across generically-headed AC1..ACn per-area quantity columns (area names in
    # a bottom legend). Currently falls to tabular with no party column -> RED. Gated on unique
    # 'areacitywisesalereport' title token + the AC-grid header.
    from extractors.party_xlsx.layouts.areacity_wise_sale_pivot import detect as _areacity_pivot_detect
    if _areacity_pivot_detect(rows):
        return "areacity_wise_sale_pivot"

    # "PARTY DISCOUNT SUMMARY ON SALES" — Busy/Marg single-column TEXT export (SAM MEDICOS /
    # KLM). Party is a bare name band; each product line carries 8 trailing discount numbers.
    # marg_busy reads 0 rows from the single text cell. Title-gated on 'partydiscountsummary'.
    from extractors.party_xlsx.layouts.party_discount_summary_xlsx import detect as _party_disc_summary_detect
    if _party_disc_summary_detect(rows):
        return "party_discount_summary_xlsx"

    # Marg "Outward Detail(s)" party-wise sale export (SATARA PHARMA / KLM). Columnar table that
    # tabular maps correctly but leaves footer noise rows + blank product on continuation rows.
    # Title-gated on the unique 'outwarddetail' token + a columnar party/product/qty header.
    from extractors.party_xlsx.layouts.marg_outward_detail_partywise import detect as _marg_outward_detail_detect
    if _marg_outward_detail_detect(rows):
        return "marg_outward_detail_partywise"

    # Wide "Companywise Customerwise" Logic-ERP export (customer band, far-apart cols).
    from extractors.party_xlsx.layouts.companywise_customerwise import detect as _companywise_detect
    if _companywise_detect(rows):
        return "companywise_customerwise"

    # "Salesmen wise Report" — customer band + division/area/product columns.
    from extractors.party_xlsx.layouts.salesmen_partywise import detect as _salesmen_detect
    if _salesmen_detect(rows):
        return "salesmen_partywise"

    # "Manufacturer Wise Item Wise (Secondary Sales)" XLSX (SHRI JAYANTHI PHARMA / KLM) — banded
    # by manufacturer, fixed-header-index mapped (single-letter Q/F/R headers don't map via the
    # shared synonym set). Title token 'manufacturerwiseitemwise' + the invno/batch/rate/val/sman
    # header set is unique; placed above area_item_sales_summary and the marg_busy/tabular fallbacks.
    from extractors.party_xlsx.layouts.manufacturer_itemwise_secondary_xlsx import detect as _mfr_itemwise_secondary_detect
    if _mfr_itemwise_secondary_detect(rows):
        return "manufacturer_itemwise_secondary_xlsx"
    # "AREA / ITEM WISE SALES SUMMARY" — the XLS twin of the party_pdf layout of the same
    # name (AGARTALA / KLM). Space-padded text, one line per cell, party bands prefixed
    # with '-'. Title-gated ("area item wise sales summary" + the four-column
    # DESCRIPTION QTY FREE RATE AMOUNT header, no "%" discount column), so it claims only
    # this report; otherwise it falls to marg_busy, which cannot read the text cell (0 rows).
    from extractors.party_xlsx.layouts.area_item_sales_summary import detect as _area_item_sales_detect
    if _area_item_sales_detect(rows):
        return "area_item_sales_summary"

    # "ITEM / ITEM WISE SALES SUMMARY" — MARG ERP 9+ product-wise export (SRI SRINIVASA / KLM).
    # Same DESCRIPTION QTY FREE RATE AMOUNT header as the AREA layout above, but the band is the
    # PRODUCT and the customers are COLUMNAR party lines beneath it. Title-gated on the distinct
    # "item item wise sales summary" token (mutually exclusive with the AREA / PARTY variants),
    # so it claims only this report; otherwise it falls to marg_busy, which inverts party/product.
    from extractors.party_xlsx.layouts.item_item_sales_summary import detect as _item_item_sales_detect
    if _item_item_sales_detect(rows):
        return "item_item_sales_summary"

    # "Customer Vs Groups Report" — KLM / KRISHNA MEDICAL single-column TEXT export flattened
    # into col0 with many shredded sale lines. Emits recoverable clean detail rows PLUS a
    # per-item rollup remainder so division value totals reconcile. Title + compact header gated,
    # unique to this export; placed above the coarse marg_busy/tabular fallthroughs.
    from extractors.party_xlsx.layouts.klm_customer_vs_groups_text import detect as _klm_cvg_text_detect
    if _klm_cvg_text_detect(rows):
        return "klm_customer_vs_groups_text"
    # Same "ITEM / ITEM WISE SALES SUMMARY" report but the single-column (fixed-width TEXT) variant
    # (M/S BURIMAA / KLM): every row is one space-padded cell (ncols==1) and it carries an extra
    # "AMOUNT ( % )" column. Gated single-column — the whole DESCRIPTION..AMOUNT header lives in
    # col0 alone (the columnar sibling above spreads it across real cells and carries no "%"), so
    # the two never collide; otherwise it falls to marg_busy, which reads 0 rows from the glued cell.
    from extractors.party_xlsx.layouts.item_item_sales_summary_text import detect as _item_item_text_detect
    if _item_item_text_detect(rows):
        return "item_item_sales_summary_text"

    # "Customer & Product Analysis" — single-column (fixed-width TEXT) banded party report
    # (SRI POORNA / KLM). The whole Inv.No..Value header + "Customer :" bands live in col0
    # alone (ncols==1), so the columnar customer_product_banded style-1 gate never fires.
    # Gated single-column on the header run + title + a "Customer :" band; placed here so it
    # beats party_item_summary/marg_busy and the style-1 customer_product_banded/tabular fallbacks.
    from extractors.party_xlsx.layouts.customer_product_banded_text import detect as _cpb_text_detect
    if _cpb_text_detect(rows):
        return "customer_product_banded_text"
    # "PARTY / ITEM WISE SALES SUMMARY" — Busy text export, party band + space-padded
    # product lines in a single (or merged) column. Checked before marg_busy, which
    # would otherwise claim it on the shared "description"+"qty" signal but cannot read
    # the figures out of the text cell.
    from extractors.party_xlsx.layouts.party_item_summary import detect as _party_item_summary_detect
    if _party_item_summary_detect(rows):
        return "party_item_summary"

    # "Item VS Parties Wise Sale Scheme Register" — product-banded party register (indent lost
    # by the xlsx loader). Separates bands from party rows by the invariant band.Amount ==
    # sum of the following party rows' Amounts. Bands are subtotals (not emitted). Title tokens
    # 'itemvsparties' unique; placed just above the product_party_banded block.
    from extractors.party_xlsx.layouts.item_vs_parties_scheme_register import detect as _item_vs_parties_detect
    if _item_vs_parties_detect(rows):
        return "item_vs_parties_scheme_register"
    # "Product + Party Wise List Report" — Product|Free|SaleQty.|ReturnQty|Amount columns
    # with the party as a name-only band row (numbers blank) and 'Party Total:' subtotals.
    # Header-gated on the distinctive raw tokens plus the band structure, so it cannot
    # steal a plain columnar file.
    from extractors.party_xlsx.layouts.product_party_banded import detect as _product_party_banded_detect
    if _product_party_banded_detect(rows):
        return "product_party_banded"

    # "Customer + Product Wise Sale (Detail)" — KLM multi-division export whose product
    # columns map cleanly (Inv No/Product Name/Qty/Rate/Area/GrsAmt) but whose party is a
    # column-0 band "<division-code> -:- <party>" (division-first, the REVERSE of the
    # JALARAM partywise_band). Checked before partywise_band, which claims this file on its
    # "customer product wise" title but reads the band the wrong way (-> empty party_name).
    from extractors.party_xlsx.layouts.customer_product_wise_band import detect as _cpw_band_detect
    if _cpw_band_detect(rows):
        return "customer_product_wise_band"

    # "Company/Area/Customer/Product Wise Sales" — Logic-ERP export (SHRI SAI / KLM) whose party
    # is a lone column-0 band "CUSTOMER NAME : NAME-AREA-CITY" over a PRODUCT C/PRODUCT NAME/QTY/
    # FREE QT/GOODS VALU/PRATE table. Also claimed by partywise_band on the shared "customer
    # product wise" title, but its band lives in col 0 (not the Name/product column) and its
    # "CUSTOMER NAME :" prefix isn't matched -> empty party_name. Checked before partywise_band;
    # gated on title + the PRODUCT-NAME/QTY/PRATE header + a CUSTOMER NAME band.
    from extractors.party_xlsx.layouts.company_area_customer_product_wise import detect as _cacpw_detect
    if _cacpw_detect(rows):
        return "company_area_customer_product_wise"

    # "Customer / Company / Itemwise Sales" — MARG/KLM export (MANISH) banded
    # Location->Series->Customer->Company. Title-gated so it diverts only this specific
    # report, which otherwise falls to ``customer_product_banded`` and mis-reads the
    # trailing company band ("KLM LABORA - <DIV>") as party_name.
    # DHRUVI "COMPANY - CUSTOMER - ITEM WISE SALE" — banded Division/PINCODE/CUSTOMER where
    # the tabular last-non-empty carry-down wrongly grabs the 6-digit PINCODE band as the
    # party. Gated on the misspelled "Barcoode" banded header + the title, so it claims only
    # this banded export (flat-columnar twins of the same title stay on tabular).
    from extractors.party_xlsx.layouts.company_customer_itemwise_banded import detect as _ccib_detect
    if _ccib_detect(rows):
        return "company_customer_itemwise_banded"

    # YOGIRAM "COMPANY-CUSTOMER-ITEM WISE SALE" PONDY export — the NO-"Barcoode" sibling of
    # company_customer_itemwise_banded. Party sits in a col0 "[ <code> ] <NAME>" band (Area in
    # col2); item lines carry a numeric raw item code in col0. Gated on the title + exact
    # "Party Name | Item Name | Area" header run WITHOUT "Barcoode" + a "[ <code> ] <NAME>"
    # band, so it claims only this export (its 'Barcoode' twin stays on the banded sibling above).
    from extractors.party_xlsx.layouts.company_customer_itemwise_area import detect as _cciw_area_detect
    if _cciw_area_detect(rows):
        return "company_customer_itemwise_area"

    # UNITED "Customer & Items New" — "Customer Name: <name> Area: <town>" glued in one col0
    # band cell (the shared CUSTOMER_BAND_RE rejects "Customer Name:", and the band sits in
    # the Inv-No voucher column so the bare-band fallback never fires). Title-gated.
    from extractors.party_xlsx.layouts.customer_items_new_xlsx import detect as _cin_detect
    if _cin_detect(rows):
        return "customer_items_new_xlsx"

    from extractors.party_xlsx.layouts.customer_company_itemwise import detect as _cci_detect
    if _cci_detect(rows):
        return "customer_company_itemwise"

    # KLM "Company Party Wise Product Sale" (GARG DISTRIBUTOR) — 3-level banded:
    # "KLM <DIV>" company bands + bare party bands over a single COMPANY / PARTY /
    # PRODUCT column, so tabular can never bind party_name. Title + the exact
    # RPL / NET AMT header cells gate it to this export alone.
    from extractors.party_xlsx.layouts.company_party_product_xlsx import detect as _cpp_detect
    if _cpp_detect(rows):
        return "company_party_product_xlsx"

    # "PARTY+ITEM WISE SALE" columnar export (KAPOOR / Marg) — a flat table with a real
    # PARTY NAME column whose town is glued as a trailing "-<AREA>" suffix. Reuses tabular's
    # exact column mapping and only peels the area into party_location. Title-gated + requires
    # a columnar party header, so it claims only this family; other files stay on tabular.
    from extractors.party_xlsx.layouts.party_item_wise_sale import detect as _piws_detect
    if _piws_detect(rows):
        return "party_item_wise_sale"

    # --- 15July KLM party_xlsx layouts. Each currently falls through EVERY specific
    #     check above to the generic tabular/marg_busy fallback and lands RED (no
    #     party_name). Placed here — after all specific detectors, before the coarse
    #     fallbacks — so none of them can preempt an existing layout; each detect() is
    #     tightly title/header-gated to its own export (verified corpus-unique). ---
    from extractors.party_xlsx.layouts.areawise_sales_statement import detect as _awss_xlsx_detect
    if _awss_xlsx_detect(rows):
        return "areawise_sales_statement"
    from extractors.party_xlsx.layouts.bhaskara_code_customer_banded import detect as _bhaskara_detect
    if _bhaskara_detect(rows):
        return "bhaskara_code_customer_banded"
    from extractors.party_xlsx.layouts.klm_order_form_xlsx import detect as _klm_order_detect
    if _klm_order_detect(rows):
        return "klm_order_form_xlsx"
    from extractors.party_xlsx.layouts.klm_warehouse_pincode_sale_dump import detect as _klm_warehouse_detect
    if _klm_warehouse_detect(rows):
        return "klm_warehouse_pincode_sale_dump"
    from extractors.party_xlsx.layouts.retailer_band_cgst_sgst import detect as _retailer_band_detect
    if _retailer_band_detect(rows):
        return "retailer_band_cgst_sgst"
    # DEEPALI "Outward Detail(s)" firm-level sale (NO customer column) — sibling of
    # marg_outward_detail_partywise above, which needs a party column this file lacks;
    # placed after it so that sibling is never diverted.
    from extractors.party_xlsx.layouts.outward_detail_firm_partywise import detect as _outward_firm_detect
    if _outward_firm_detect(rows):
        return "outward_detail_firm_partywise"

    compact_text = compact(" ".join(" ".join(row) for row in rows[:150]))
    if (
        "partywiseoutward" in compact_text
        or "partywise outward" in " ".join(" ".join(r) for r in rows[:8]).lower()
    ):
        return "fawin_partywise"
    if "listofsalebyitem" in compact_text:
        return "data_spec_sale_by_item"
    if (
        "partywise sale" in " ".join(" ".join(r) for r in rows[:8]).lower()
        and "product name" in " ".join(" ".join(r) for r in rows[:8]).lower()
    ):
        return "jaimini_partywise"
    if (
        "party+productwise" in compact_text
        or "party + product wise" in " ".join(" ".join(r) for r in rows[:8]).lower()
    ):
        return "painkiller_partywise"
    for row in rows[:150]:
        header_cells = [normalize(c) for c in row if cell_text(c)]
        if "party" in header_cells and "product" in header_cells:
            return "tabular_party_product"
        # Flat per-row table with PRODUCT + NAME(customer) + CITY columns (SALEAPX-style),
        # where the bare NAME column otherwise mis-maps to vendor_name not party_name.
        if (
            "product" in header_cells
            and "name" in header_cells
            and "city" in header_cells
        ):
            return "product_name_city"
        header_text = normalize(" ".join(row))
        if "itemname" in header_text and ("billno" in header_text or "bill" in header_text):
            return "infosoft_bandwise"
        if "itemname" in header_text and "srno" in header_text:
            return "infosoft_bandwise"
    compact_text = compact(" ".join(" ".join(row) for row in rows[:150]))
    # A columnar table that already exposes a Party Name column (e.g. Marg
    # "Party-Itemwise-Billwise Sale": Cust|Party Name|Area|Bill No|Date|...|Value) belongs
    # to ``tabular``; only band-style Busy/Tally exports (no party column) go to marg_busy.
    columnar_party = _has_columnar_party_header(rows)
    if "partyitemwise" in compact_text and not columnar_party:
        return "marg_busy"
    if "description" in compact_text and "qty" in compact_text and not columnar_party:
        return "marg_busy"
    if "salesdetailregister" in compact_text or (
        "sales detail register" in " ".join(" ".join(r) for r in rows[:8]).lower()
    ):
        return "marg_register_excel"
    # Banded customer report (style 1): a "Customer :<name>" band + a ProdName/value
    # header row. Specific (needs BOTH), placed just above the generic tabular
    # fallback so it only claims files that would otherwise mis-extract as tabular.
    if any(_CUSTOMER_BAND_RE.match(cell_text(row[0]) if row else "") for row in rows[:200]):
        for hrow in rows[:150]:
            cells = [normalize(c) for c in hrow if cell_text(c)]
            if any(c in cells for c in _BANDED_PRODUCT_HDR) and any(
                c in cells for c in _BANDED_VALUE_HDR
            ):
                return "customer_product_banded"
    from extractors.party_xlsx.layouts.partywise_band import detect as _partywise_band_detect

    header_idx = detect_header_row(rows, min_matches=4)
    if header_idx is not None:
        # Banded customer report (style 2): no party column, but the customer name
        # sits in bare band rows (invoice no/date blank) above each product group.
        if _has_bare_name_bands(rows, header_idx):
            return "customer_product_banded"
        # Party-as-band exports whose columns differ from the banded family above
        # (Name+Product two-column, bands in the product column, etc.).
        if _partywise_band_detect(rows):
            return "partywise_band"
        return "tabular"
    if _partywise_band_detect(rows):
        return "partywise_band"
    return "unknown"
