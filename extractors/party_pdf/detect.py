import re


def _gvc_band_customer_fraction(text):
    """For a KLM 'Group Vs Customer Details' report, the fraction of BAND lines (no-date
    text lines that aren't furniture or bare-number subtotals) that look like customer
    names. ~1.0 => CUSTOMER-banded (M.K./BHAVYA: customer bands, item rows); ~0.0 =>
    PRODUCT-banded (SRI KRISHNA/SRI SUBRAHMANYA: item/address bands, customer rows)."""
    _date = re.compile(r"\b\d{1,2}/[A-Za-z]{3}/\d{2,4}\b")
    _cust = re.compile(
        r"MEDICAL|PHARMAC|STORES|AGENC|SURGICAL|MEDICALS|MEDICOS|TRADERS|ENTERPRIS|\bDRUG",
        re.I,
    )
    _furn = ("mkmedical", "bhavya", "srikrishna", "srisubra", "d.no", "groupvs",
             "itemname", "1stfloor", "page", "total")
    bands = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or _date.search(s) or re.match(r"^[\d,.\s]+$", s):
            continue
        low = s.lower().replace(" ", "")
        if low.startswith(_furn) or not re.search(r"[A-Za-z]{3}", s):
            continue
        bands.append(s)
    if not bands:
        return 0.0
    return sum(1 for b in bands if _cust.search(b)) / len(bands)


