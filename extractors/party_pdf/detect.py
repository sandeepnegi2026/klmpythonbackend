import re


def detect_format(text, n_rects, n_lines):
    t = text[:2000]
    tl = t.lower()
    tl_compact = re.sub(r"\s+", "", tl)
    # SIND DISTRIBUTORS "MediVision Platinum" customer-wise/product-wise sale-DC.
    # Adobe-UTF-8 CID font — pdfminer yields nothing; pdf_io falls back to PyMuPDF
    # and this positional parser reads word x-coords via fitz. Title signature is
    # unique across all New_Data PDFs (zero collisions).
    if "customer-wise,product-wisesale/dcdetails" in tl_compact:
        return "medivision_sale_dc"
    if "freequantitystatement" in tl_compact:
        return "technomax_free_qty"
    if "customer & product analysis" in tl:
        return "profitmaker"
    if "partynameitemnamequantityfreeamount" in tl_compact:
        return "sale_register_consolidated"
    # AGARTALA PHARMA "AREA / ITEM WISE SALES SUMMARY": party bands prefixed with '-', header
    # DESCRIPTION QTY. FREE RATE AMOUNT. The 5S PHARMA area_item_summary variant carries an
    # extra '( % )' discount column, so the paren-guard keeps those on area_item_summary below.
    if (
        "area/itemwisesalessummary" in tl_compact
        and "descriptionqty.freerateamount" in tl_compact
        and "descriptionqty.freerateamount(" not in tl_compact
    ):
        return "area_item_sales_summary"
    if "d e s c r i p t i o n" in tl and re.search(r"area\s*/\s*item\s*wise", tl):
        return "area_item_summary"
    if "sales detail register" in tl and (
        "itemwise-customerwise" in tl or "mf-itemwise" in tl
    ):
        return "marg_register_itemwise"
    if "sales detail summary" in tl and (
        "mf-customer" in tl or "mf - customer" in tl
    ):
        return "marg_summary"
    if "sales detail register" in tl and "mf-customer" in tl:
        return "marg_register"
    if "sale details" in tl and n_lines > 5:
        return "marg_sale_details"
    if n_rects > 50 and re.search(r"from:\s*\d{2}/\d{2}", tl):
        return "marg_bordered_billwise" if "bill no" in tl else "marg_bordered"
    if "customer-wise product-wise" in tl and "----" in t:
        return "unisolve"
    if "item / item wise" in tl or "item/item wise" in tl:
        return "busy_tally_itemwise"
    # YUVEE 3-band "PARTY / ITEM WISE SALES SUMMARY" (SALE / SALES RETURN / TOTAL with an
    # AVR.RATE column, 12 numbers per row) — busy_tally's per-line 5/6-number patterns reject
    # its rows (0 extracted). The AVR.RATE column exists ONLY in this summary; corpus-wide the
    # 282 busy_tally files carry the same title but none carry 'avr.rate'. MUST precede busy_tally.
    if "party/itemwisesalessummary" in tl_compact and "avr.rate" in tl_compact:
        return "party_item_summary_sr_total"
    if "party / item wise" in tl or "party/item" in tl:
        return "busy_tally"
    if (
        "customer / company / itemwise" in tl
        and "codeitemnamepackingbatchno.qty.fqty" in tl_compact
    ):
        # Series-banded variant (no Sr column, integer qty, dd/mm/yyyy dates,
        # VC/AC##### invoices). The Sr.-column variant still routes to logic_erp.
        return "customer_itemwise_series"
    if "customer / company / itemwise" in tl:
        return "logic_erp"
    if "product c" in tl and "====" in t:
        return "wep_legacy"
    if n_rects > 5 and re.search(r"from:\s*\d{2}/\d{2}", tl):
        return "marg_bordered"
    if (
        re.search(r"free\s+quantity", tl)
        and "billref" in tl_compact
        and "statement" not in tl_compact
    ):
        return "prompt_free_qty"
    if re.search(r"(normal|party)\s+from:", tl) and (
        "billref" in tl_compact or "bill ref" in tl
    ):
        return "prompt_normal"
    # --- New KLM party layouts (placed last so existing rules always win; these
    #     only catch files that otherwise fall through to "unknown"). Header
    #     signatures are matched over the FULL text since a column header can sit
    #     below the first 2000 chars on long reports. Each signal is verified to
    #     match only its own files (no already-working file is rerouted).
    tfull = text.lower()
    cfull = re.sub(r"\s+", "", tfull)
    if "manufacturerwise sales report" in tfull and "billdatebillnoproductname" in cfull:
        return "manufacturerwise_billwise"
    if "customerwise-productwise" in cfull and "lifecareformulations" in cfull:
        return "customerwise_productwise"
    if (
        "productnamepackingbillnobl.dateqtyf.qtyrateamount" in cfull
        or "billno.billproductnamepackingbatchqtyfreeratevalue" in cfull
        or "datetrn.no.codeitemnameqty.freeratevalue" in cfull
        or "namepackbillrefdatemrpbatchqtyfreerateamount" in cfull
    ):
        return "billwise_multiheader"
    if (
        ("productpartyanalysis" in cfull and "codepartynameareaqtyfreeamount" in cfull)
        or ("company-customer-itemwisesale" in cfull)
        or ("customer-itemwisesale" in cfull and "itemnamepackqty" in cfull)
        or ("customer-productwisesales" in cfull and "productcodeproductnamepacking" in cfull)
    ):
        return "customer_product_grouped"
    if "company/partywisesalessummary" in cfull and "sno.descriptionsalesreturnamount" in cfull:
        return "company_party_summary"
    if (
        ("srno|entryno" in cfull and "accountname" in cfull)
        or ("product|hsn|pkg" in cfull and "|amount|" in cfull)
    ):
        return "pipe_delimited"
    if (
        "d e s c r i p t i o n" in tfull
        and "party/itemwisesalessummary" in cfull
        and "descriptionqty.rateamount" in cfull
        and "areaitemwise" not in cfull
    ):
        return "party_item_summary_nofree"
    # --- Tail layouts from the second workflow sweep (each verified to match only
    #     its own currently-"unknown" file; placed last so existing rules win). ---
    if "companywisecustomerwisereport" in cfull:
        return "companywise_customerwise"
    if "partydiscountsummaryonsales" in cfull:
        return "party_discount_summary"
    if "product-wisecustomer-wisefreeissue" in cfull:
        return "saraswati_freeissue"
    if "mfac group wise report" in tfull:
        return "laxmi_mfac"
    if "billnodateproductnam" in cfull and "qty.fr.sch.qty" in cfull:
        return "shree_nath_billwise"
    if "itemwise sales details" in tfull and "party code & name" in tfull:
        return "rp_pharma_itemwise"
    if "companywiseareawisesalesdetail" in cfull:
        return "companywise_areawise"
    if "datebillnoproducthsnpack" in cfull:
        return "navkar_productwise"
    if "salesstatement" in cfull and "partynameamountdiscountnetamt" in cfull:
        return "bajaj_salestatement"
    if "billdatepartynameitemnametotalpacks" in cfull:
        return "bharat_saleregister"
    if "tobuyername" in cfull and "ratedisc%gst%amount" in cfull:
        return "tax_invoice"
    if "product + party wise list" in tfull:
        return "product_party_wise_list"
    if "a.qtyfr.qtytotalqty" in cfull:
        return "product_itemwise_partywise"
    if (
        "customer,companyandproductsales" in cfull
        and "productnamepackingqtyfreerateamount" in cfull
    ):
        return "klm_customer_company_product"
    # SRI VASAVI DOSPrinter "COMPANY, CUSTOMER AND INVOICE SALES": Customer:<name>,<town>
    # bands + invoice-level rows (Inv|Date|Product|Pack|Batch|Qty|Free|Price|Value|Discount).
    # Distinct from klm_customer_company_product above (different word order, no Invoice/Batch/
    # Discount columns). Placed after it so existing rules always win.
    if (
        "company,customerandinvoicesales" in cfull
        and "invoiceinvoiceproductnamepackingbatchquantityfreepricevaluediscount" in cfull
    ):
        return "klm_company_customer_invoice"
    if (
        "customervsitemdetails" in cfull
        and "itemnameitemtownbilldatebillno" in cfull
    ):
        return "klm_customer_vs_item"
    if "customervsitemsummaries" in cfull and "group/names.qtys.free" in cfull:
        return "klm_customer_vs_item_summary"
    if "areawisepartywisesalessummary" in cfull and "productnamepackmakemaytotal" in cfull:
        return "areawise_partywise_summary_pdf"
    if "productwisesalelist(combined)" in cfull:
        return "product_wise_sale_combined"
    if (
        "salesanalysis" in cfull
        and "itemqtyfreevalue#totalqtytotalfreetotalvalue" in cfull
    ):
        # Marg "Sales Analysis" party report (VENUS PHARMA / KLM). 3-level banded
        # (Manufacturer -> Customer -> item lines) with a two-column glyph-bled
        # PDF text layer, so it is parsed positionally by word x-coordinates.
        # Signature = the full compact column header, verified to match ONLY this
        # file across the whole corpus (1/186 New_Data PDFs).
        return "marg_sales_analysis_pdf"
    if (
        "party/productwisenetsales" in cfull
        and "party/productnamesaleqtyretqtynetqty" in cfull
    ):
        return "party_product_net_sales_pdf"
    if (
        "billno.datenameofcustomerplacebatchqtyfreevalue" in cfull
        and "itemwise-billwise" in tfull
    ):
        return "jawahar_itemwise_billwise"
    # JEYANTHI PHARMAA "Areawise Sales Report" (KLM billwise, monospace DOS export): AREA
    # bands -> customer blocks -> bill-line item rows, free/scheme qty in the 'Repl' column.
    # Appended at the very tail so only files that fall through EVERY existing rule (currently
    # 'unknown', 0 rows) can reach it — no working file can be rerouted.
    if (
        "areawisesalesreport" in cfull
        and "productnamecustomernamebillnumberbilldatpackquanfreereplsalesvalue" in cfull
    ):
        return "areawise_sales_billwise"
    # C.D. ASSOCIATES "Customer & Product Sales" (Customer:<name> City:<city> bands, MP#####
    # invoice rows). Tail-placed so every existing rule wins first.
    if "customer&productsales" in cfull and "inv.nodateproductpackbatchqtyfreeratevalue" in cfull:
        return "customer_product_sales"
    # DEEPA(A) "PARTY WISE SALES STATEMENT" (KLM division bands, PARTY NAME ITEM NAME REP FRE
    # QTY VALUE DISC NET AMT; positional). Tail-placed.
    if "partywisesalesstatement" in cfull and "itemnamerepfreqtyvaluediscnetamt" in cfull:
        return "klm_party_wise_statement"
    return "unknown"