def detect_format(text, n_rects, n_lines):
    t = text[:2000]
    tl = t.lower()
    tl_compact = re.sub(r"\s+", "", tl)
    # --- 15July KLM Class-B overrides ------------------------------------------
    # These three files carry a generic report title (Sales Detail Register /
    # Customer & Product Analysis / Product + Party Wise List) that otherwise
    # matches the marg_register / profitmaker / marg_bordered rules below, but
    # their specific column layout makes those parsers return 0 rows (RED). Each
    # override is keyed on the file's EXACT compact column-header run — verified
    # corpus-unique so it only ever reclaims its own currently-RED files (the
    # full regression holds). Matched over the FULL text since the column header
    # can sit past the first 2000 chars on long reports.
    _cfull = re.sub(r"\s+", "", text.lower())
    # AAGAM / VISNAGAR "Sales Detail Register (Mf-Customerwise)" — the SrNo-first
    # AMOUNT-bearing variant. It shares the exact column header of its blank-amount
    # sibling prathna_register, so the header token alone cannot separate them;
    # the discriminator is the BODY: this variant has detail rows ending in TWO
    # decimals (Sale Rate + Amount) after a trailing-dot Qty, whereas prathna's
    # Amount column is blank so its rows end in a single decimal (Rate only).
    # Requiring an amount-bearing row keeps PRATHNA out of this gate (it falls
    # through to the marg_register -> prathna_register fallback in pdf_io). The
    # `[^\S\n]` (horizontal-whitespace) spacing pins the two-decimal run to ONE
    # line so a wrapped value on the next line can't forge a false match.
    if (
        "srnodateitemnamebatchnoqtyschqty" in _cfull
        and re.search(
            r"(?m)^\w[\w-]*[^\S\n]+\d{2}-\d{2}-\d{4}[^\S\n]+.+?\d+\.[^\S\n]+"
            r"[\d,]+\.\d{2,}[^\S\n]+[\d,]+\.\d{2,}[^\S\n]*$",
            text,
        )
    ):
        return "klm_sales_detail_register"
    # C.D. PHARMA: DASH-date dialect of "Customer & Product Analysis"; the
    # profitmaker sibling's row gate needs SLASH dates so it 0-rows this. Require
    # the exact header AND a dash-dated invoice detail row so a genuine
    # (slash-dated) profitmaker file never diverts here.
    if (
        "inv.nodateproductpackbatchqtyfreeratevalue" in _cfull
        and re.search(r"(?m)^[A-Za-z]{0,4}\d[\w-]*\s+\d{2}-\d{2}-\d{4}\s", text)
    ):
        return "customer_product_analysis_dash"
    # MANISH: 5-number "Product + Party Wise List" (Free/FreeAmt./SaleQty./Amount/
    # TotalAmt). marg_bordered claims it first (rects + "from:"); the 4-number
    # product_party_wise_list sibling (AKSHAR) has header "productfreesaleqty..."
    # with NO "freeamt", so this token cleanly separates the two.
    if "productfreefreeamt.saleqty" in _cfull:
        return "product_party_wise_freeamt"
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
    # KHATTAR "SALE REGISTER CONSOLIDATED" variant with an extra AVG.RATE column
    # (PARTY NAME ITEM NAME QUANTITY FREE AVG.RATE AMOUNT -> 4 numbers/row).
    if "partynameitemnamequantityfreeavg.rateamount" in tl_compact:
        return "sale_register_consolidated"
    # SwilERP "Product-Customer Wise Sales" (CAPITAL PHARMA AGENCIES): product
    # bands with per-customer rows (Customer | Station | Qty | Sales Value).
    # Positional — word x0 slices the columns the flat text can't.
    if (
        "product-customerwisesales" in tl_compact
        and "customerstationqty.salesvalue" in tl_compact
    ):
        return "product_customer_wise_sales"
    # "Company Party Wise Product Sale Report" (RAOUSHAN PHARMA, KLM): COMPANY
    # band -> PARTY heading -> product rows (Product | Qty | Free | Amt).
    if "company/party/productqtyfreeamt" in tl_compact:
        return "company_party_product_sale"
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
    # BHAGYODAY "Sales Detail Register (Mf-Areawise)" — MF/Area/Customer banded
    # per-invoice sales, 2-digit-year rows. Sibling of klm_sales_detail_register
    # (Mf-Customerwise); neither the itemwise nor the mf-customer register gate matches it.
    if "sales detail register" in tl and "mf-areawise" in tl:
        return "r15_klm_sales_detail_areawise"
    if "sales detail register" in tl and (
        "itemwise-customerwise" in tl or "mf-itemwise" in tl
    ):
        return "marg_register_itemwise"
    # SOURABH MEDICOSE "Sales Detail Summary (Mf-Customer-Itemwise)" — DATELESS,
    # item-code-bearing Sale/Pur/MRP-amount variant; the generic title routes it
    # to marg_summary (0 rows / RED). Keyed on the EXACT compact column header
    # (corpus-unique), so it only reclaims its own RED file. MUST precede marg_summary.
    if "itemnameitemcodeqtysaleamountpuramtschqtymrpamt" in _cfull:
        return "r15_marg_mf_customer_sales_summary"
    if "sales detail summary" in tl and (
        "mf-customer" in tl or "mf - customer" in tl
    ):
        return "marg_summary"
    # MARUTI "Sales Detail Register (Mf-Customer-Itemwise, Batchwise)" — the generic
    # title routes it to marg_register below (0 rows / RED); this exact contiguous
    # column-header run (Item Batch Qty S.Qty S.Rate MRP Amount) is unique. MUST precede marg_register.
    if "itembatchqtys.qtys.ratemrpamount" in _cfull:
        return "maruti_klm_batchwise_mf_customer"
    if "sales detail register" in tl and "mf-customer" in tl:
        return "marg_register"
    if "sale details" in tl and n_lines > 5:
        return "marg_sale_details"
    # AARCHI / ARCHI DISTRIBUTOR: 3-number "Product + Party Wise List"
    # (Free/SaleQty./Amount). marg_bordered claims it first (rects + "from:"); the
    # 4-num product_party_wise_list sibling (AKSHAR) compacts to
    # "productfreesaleqty.returnqty.amount" and the 5-num product_party_wise_freeamt
    # (MANISH) has "freeamt", so this exact run separates all three. MUST precede marg_bordered.
    if "productfreesaleqty.amount" in _cfull:
        return "product_party_wise_freeamt3"
    # STOCKWELL PHARMA: 8-number "Product + Party Wise List" (Free/SaleQty./ReturnQty/
    # TotalQty/Amount/TotalAmt/GSTAmt./GrossAmt.). Longer than every sibling token so
    # it cannot steal them; the 4-num AKSHAR parser 0-rows it. MUST precede marg_bordered.
    if "productfreesaleqty.returnqtytotalqtyamounttotalamtgstamt.grossamt." in _cfull:
        return "product_party_wise_totqty_gst"
    # AKSHAR / N.K.MEDICO "Product + Party Wise List Report" (4-num Free/SaleQty/
    # ReturnQty/Amount): the ruled export has huge n_rects so marg_bordered grabs it
    # before the title-keyed product_party_wise_list gate further down. Route by the
    # title here first — product_party_wise_list parses it cleanly (492/284 rows).
    if "product+partywiselist" in _cfull:
        return "product_party_wise_list"
    if n_rects > 50 and re.search(r"from:\s*\d{2}/\d{2}", tl):
        return "marg_bordered_billwise" if "bill no" in tl else "marg_bordered"
    # MAHESH "Customer-Wise Product-Wise Sales Summary": coded customer bands
    # ("A004 <NAME>,<CITY>") with per-product AGGREGATE rows (no bill numbers) —
    # the Unisolve billwise parser 0-rows it. Gate on its unique compact column
    # header; must precede the broader unisolve title rule below.
    if "codecustomername&cityprd.codeproductname" in tl_compact:
        return "customer_product_wise_summary"
    # SHREE ISHWAR MEDICAL AGENCY "Customer-Wise Product-Wise Sales" variant: shares
    # the unisolve title AND its header column run, but its rows use a non-standard
    # "BIJ <invno>" invoice-type that parse_unisolve 0-rows, and it has NO trailing
    # "Prod.Dis" column (which the standard unisolve variant — e.g. ANAND MEDICAL —
    # carries). The plain header token is a SUBSTRING of the Prod.Dis variant, so
    # the exclusion + the BIJ body-row guard are BOTH required to avoid stealing the
    # GREEN unisolve baselines. MUST precede the broad unisolve title rule.
    if (
        "productnamepackinv/dmnodatebatchno.qtyfreeratevalue" in tl_compact
        and "qtyfreeratevalueprod.dis" not in tl_compact
        and re.search(r"(?m)\bBIJ\s+\d", text)
    ):
        return "r15_ishwar_customer_product_pack_bij"
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
    # AMRITA "PARTY / ITEM WISE SALES SUMMARY" QTY+FREE-only variant (header
    # 'D E S C R I P T I O N QTY. FREE' — NO rate/amount/value column). Both
    # party_item_summary_nofree (needs money tokens) and busy_tally 0-row it.
    # The 'freerateamount' exclusion protects the area_item_sales_summary sibling
    # (its header contains 'descriptionqty.free' as a substring). MUST precede busy_tally.
    if (
        "party/itemwisesalessummary" in tl_compact
        and "descriptionqty.free" in tl_compact
        and "descriptionqty.freerateamount" not in tl_compact
        and "avr.rate" not in tl_compact
    ):
        return "party_item_summary_qtyfree"
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
    # NAIK AGENCIES "PARTY WISE SALE/PURCHASE REPORT" — WEP-style challan/bill item
    # register banded by party. Its header ("...PRODUCT CODE/ NAME PACKING BATCH NO.
    # EXP.DT. QTY FREE RATE AMOUNT") is caught by the coarse ("product c" + "====")
    # wep_legacy rule whose row regex 0-rows this dialect (RED). MUST precede wep_legacy.
    if "packingbatchno.exp.dt.qtyfree" in _cfull:
        return "naik_party_sale_purchase"
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
    # Prompt ERP "Normal" party-billwise, mixed-case BillRef variant (SHRI ASHOK
    # "klm party"). Same header/structure as prompt_normal but BillRefs are Cash/1130,
    # Credit-L/196, Credit-O/261 (mixed/lower-case), which prompt_normal's uppercase-only
    # regex 0-rows. Gated on the mixed-case token; MUST precede the prompt_normal rule.
    if (
        "productpackbillrefdatemrpbatchqtyfreerateamount" in tl_compact
        and (re.search(r"cash/\d", tl) or "credit-" in tl)
    ):
        return "prompt_billwise_mixed"
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
    # Value-bearing FREE variant of PARTY / ITEM WISE SALES SUMMARY: header
    # 'DESCRIPTION QTY. FREE RATE AMOUNT' compacts to 'descriptionqty.freerateamount'
    # (FREE between QTY. and RATE), which the plain nofree gate above rejects (needs
    # 'descriptionqty.rateamount', not a substring of the FREE variant). The
    # party_item_summary_qtyfree gate earlier already excludes this token. Reuses the
    # party_item_summary_nofree parser, which handles the FREE column + '.PARTY-AREA' headings.
    if (
        "d e s c r i p t i o n" in tfull
        and "party/itemwisesalessummary" in cfull
        and "descriptionqty.freerateamount" in cfull
        and "areaitemwise" not in cfull
        and "avr.rate" not in cfull
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
    # LAXMI "Itemwise Sales / Free Goods" (division+item banded) — also matches the
    # generic rp_pharma_itemwise title rule, but its glyph-corrupted compact header
    # token is specific and must win first. MUST precede rp_pharma_itemwise.
    if "bielxlpdntobilldtsm" in cfull:
        return "laxmi_itemwise_free_goods"
    if "itemwise sales details" in tfull and "party code & name" in tfull:
        return "rp_pharma_itemwise"
    if "companywiseareawisesalesdetail" in cfull:
        return "companywise_areawise"
    if "datebillnoproducthsnpack" in cfull:
        return "navkar_productwise"
    # KLM "Sales Statement" (bill-wise, scheme qty — KLM BILL WISE) shares the EXACT
    # column header of bajaj_salestatement ("BILL NO. PARTY NAME AMOUNT DISCOUNT NET
    # AMT TAX PAYABLE DR/CR NET AMOUNT"), so no detect token can separate them. Its
    # scheme-qty body layout makes parse_bajaj_salestatement return 0 rows, so it is
    # handled by the pdf_io 0-row fallback (bajaj_salestatement -> klm_salestatement_scheme)
    # instead — bajaj files that parse normally are byte-for-byte unaffected.
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
    # SREE SWATHI DOSPrinter "COMPANY AND PRODUCT, AREA, INVOICE": PRODUCT-major
    # sibling of the customer-major klm_company_customer_invoice above. Product Name:/
    # Area Name: bands -> invoice rows (Inv|Date|Customer Name|Qty|Free|Value|Discount);
    # the customer name is optional and Value reconciles to the printed Grand Total.
    # Distinct title/header tokens; tail-placed so existing rules always win.
    if (
        "companyandproduct,area,invoice" in cfull
        and "invoiceinvoicecustomernamequantityfreevaluediscount" in cfull
    ):
        return "sree_swathi_company_product_area_invoice"
    # KOOTTIPARAMBIL / AYYAPPA "Customerwise Itemwise Billwise Sales Report": company
    # (KLM <div>) + customer (<code> <name>,<town>) bands -> bill rows anchored on the
    # trailing 5 decimals (Rate MRP Value Pur.Rate Pur.Value); Value reconciles to the
    # per-customer + grand totals. Distinct title/header tokens; tail-placed.
    if (
        "customerwiseitemwisebillwisesalesreport" in cfull
        and "billnorefiddateitemdescriptionqtyfreeratemrpvaluepur.ratepur.value" in cfull
    ):
        return "customerwise_itemwise_billwise"
    # SRI SHIV SHAKTI "SALES STATEMENT OF THE COMPANY < KLM >": product-grouped party
    # statement, S.NO|PARTY rows; row AMOUNT (GST-incl.) reconciles to per-product +
    # grand TOTAL. Distinct title/header tokens; tail-placed.
    if (
        "salesstatementofthecompany<klm>" in cfull
        and "s.nopartynamebillno.dateqtyratedealdiscgstamount" in cfull
    ):
        return "sri_shiv_shakti_company_sales_statement"
    # TRADELINK "CUSTOMER - INVOICE - ITEM WISE SALE": customer-banded, item rows end
    # at MRP (no value col) -> amount = qty*rate, per-customer TOTAL is the oracle.
    if (
        "customer-invoice-itemwisesale" in cfull
        and "itcoderackpackitemnamebatchqty.freeratemrp" in cfull
    ):
        return "tradelink_customer_invoice_itemwise"
    # SAI BHASKAR "Customer VS Item Details": party-banded, POSITIONAL x1-band parser.
    # Shares the 'customervsitemdetails' title with klm_customer_vs_item below but its
    # header is 'Item name Town ...' (no second 'Item'), so the header tokens are
    # mutually exclusive. MUST precede klm_customer_vs_item to be safe.
    if (
        "customervsitemdetails" in cfull
        and "itemnametownbilldatebillno.batchnoqtyfreeratenetvalue" in cfull
    ):
        return "sai_bhaskar_customer_vs_item"
    # NAGAMMAI PHARMA "Customer Purchase-Divisionwise Report": POSITIONAL x1-band party
    # billwise. Per-party subtotal reconciles to <=0.01 (the oracle); glyph-corrupted
    # grand total is vendor-rounded <=0.06. Distinct title/header tokens; tail-placed.
    if (
        "customerpurchase-divisionwisereport" in cfull
        and "billdatbillnumberproductnamepackbatchexpirqtyfrereprat" in cfull
    ):
        return "klm_nagammai_customer_purchase_divisionwise"
    # ATTASSERIL "Partywise Qtywise Sales" (party code + name(phone),area; qty+amount, no rate).
    if "partywiseqtywisesales" in cfull:
        return "klm_partywise_qtywise_sales"
    # INDRA "Customer-ProductWiseSales" (customer-banded; product qty/free/amount).
    # Fully glued export: the title has NO spaces, so match tfull (space-preserving)
    # to avoid stealing the SPACED "Customer-Product wise Sales" report (Agrawal's
    # customer_product_wise_packing), which collapses to the same token in cfull.
    if "customer-productwisesales" in tfull:
        return "klm_customer_product_wise_sales"
    # LEO "Companywise Areawise Report" billwise (LP[HS]/n/n bill rows; TD col always '-').
    if (
        "companywiseareawisereport" in cfull
        and "billnodateitemnamebatchnoexpqtyfreetdsratetotal" in cfull
    ):
        return "leo_companywise_areawise_billwise"
    # JAI AMBEY "Customer Wise Sales(Detail)": horizontal page-split (text half + numeric
    # 'Qty(Unit1)'/'Amount' half), positional.
    if "customerwisesales(detail)" in cfull and "qty(unit1)" in cfull:
        return "jai_ambey_customer_wise_sales"
    # SRI SARAVANA "Sales Replacement Report": division/product/customer banded, positional.
    if "salesreplacementreport" in cfull and "billnumbe" in cfull:
        return "sri_sales_replacement_report"
    # AMRIT "Company wise - Sales statement" (billwise). Shares the title token with the
    # MISHRA two-column variant below; the 'Bill No Date Batch...' header is distinct.
    if (
        "companywise-salesstatement" in cfull
        and "billnodatebatchnoex.dtptrmrpqtyfreeamount" in cfull
    ):
        return "amrit_companywise_sales_statement"
    # MISHRA "Company wise - Sales statement" TWO-COLUMN variant (shares the AMRIT title
    # token; the doubled 'Product Name Packing Qty Free' header is distinct).
    if (
        "companywise-salesstatement" in cfull
        and "productnamepackingqtyfreeproductnamepackingqtyfree" in cfull
    ):
        return "mishra_companywise_partywise_twocol"
    # ARCHI "CUSTOMER+ ITEM WISE SALE".
    if (
        "customer+itemwisesale" in cfull
        and "saleqtyfreeqtytotalqtygrossamountnetamount" in cfull
    ):
        return "klm_customer_item_wise_sale"
    # ASHA "Item Wise Summary of Sale By Party".
    if (
        "itemwisesummaryofsalebyparty" in cfull
        and "sr.itemnameqtyfreevaluecgstsgstigstamount" in cfull
    ):
        return "klm_item_wise_sale_by_party"
    # BALAJI "Product-Customer Wise Sales" (has a Pin Code column). MUST precede the
    # SUMAN sibling below: SUMAN's header token is a prefix of BALAJI's, so BALAJI would
    # otherwise be mis-detected as SUMAN.
    if (
        "product-customerwisesales" in cfull
        and "customerstationqty.freeqtsalesvaluepincode" in cfull
    ):
        return "klm_product_customerwise_sales"
    # SUMAN "Product-Customer Wise Sales" (no Pin Code; different print geometry).
    if (
        "product-customerwisesales" in cfull
        and "customerstationqty.freeqtsalesvalue" in cfull
    ):
        return "suman_product_customer_wise_sales"
    # CHOUDHARY SwilERP "Customer Information".
    if "customerinformation" in cfull and "qty.valueqty.value" in cfull:
        return "choudhary_customer_information"
    # JACKSON "Companywise Customerwise Sales Statement".
    if (
        "companywisecustomerwisesalesstatement" in cfull
        and "productbillnodatebatchnoexpirymrpqtyrateamount" in cfull
    ):
        return "jackson_companywise_customerwise_sales"
    # JMV "Party & Product Wise Sale" (fully columnar).
    if (
        "party&productwisesale" in cfull
        and "itemcodecitypartynameproductnamepackingquantityfreeavg.rateamount" in cfull
    ):
        return "jmv_party_product_city"
    # KANARA "Areawise Partywise Sales".
    if (
        "areawisepartywisesales" in cfull
        and "nameproductpackinqtyfreevalue" in cfull
    ):
        return "kanara_areawise_partywise_sales"
    # MANISH "Product-Wise Customer-Wise Sales Summary".
    if (
        "product-wisecustomer-wisesalessummary" in cfull
        and "prd.codeproductname" in cfull
    ):
        return "manish_product_customer_summary"
    # RAVIRA "Customer And Company Sales" (glyph-fenced title 'E ... SalesF').
    if (
        "customerandcompanysalesf" in cfull
        and "inv.nodateprouctnamepackbatchqtyfreeamount" in cfull
    ):
        return "ravira_customer_company_sales"
    # TRINITY "PARTY + ITEM WISE SALE & SALE RETURN REPORT".
    if (
        "party+itemwisesale&salereturnreport" in cfull
        and "sno.itemnamepackingfreevalueg.amountnetamount" in cfull
    ):
        return "trinity_party_item_wise_sale"
    # SmartPharma360 "Customer-Company wise Product Sales" (KLM): Company Name: bands ->
    # per-invoice rows (Inv.No|InvDate|Product Name|Batch|Qty|Free|Rate|Value). Distinct
    # header from the klm_company_customer_invoice sibling above. Tail-placed.
    # SmartPharma360 "Customer-Company wise Product Sales" — URL variant (ABHIRAM):
    # rows have NO leading company prefix, SI-AB-26-... invoices, and a trailing
    # 'Invoice URL' column. Its token is a strict SUPERSET of the sibling's (adds
    # 'invoiceurl'), so it MUST be tested BEFORE the sibling; SRI BABA (no URL) is
    # not stolen.
    if (
        "customer-companywiseproductsales" in cfull
        and "inv.no.invdateproductnamebatchqtyfreeratevalueinvoiceurl" in cfull
    ):
        return "smartpharma_cust_company_url"
    if (
        "customer-companywiseproductsales" in cfull
        and "inv.no.invdateproductnamebatchqtyfreeratevalue" in cfull
    ):
        return "smartpharma_customer_company_sales"
    # SRI SHIRIDI SAI "Group Vs Customer Details" (KLM): product item-line + number-line
    # merged per row, customer-code paren bands. Distinct from klm_customer_vs_item below
    # (which needs 'customervsitemdetails'); tokens unique. Tail-placed.
    if (
        "groupvscustomerdetails" in cfull
        and "towndatenumberbatchmrpqtyfreereplacerategrossvaluenetvalue" in cfull
    ):
        return "klm_group_vs_customer"
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
    # SHREE SHIVASAKTHI MEDICAL AGENCIES "Areawise Sales Report" (KLM billwise,
    # monospace DOS export): CUSTOMER bands -> bill/item rows -> Customer Sub
    # Total + bare-7-num roll-up echoes. Different column order from JEYANTHI
    # (bill-first with customer BAND vs product-first with customer COLUMN), so
    # its header token is unique. Tail-placed so every existing rule wins first.
    if (
        "areawisesalesreport" in cfull
        and "billnumberbilldatepproductnamepackingquantfreeqdsalevaluetaxamounetamountrep" in cfull
    ):
        return "shivasakthi_areawise_billwise"
    # VASAN MEDICAL AGENCIES "Areawise Sales Report ... for <DIV> KLM LABORATORIES
    # PVT LTD": PRODUCT-FIRST billwise, AREA/CUSTOMER/TOWN carried in a positional
    # BAND (split by word x0), free/scheme qty in 'Free' col, 'Repl' always '-'.
    # Its column header differs from JEYANTHI's (packi/billnumber/qty/free/repl/
    # saleval) so no overlap. Tail-placed.
    if (
        "areawisesalesreport" in cfull
        and "productnamepackibillnumberbilldateqtyfreereplsaleval" in cfull
    ):
        return "vasan_areawise_billwise"
    # C.D. ASSOCIATES "Customer & Product Sales" (Customer:<name> City:<city> bands, MP#####
    # invoice rows). Tail-placed so every existing rule wins first.
    if "customer&productsales" in cfull and "inv.nodateproductpackbatchqtyfreeratevalue" in cfull:
        return "customer_product_sales"
    # DEEPA(A) "PARTY WISE SALES STATEMENT" (KLM division bands, PARTY NAME ITEM NAME REP FRE
    # QTY VALUE DISC NET AMT; positional). Tail-placed.
    if "partywisesalesstatement" in cfull and "itemnamerepfreqtyvaluediscnetamt" in cfull:
        return "klm_party_wise_statement"
    # CENTRAL AGENCIES "Areawise Sales Statment" (KLM billwise, text/plumber).
    # Signature = its unique compact column header; "codecustomernamerepcode"
    # collides with no other layout. Tail-placed so every existing rule wins.
    # CENTRAL DISTRIBUTORS "Areawise Sales Statment" — Packing-column variant of the
    # CENTRAL AGENCIES areawise_sales_statement: header carries an explicit "Packing"
    # column and the Rep Code is an alphabetic rep *name*, so the numeric-rep
    # areawise_sales_statement parser reads 0 rows. Its header token is a SUPERSET of the
    # plain gate below, so it MUST precede it.
    if "billnobilldatecodecustomernamerepcodeproductnamepackingqtyfreeqty" in cfull:
        return "areawise_sales_statement_packing"
    if "billnobilldatecodecustomernamerepcodeproductname" in cfull:
        return "areawise_sales_statement"
    # CENTRAL AGENCIES "Areawise Sales Statement" — AREA+CUSTOMER banded BlueFox variant
    # (KLM COSMO): NO Code/Customer Name/Rep Code column, so its header reads
    # 'billnobilldateproductname...' (not 'billnobilldatecodecustomername...'). Mutually
    # exclusive with the two gates above; party comes from the comma-bearing customer sub-band.
    if (
        "areawisesalesstatement" in cfull
        and "billnobilldateproductnamepackingqtyfreeqtyamount" in cfull
    ):
        return "areawise_sales_statement_banded"
    # VASAVI MEDICARE "Area Wise Sales Report for the period of <ISO> and
    # <ISO>": "<CODE> - <PARTY>, <AREA>-<PIN>" bands + invoice rows. Signature =
    # title + its compact column header. Tail-placed. (The JEYANTHI
    # areawise_sales_billwise gate needs a DIFFERENT column header, no overlap.)
    if (
        "areawisesalesreportfortheperiodof" in cfull
        and "sr.codeproductnamepackingbatchno.qtyfqtysch" in cfull
    ):
        return "areawise_sales_period"
    # VIJAY MEDICAL "SALE REGISTER DETAILED" (Marg billwise): "PARTY NAME - X"
    # bands, SNO|BILL DATE|BILL NO.|ITEM|LOT|QTY|FREE|RATE/UNIT|NET AMOUNT rows.
    # Signature = title + its compact header run. Tail-placed.
    if (
        "saleregisterdetailed" in cfull
        and "billdatebillno.itemname" in cfull
    ):
        return "sale_register_detailed"
    # BlueFox Systems "Customerwise Sales Statement on <Month>/<Year>" (FATIMA
    # HEALTHCARE): "<PARTY>,<TOWN>" bands -> bill rows. Signature = title + its
    # compact column header (both required). Tail-placed so existing rules win.
    if (
        "customerwisesalesstatementon" in cfull
        and "billdatebillnoproductpackingqtyfreeamount" in cfull
    ):
        return "bluefox_customerwise_sales"
    # PURANI HOSPITAL SUPPLIES "BackBone MFR Sales Detail Report" (11-col lattice):
    # Product|BillNo/Date|Customer|City|Batch|Expiry|Qty|Free|Rpl|PTR|Total Sales.
    # Positional lattice parser + straddle recovery. Tail-placed.
    if (
        "mfrsalesdetailreport" in cfull
        and "productnamebillno/datecustomernamecitybatchexpiryqtyfreeqty" in cfull
    ):
        return "backbone_mfr_sales_detail"
    # RAKESH MEDICAL STORES (Shimla) LOGIC ERP "CUSTOMER+ITEM WISE SALE". Positional;
    # '+' title distinguishes it from the hyphen 'customer-itemwisesale' rule above.
    if "customer+itemwisesale" in cfull and "customernameitemname" in cfull:
        return "customer_item_wise_sale"
    # KAPOOR MEDICAL STORE "PARTY+ITEM WISE SALE" (Marg billwise, positional): PARTY
    # NAME bands -> SNO|BILL NO|BILL DATE|ITEM|QTY|[FREE]|EXPIRY|MRP|GROSS|NET rows.
    if (
        "party+itemwisesale" in cfull
        and "billno.billdateitemname" in cfull
    ):
        return "kapoor_party_itemwise_sale"
    # UNIVERSAL MEDICAL AGENCY Marg "SALE SUMMARY" party-level roll-up (text): one row
    # per party "<PARTY> <int-May> <TotalValue>". Month-agnostic gate; 'salesummary'
    # (single 's') is NOT a substring of company_party_summary's 'salessummary'.
    if "salesummary" in cfull and "totalvalue" in cfull and "netsales" in cfull:
        return "marg_sale_summary_party"
    # KRISHNA SAI "Sales Statement Summary" (KLM division reports). ITEM-primary rows;
    # gated on title + its exact compact ITEM-first column header (distinct from the
    # PARTY-first sale_register 'partynameitemname...').
    if (
        "salesstatementsummary" in cfull
        and "itemnamepartynamequantityfreesaleamounttaxamount" in cfull
    ):
        return "sales_statement_summary_itemwise"
    # BALAJI "Mfacwise Custwise Areawise Itemwise Report" (KLM COSMO). Single unique token.
    if "mfacwisecustwiseareawiseitemwisereport" in cfull:
        return "mfacwise_custwise_itemwise"
    # SREE SUPREME (NAMAKKAL) KLM CASMO DOS exports — two sibling positional billwise
    # reports. Slash/dot tokens are distinct from the hyphenated product/customer gates.
    if "prod/cust.wisesales" in cfull and "inv.noinv.datecustomernameplaceqtyfreereplratevalue" in cfull:
        return "prodcust_wise_billwise"
    if "area-prod-wisesales" in cfull and "productnamepackginv.noinv.dateqtyfreereplvalue" in cfull:
        return "areaprod_wise_billwise"
    # Agrawal "Customer-Product wise Sales": CODE-NAME party headings + product rows
    # 'Product Name Packing Qty. Freeqty Value' (no product-code column, so distinct
    # from customer_product_grouped's 'productcodeproductnamepacking' gate above).
    if "customer-productwisesales" in cfull and "productnamepackingqty.freeqtyvalue" in cfull:
        return "customer_product_wise_packing"
    # KAKADE AGENCIES "Partywise Sales Summary" (Marg/MVGold HTML->PDF): one block per
    # party — a PARTY header line carrying the block's running Qty/Amount totals, then its
    # PRODUCT lines. Six trailing cols Qty|Sch Qty|Sch Amt|ID Amt|Amount|Amount-ID; the
    # 'Amount - ID' column is unique to this export. Tail-placed (before 'unknown') so every
    # existing rule wins first; matches only files currently falling through to unknown.
    if (
        "partywisesalessummary" in cfull
        and "particularsqtyschqtyschamtidamtamountamount-id" in cfull
    ):
        return "partywise_sales_summary"
    # MALU MEDICO Marg "CUSTOMER - INVOICE - ITEM WISE SALE" (KLM billwise): CUSTOMER band
    # -> per-invoice sub-band (date + SB/no + taxable/GST/invoice value) -> item lines
    # (COMPNAME PACK ITEM BATCH QTY SCM% RATE MRP NETAMT). Title + its exact compact column
    # header are corpus-unique (0/1083 PDFs). Tail-placed (before 'unknown').
    if (
        "customer-invoice-itemwisesale" in cfull
        and "compnamepackitemnamebatchqty.scm%ratemrpnetamt" in cfull
    ):
        return "customer_invoice_itemwise_sale"
    # METRO MEDICAL AGENCIES "Party Sale Report" — banded party layout. BOTH the party
    # heading and item rows end in numbers; the first numeric row after a header is the
    # party (running qty/amount totals), following rows are its items until the sums close.
    # Two dialects: 3-num "Particulars Address/unit Qty Scm Qty Amount" and 2-num
    # "Particulars Qty Amount". Gate = "Party Sale Report" title + exact header run
    # (corpus-unique). Tail-placed so every existing rule wins first.
    if "partysalereport" in cfull and (
        ("particularsaddress" in cfull and "scmqtyamount" in cfull)
        or "particularsqtyamount" in cfull
    ):
        return "party_sale_report"
    # HERITAGE MARKTEERS "Customerwise Billwise Itemwise Report": division band ->
    # customer band ("<code> <PARTY>,<addr town>") -> product-first billwise rows
    # (Bill No | Date | Item | Qty | Free | Rate | Value). Title + exact compact header
    # are corpus-unique.
    if (
        "customerwisebillwiseitemwisereport" in cfull
        and "billnodateitemdescriptionqtyfreeratevalue" in cfull
    ):
        return "customerwise_billwise_itemwise"
    # METRO "Party Product Analysis" (Orion): "PARTY : <name> Ph:.. <town>" bands ->
    # product rows with header 'CODE PRODUCT NAME PACK QTY FREE REPL VALUE' (REPL is a
    # replacement-qty column). Title + this exact compact header co-occur only here.
    if (
        "partyproductanalysis" in cfull
        and "codeproductnamepackqtyfreereplvalue" in cfull
    ):
        return "metro_orion_product_analysis"

    # ===== 15 July RED-cluster Class-A tail gates (batch 2) =====================
    # Every one of these files currently falls through EVERY rule above to
    # "unknown", so placing them here cannot reroute any working file. Tokens are
    # matched over the FULL compact text (cfull) since headers can sit past 2000
    # chars. The generic-header nilkanth gate is placed LAST.
    # R.P.DRUGS "klmpartywise" dealer statement — no header row; structural gate.
    if (
        "w.e.f." in _cfull
        and re.search(r"(?im)^\s*dealer:.+:", text)
        and re.search(r"(?m)^\s*\d+:.+?\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s+\d+N\s*$", text)
    ):
        return "r15_rpdrugs_dealer_partywise"
    # MediVision "Platinum" sale/DC SUMMARY sibling of medivision_sale_dc (details).
    if "customer-wise,product-wisesale/dcsummary" in cfull:
        return "medivision_sale_dc_summary"
    # KLM "Group Vs Customer Details" Icode/Ipack report — TWO dialects share this exact
    # title + column header. PRODUCT-banded (SRI SUBRAHMANYA / SRI KRISHNA: item name bands,
    # customers are the data rows) -> r15. CUSTOMER-banded (M.K. MEDICAL / BHAVYA: customer
    # name bands, items are the data rows) -> custbanded parser, which the r15 parser both
    # inverts (item<->party) and field-mangles (its x-anchors are hardcoded to SRI
    # SUBRAHMANYA's shifted-right coordinates). The band-content fraction separates them
    # cleanly (customer-banded >=0.83, product-banded ==0.0).
    if "groupvscustomerdetails" in cfull and "icodeipacktowndocdatebillnobatch" in cfull:
        if _gvc_band_customer_fraction(text) > 0.5:
            return "klm_group_vs_customer_custbanded"
        return "r15_klm_group_vs_customer_icode"
    # PURUSHOTHAM "Area Wise Customer, Company And Product Sales" (PROFITMAKER, positional).
    if (
        "areawisecustomer,companyandproductsales" in cfull
        and "productnameqtyfreegrossnetamount" in cfull
    ):
        return "r15_profitmaker_area_ccp"
    # SmartPharma360 Packing/Mrp/Discount variant (PRUDHVI) — superset header of the sibling.
    if (
        "customer-companywiseproductsales" in cfull
        and "inv.no.invdateproductnamepackingbatchmrpqtyfreeratediscountvalue" in cfull
    ):
        return "smartpharma_cust_company_pack_disc"
    # SUDHIR "COMPANY / ITEM WISE SALES SUMMARY" — division>party>product, disc% col.
    if (
        "company/itemwisesalessummary" in cfull
        and "descriptionqty.freerateamount(%)" in cfull
    ):
        return "company_item_wise_sales_summary"
    # HMRS PHARMA CARE "Party / Product (Area Wise)" — Free col printed but never filled.
    if (
        "pcodeproductnameinvnoareacityinvdateqtyfreegrsamtmanufacturer" in _cfull
        and re.search(r"(?m)^\d{3,7}\s+.*?\d{2}/\d{2}/\d{4}\s+\d+\s+[\d,]+\.\d+", text)
    ):
        return "r15_hmrs_klm_party_product_areawise"
    # PHARMA + plus "Product wise sale list" — narrow wrapped columns; positional.
    if "datbillproducthpabatcex.qty.freremrratval" in cfull:
        return "r15_pharmaplus_productwise"
    # SUN TRADER "List of Sale By Party" (Data Spec).
    if "qtyfreemrppurateratevaluenetrateamount" in _cfull:
        return "suntraders_saleby_party_docno"
    # BHOOLA "SALES REGISTER [ALL PARTY WITH ALL PRODUCTS]" — Free-Qty/Free-Value split.
    if "productnamefreeqtyfreevalueqtytotalqtyamount" in _cfull:
        return "r15_saleregister_allparty_freeqty"
    # SANTRAM "Customerwise Itemwise" — Mkt By/Division/Code/Item/Packing.
    if "sr.mktbydivisioncodeitemnamepacking" in _cfull:
        return "santram_customerwise_itemwise_qty"
    # SUCCESS PHARMAA "Areawise Sales Report" — truncated fixed-width header; positional.
    if "productnamepackiquanfreereplnetamoun" in _cfull:
        return "success_areawise_report"
    # SAI GANESH "SALES REPORT" — product/pack/batch, MRP column; positional.
    if "productpackbatchqtyfreemrprateamount" in _cfull:
        return "saiganesh_product_pack_batch"
    # RAMESH MEDICAL "PARTYWISE/ITEMWISE SALE" — packing glued in name; Qty/Free/Tot.Qty./Value.
    if "packingquantityfreetot.qty.value" in cfull:
        return "r15_ramesh_partywise_itemwise_pack"
    # KLM "Item-wise Customer-wise Offtake" — Company>Product>Customer rows.
    if "itemdescriptiontotalbonusquantityrateamountamount" in cfull:
        return "klm_customerwise_offtake"
    # NILKANTH "Product Summary" — generic Product/Pack/Qty/Free/Rate/Amount header;
    # positional. Placed LAST so every more-specific gate above wins first.
    if "productpackqtyfreerateamount" in cfull:
        return "nilkanth_product_summary_pack"
    return "unknown"
